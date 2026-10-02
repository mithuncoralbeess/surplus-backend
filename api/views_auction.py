import logging
from decimal import Decimal
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from AdminApp.models import Auction, AuctionBid, AuctionImage, AuctionWatchlist, VendorDetails
from AdminApp.auction_engine import AuctionEngine, AuctionBiddingError

logger = logging.getLogger(__name__)


def _get_vendor_from_request(request):
    """
    Helper to resolve VendorDetails from request.user, session, or vendor_id header/body.
    """
    # 1. From authenticated DRF user if available
    if getattr(request, "user", None) and request.user.is_authenticated:
        vendor = VendorDetails.objects.filter(email=request.user.email).first()
        if vendor:
            return vendor

    # 2. From vendor_id in request body or headers
    vendor_id = request.data.get("vendor_id") or request.headers.get("X-Vendor-Id") or request.GET.get("vendor_id")
    if vendor_id:
        v_str = str(vendor_id).strip()
        clean_id = v_str[4:].strip() if v_str.upper().startswith("USR-") else v_str
        try:
            return VendorDetails.objects.filter(id=int(clean_id), status=True).first()
        except (ValueError, TypeError):
            return VendorDetails.objects.filter(email__iexact=v_str, status=True).first()

    return None


@csrf_exempt
@api_view(["GET"])
@permission_classes([AllowAny])
def list_auctions(request):
    """
    GET /api/auctions/
    List auctions with filtering by status (live, upcoming, ended), category, search, and sorting.
    """
    status_filter = request.GET.get("status", "all").lower()
    item_type = request.GET.get("item_type")
    category_id = request.GET.get("category_id")
    query = request.GET.get("q", "").strip()
    ordering = request.GET.get("ordering", "-created_at")

    qs = Auction.objects.select_related("category", "vendor", "winner").prefetch_related("images")

    # Exclude drafts from public listing
    qs = qs.exclude(status="draft")

    now = timezone.now()

    if status_filter == "live":
        qs = qs.filter(status="live") | qs.filter(status="scheduled", start_time__lte=now, end_time__gt=now)
    elif status_filter == "upcoming" or status_filter == "scheduled":
        qs = qs.filter(status="scheduled", start_time__gt=now)
    elif status_filter == "ended":
        qs = qs.filter(status__in=["ended", "sold", "reserve_not_met"])

    if item_type:
        qs = qs.filter(item_type=item_type)

    if category_id:
        qs = qs.filter(category_id=category_id)

    if query:
        qs = qs.filter(title__icontains=query) | qs.filter(auction_id__icontains=query) | qs.filter(description__icontains=query)

    valid_orderings = ["-created_at", "created_at", "end_time", "-current_bid", "current_bid", "total_bids"]
    if ordering in valid_orderings:
        qs = qs.order_by(ordering)
    else:
        qs = qs.order_by("-created_at")

    # Pagination
    page_number = request.GET.get("page", 1)
    page_size = min(int(request.GET.get("page_size", 12)), 50)
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page_number)

    results = []
    for a in page_obj:
        a.sync_status()
        primary_img = a.images.filter(is_primary=True).first() or a.images.first()
        results.append({
            "id": a.id,
            "auction_id": a.auction_id,
            "title": a.title,
            "item_type": a.item_type,
            "item_reference_id": a.item_reference_id,
            "currency": a.currency,
            "starting_bid": str(a.starting_bid),
            "current_bid": str(a.current_bid),
            "minimum_next_bid": str(a.minimum_next_bid),
            "buy_now_price": str(a.buy_now_price) if a.buy_now_price else None,
            "total_bids": a.total_bids,
            "status": a.status,
            "is_live": a.is_live,
            "time_remaining_seconds": a.time_remaining_seconds,
            "start_time": a.start_time.isoformat(),
            "end_time": a.end_time.isoformat(),
            "primary_image": primary_img.url if primary_img else None,
            "category_name": a.category.name if a.category else None,
        })

    return Response({
        "success": True,
        "count": paginator.count,
        "num_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "results": results,
    }, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["GET"])
@permission_classes([AllowAny])
def auction_detail(request, auction_id):
    """
    GET /api/auctions/<auction_id>/
    Full auction details, media gallery, item specifications snapshot, and current bid state.
    """
    try:
        if str(auction_id).isdigit():
            auction = Auction.objects.select_related("category", "vendor", "winner").prefetch_related("images", "bids").get(id=int(auction_id))
        else:
            auction = Auction.objects.select_related("category", "vendor", "winner").prefetch_related("images", "bids").get(auction_id=auction_id)
    except Auction.DoesNotExist:
        return Response({"success": False, "message": "Auction not found."}, status=status.HTTP_404_NOT_FOUND)

    auction.sync_status()
    auction.views_count += 1
    auction.save(update_fields=["views_count"])

    current_vendor = _get_vendor_from_request(request)
    live_state = AuctionEngine.get_live_state(auction.id, current_user=current_vendor)

    images = [{"id": img.id, "url": img.url, "is_primary": img.is_primary} for img in auction.images.all()]

    is_watchlisted = False
    if current_vendor:
        is_watchlisted = AuctionWatchlist.objects.filter(auction=auction, user=current_vendor).exists()

    return Response({
        "success": True,
        "auction": {
            "id": auction.id,
            "auction_id": auction.auction_id,
            "title": auction.title,
            "description": auction.description,
            "item_type": auction.item_type,
            "item_reference_id": auction.item_reference_id,
            "item_metadata": auction.item_metadata,
            "category": {"id": auction.category.id, "name": auction.category.name} if auction.category else None,
            "vendor_name": auction.vendor.company_name or auction.vendor.username if auction.vendor else "Surplus Liquidations",
            "currency": auction.currency,
            "starting_bid": str(auction.starting_bid),
            "current_bid": str(auction.current_bid),
            "minimum_next_bid": str(auction.minimum_next_bid),
            "bid_increment": str(auction.bid_increment),
            "buy_now_price": str(auction.buy_now_price) if auction.buy_now_price else None,
            "status": auction.status,
            "is_live": auction.is_live,
            "total_bids": auction.total_bids,
            "views_count": auction.views_count,
            "time_remaining_seconds": auction.time_remaining_seconds,
            "start_time": auction.start_time.isoformat(),
            "end_time": auction.end_time.isoformat(),
            "auto_extend_minutes": auction.auto_extend_minutes,
            "images": images,
            "is_watchlisted": is_watchlisted,
            "live_bidding": live_state,
        }
    }, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def place_bid(request, auction_id):
    """
    POST /api/auctions/<auction_id>/bid/
    Atomically places a bid via AuctionEngine.
    Body: { "amount": 250.00, "vendor_id": 12, "max_proxy_amount": 500.00 (optional) }
    """
    vendor = _get_vendor_from_request(request)
    if not vendor:
        return Response({
            "success": False,
            "message": "Authentication required. Please login with your buyer account to place bids."
        }, status=status.HTTP_401_UNAUTHORIZED)

    raw_amount = request.data.get("amount")
    if not raw_amount:
        return Response({"success": False, "message": "Bid amount is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        amount = Decimal(str(raw_amount))
    except Exception:
        return Response({"success": False, "message": "Invalid bid amount specified."}, status=status.HTTP_400_BAD_REQUEST)

    max_proxy = request.data.get("max_proxy_amount")
    if max_proxy:
        try:
            max_proxy = Decimal(str(max_proxy))
        except Exception:
            max_proxy = None

    client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")

    try:
        bid_result = AuctionEngine.place_bid(
            auction_identifier=auction_id,
            bidder=vendor,
            amount=amount,
            max_proxy_amount=max_proxy,
            ip_address=client_ip
        )
        return Response(bid_result, status=status.HTTP_201_CREATED)
    except AuctionBiddingError as e:
        return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error placing bid")
        return Response({"success": False, "message": f"Server error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(["GET"])
@permission_classes([AllowAny])
def live_auction_feed(request, auction_id):
    """
    GET /api/auctions/<auction_id>/live-feed/
    Lightweight, fast endpoint for frontend polling countdown & current bid updates.
    """
    current_vendor = _get_vendor_from_request(request)
    state = AuctionEngine.get_live_state(auction_id, current_user=current_vendor)
    if not state.get("success"):
        return Response(state, status=status.HTTP_404_NOT_FOUND)
    return Response(state, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def buy_now(request, auction_id):
    """
    POST /api/auctions/<auction_id>/buy-now/
    Instant buyout purchase.
    """
    vendor = _get_vendor_from_request(request)
    if not vendor:
        return Response({
            "success": False,
            "message": "Authentication required. Please login with your buyer account."
        }, status=status.HTTP_401_UNAUTHORIZED)

    client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")

    try:
        res = AuctionEngine.execute_buy_now(auction_identifier=auction_id, buyer=vendor, ip_address=client_ip)
        return Response(res, status=status.HTTP_200_OK)
    except AuctionBiddingError as e:
        return Response({"success": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.exception("Unexpected error executing buy now")
        return Response({"success": False, "message": f"Server error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(["GET"])
@permission_classes([AllowAny])
def my_bids(request):
    """
    GET /api/auctions/my-bids/
    Returns all auctions the authenticated user has participated in.
    """
    vendor = _get_vendor_from_request(request)
    if not vendor:
        return Response({"success": False, "message": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

    bids_qs = AuctionBid.objects.filter(bidder=vendor).select_related("auction").order_by("-created_at")

    # Group by auction
    participated_auctions = {}
    for bid in bids_qs:
        auc = bid.auction
        if auc.id not in participated_auctions:
            participated_auctions[auc.id] = {
                "auction_id": auc.auction_id,
                "title": auc.title,
                "currency": auc.currency,
                "current_bid": str(auc.current_bid),
                "my_highest_bid": str(bid.amount),
                "status": auc.status,
                "is_live": auc.is_live,
                "time_remaining_seconds": auc.time_remaining_seconds,
                "user_is_winning": auc.winner_id == vendor.id if auc.status == "sold" else bid.is_winning,
                "is_won": bool(auc.status == "sold" and auc.winner_id == vendor.id),
            }

    return Response({
        "success": True,
        "count": len(participated_auctions),
        "auctions": list(participated_auctions.values()),
    }, status=status.HTTP_200_OK)


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def toggle_watchlist(request, auction_id):
    """
    POST /api/auctions/<auction_id>/watchlist/
    Adds or removes an auction from the user's watchlist.
    """
    vendor = _get_vendor_from_request(request)
    if not vendor:
        return Response({"success": False, "message": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        auction = Auction.objects.get(auction_id=auction_id) if not str(auction_id).isdigit() else Auction.objects.get(id=int(auction_id))
    except Auction.DoesNotExist:
        return Response({"success": False, "message": "Auction not found."}, status=status.HTTP_404_NOT_FOUND)

    existing = AuctionWatchlist.objects.filter(auction=auction, user=vendor).first()
    if existing:
        existing.delete()
        return Response({"success": True, "watchlisted": False, "message": "Removed from watchlist."}, status=status.HTTP_200_OK)
    else:
        AuctionWatchlist.objects.create(auction=auction, user=vendor)
        return Response({"success": True, "watchlisted": True, "message": "Added to watchlist."}, status=status.HTTP_201_CREATED)
