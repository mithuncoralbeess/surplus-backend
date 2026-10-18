import logging
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from AdminApp.models import Auction, AuctionBid, VendorDetails

logger = logging.getLogger(__name__)


class AuctionBiddingError(Exception):
    """Custom exception for auction bidding business rule violations."""
    pass


class AuctionEngine:
    """
    Core Bidding & Lifecycle Engine.
    Engineered to be completely model-agnostic, concurrency-safe, and self-contained.
    """

    @classmethod
    @transaction.atomic
    def place_bid(cls, auction_identifier, bidder: VendorDetails, amount: Decimal, max_proxy_amount: Decimal = None, ip_address: str = None) -> dict:
        """
        Atomically places a bid on an auction with row-level locking to prevent race conditions.
        Handles minimum bid increment validation, self-bidding prevention, and anti-sniping extensions.
        """
        if not bidder or not bidder.id:
            raise AuctionBiddingError("A valid, registered bidder account is required to place bids.")

        # Lock the auction row until transaction completes
        try:
            if isinstance(auction_identifier, int) or (isinstance(auction_identifier, str) and auction_identifier.isdigit()):
                auction = Auction.objects.select_for_update().get(id=int(auction_identifier))
            else:
                auction = Auction.objects.select_for_update().get(auction_id=str(auction_identifier))
        except Auction.DoesNotExist:
            raise AuctionBiddingError("Auction listing not found.")

        # Sync temporal state (scheduled -> live, live -> ended)
        auction.sync_status()

        now = timezone.now()

        # Validate that the auction is currently active for bidding
        if auction.status != "live":
            if auction.status == "scheduled" and auction.start_time <= now <= auction.end_time:
                auction.status = "live"
                auction.save(update_fields=["status", "updated_at"])
            elif auction.status == "scheduled":
                raise AuctionBiddingError(f"Auction has not started yet. Bidding opens on {auction.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}.")
            else:
                raise AuctionBiddingError(f"Bidding is closed. Current auction status is '{auction.status}'.")

        # Ensure end time has not passed
        if now >= auction.end_time:
            auction.status = "ended"
            auction.save(update_fields=["status", "updated_at"])
            raise AuctionBiddingError("Auction has ended. No further bids can be accepted.")

        # Prevent vendor/seller from bidding on their own item (anti-shill bidding)
        if auction.vendor and auction.vendor.id == bidder.id:
            raise AuctionBiddingError("Sellers and consignors are prohibited from bidding on their own listings.")

        amount = Decimal(str(amount))
        min_required = auction.minimum_next_bid

        # Validate minimum bid threshold
        if amount < min_required:
            raise AuctionBiddingError(
                f"Bid of ${amount:,.2f} is too low. The minimum acceptable bid is ${min_required:,.2f} "
                f"(current bid: ${auction.current_bid:,.2f} + ${auction.bid_increment:,.2f} increment)."
            )

        # Anti-Sniping Soft Close Logic:
        # If a bid arrives in the final threshold window (e.g. 120 seconds), extend end_time
        seconds_left = (auction.end_time - now).total_seconds()
        was_extended = False
        if 0 < seconds_left <= auction.auto_extend_threshold_seconds:
            auction.end_time += timedelta(minutes=auction.auto_extend_minutes)
            was_extended = True
            logger.info(
                f"[AuctionEngine] Anti-sniping triggered for {auction.auction_id}. "
                f"Extended by {auction.auto_extend_minutes} mins to {auction.end_time.isoformat()}."
            )

        # Demote previous winning bids for this auction
        AuctionBid.objects.filter(auction=auction, is_winning=True).update(is_winning=False)

        # Create immutable bid record
        bid = AuctionBid.objects.create(
            auction=auction,
            bidder=bidder,
            amount=amount,
            max_proxy_amount=Decimal(str(max_proxy_amount)) if max_proxy_amount else None,
            bid_type="proxy" if max_proxy_amount else "manual",
            is_winning=True,
            ip_address=ip_address,
        )

        # Update auction state
        auction.current_bid = amount
        auction.total_bids += 1
        auction.save(update_fields=["current_bid", "total_bids", "end_time", "updated_at"])

        return {
            "success": True,
            "message": f"Bid of ${amount:,.2f} placed successfully!",
            "bid_id": bid.id,
            "auction_id": auction.auction_id,
            "amount": str(amount),
            "current_bid": str(auction.current_bid),
            "minimum_next_bid": str(auction.minimum_next_bid),
            "total_bids": auction.total_bids,
            "extended": was_extended,
            "end_time": auction.end_time.isoformat(),
            "time_remaining_seconds": auction.time_remaining_seconds,
            "is_reserve_met": auction.is_reserve_met,
        }

    @classmethod
    @transaction.atomic
    def execute_buy_now(cls, auction_identifier, buyer: VendorDetails, ip_address: str = None) -> dict:
        """
        Instantly concludes the auction via the Buy-Now price if configured.
        """
        try:
            if isinstance(auction_identifier, int) or (isinstance(auction_identifier, str) and auction_identifier.isdigit()):
                auction = Auction.objects.select_for_update().get(id=int(auction_identifier))
            else:
                auction = Auction.objects.select_for_update().get(auction_id=str(auction_identifier))
        except Auction.DoesNotExist:
            raise AuctionBiddingError("Auction listing not found.")

        auction.sync_status()

        if not auction.buy_now_price or auction.buy_now_price <= Decimal("0.00"):
            raise AuctionBiddingError("Instant Buy Now is not enabled for this auction.")

        if auction.status not in ("scheduled", "live"):
            raise AuctionBiddingError(f"Cannot buy now. Auction is currently '{auction.status}'.")

        if auction.vendor and auction.vendor.id == buyer.id:
            raise AuctionBiddingError("Sellers cannot buy their own listings.")

        buy_price = auction.buy_now_price

        # Demote previous winning bids
        AuctionBid.objects.filter(auction=auction, is_winning=True).update(is_winning=False)

        # Record buy now bid
        bid = AuctionBid.objects.create(
            auction=auction,
            bidder=buyer,
            amount=buy_price,
            bid_type="buy_now",
            is_winning=True,
            ip_address=ip_address,
        )

        # Conclude auction
        auction.status = "sold"
        auction.winner = buyer
        auction.winning_bid_amount = buy_price
        auction.current_bid = buy_price
        auction.total_bids += 1
        auction.save(update_fields=[
            "status", "winner", "winning_bid_amount", "current_bid", "total_bids", "updated_at"
        ])

        return {
            "success": True,
            "message": f"Congratulations! You purchased {auction.title} for ${buy_price:,.2f}.",
            "auction_id": auction.auction_id,
            "bid_id": bid.id,
            "price": str(buy_price),
            "status": "sold",
        }

    @classmethod
    @transaction.atomic
    def evaluate_and_close(cls, auction_identifier) -> Auction:
        """
        Evaluates final bids against the confidential reserve price and seals the auction outcome.
        """
        if isinstance(auction_identifier, int) or (isinstance(auction_identifier, str) and auction_identifier.isdigit()):
            auction = Auction.objects.select_for_update().get(id=int(auction_identifier))
        else:
            auction = Auction.objects.select_for_update().get(auction_id=str(auction_identifier))

        top_bid = auction.bids.order_by("-amount", "-created_at").first()

        if top_bid:
            if auction.is_reserve_met:
                auction.status = "sold"
                auction.winner = top_bid.bidder
                auction.winning_bid_amount = top_bid.amount
                top_bid.is_winning = True
                top_bid.save(update_fields=["is_winning"])
            else:
                auction.status = "reserve_not_met"
        else:
            auction.status = "ended"

        auction.save(update_fields=["status", "winner", "winning_bid_amount", "updated_at"])
        return auction

    @classmethod
    def get_live_state(cls, auction_identifier, current_user: VendorDetails = None) -> dict:
        """
        Returns a high-speed, lightweight dictionary of auction status for UI live polling / WebSockets.
        Masks bidder identities (e.g., 'j***9') for public fairness and privacy.
        """
        try:
            if isinstance(auction_identifier, int) or (isinstance(auction_identifier, str) and auction_identifier.isdigit()):
                auction = Auction.objects.get(id=int(auction_identifier))
            else:
                auction = Auction.objects.get(auction_id=str(auction_identifier))
        except Auction.DoesNotExist:
            return {"success": False, "error": "Auction not found"}

        auction.sync_status()

        # Fetch recent 10 bids
        recent_bids = []
        for b in auction.bids.select_related("bidder").order_by("-created_at")[:10]:
            username = b.bidder.username if b.bidder else "Anonymous"
            masked_name = cls._mask_username(username)
            recent_bids.append({
                "id": b.id,
                "amount": str(b.amount),
                "bidder_masked": masked_name,
                "bid_type": b.bid_type,
                "is_winning": b.is_winning,
                "created_at": b.created_at.strftime("%H:%M:%S UTC"),
                "is_current_user": bool(current_user and b.bidder_id == current_user.id),
            })

        user_is_winning = False
        user_bid_count = 0
        if current_user and current_user.id:
            winning_bid = auction.bids.filter(is_winning=True).first()
            user_is_winning = bool(winning_bid and winning_bid.bidder_id == current_user.id)
            user_bid_count = auction.bids.filter(bidder=current_user).count()

        return {
            "success": True,
            "auction_id": auction.auction_id,
            "title": auction.title,
            "status": auction.status,
            "is_live": auction.is_live,
            "currency": auction.currency,
            "starting_bid": str(auction.starting_bid),
            "current_bid": str(auction.current_bid),
            "minimum_next_bid": str(auction.minimum_next_bid),
            "bid_increment": str(auction.bid_increment),
            "buy_now_price": str(auction.buy_now_price) if auction.buy_now_price else None,
            "total_bids": auction.total_bids,
            "time_remaining_seconds": auction.time_remaining_seconds,
            "start_time": auction.start_time.isoformat(),
            "end_time": auction.end_time.isoformat(),
            "is_reserve_met": auction.is_reserve_met,
            "user_is_winning": user_is_winning,
            "user_bid_count": user_bid_count,
            "winner_name": cls._mask_username(auction.winner.username) if auction.winner else None,
            "winning_bid_amount": str(auction.winning_bid_amount) if auction.winning_bid_amount else None,
            "recent_bids": recent_bids,
        }

    @staticmethod
    def _mask_username(username: str) -> str:
        """Masks a username for bidder privacy: 'john_doe' -> 'j***e'"""
        if not username:
            return "User"
        if len(username) <= 2:
            return username[0] + "*"
        return username[0] + "***" + username[-1]
