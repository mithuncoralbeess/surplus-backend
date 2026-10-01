from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone

from AdminApp.models import Auction, AuctionBid, VendorDetails, MainCategory
from AdminApp.auction_engine import AuctionEngine, AuctionBiddingError


class AuctionEngineTests(TestCase):
    def setUp(self):
        # Create test bidders
        self.seller = VendorDetails.objects.create(
            username="seller_user",
            email="seller@example.com",
            full_name="Seller Company Inc",
            user_type="SELLER",
        )
        self.buyer1 = VendorDetails.objects.create(
            username="buyer_one",
            email="buyer1@example.com",
            full_name="Buyer One Corp",
            user_type="BUYER",
        )
        self.buyer2 = VendorDetails.objects.create(
            username="buyer_two",
            email="buyer2@example.com",
            full_name="Buyer Two Ltd",
            user_type="BUYER",
        )

        self.category = MainCategory.objects.create(
            name="Industrial Equipment",
            slug="industrial-equipment",
        )

        now = timezone.now()
        self.start_time = now - timedelta(hours=1)
        self.end_time = now + timedelta(days=2)

        # Create model-agnostic test auction
        self.auction = Auction.objects.create(
            title="Surplus Inverter Generators Batch",
            description="50 Units of high-capacity backup generators",
            item_type="custom",
            item_reference_id="GEN-2026-TEST",
            item_metadata={"origin": "Test Liquidation", "units": 50},
            category=self.category,
            vendor=self.seller,
            starting_bid=Decimal("500.00"),
            current_bid=Decimal("500.00"),
            reserve_price=Decimal("1200.00"),
            bid_increment=Decimal("50.00"),
            buy_now_price=Decimal("2000.00"),
            start_time=self.start_time,
            end_time=self.end_time,
            auto_extend_minutes=3,
            auto_extend_threshold_seconds=120,
            status="live",
        )

    def test_first_bid_at_starting_bid(self):
        """First bid should be acceptable at starting bid."""
        res = AuctionEngine.place_bid(self.auction.id, self.buyer1, Decimal("500.00"))
        self.assertTrue(res["success"])
        self.auction.refresh_from_db()
        self.assertEqual(self.auction.current_bid, Decimal("500.00"))
        self.assertEqual(self.auction.total_bids, 1)

    def test_subsequent_bid_increment(self):
        """Second bid must respect bid increment ($500 + $50 = $550)."""
        AuctionEngine.place_bid(self.auction.id, self.buyer1, Decimal("500.00"))

        # Too low bid ($520 < $550) should be rejected
        with self.assertRaises(AuctionBiddingError) as ctx:
            AuctionEngine.place_bid(self.auction.id, self.buyer2, Decimal("520.00"))
        self.assertIn("too low", str(ctx.exception).lower())

        # Valid bid ($550)
        res = AuctionEngine.place_bid(self.auction.id, self.buyer2, Decimal("550.00"))
        self.assertTrue(res["success"])
        self.auction.refresh_from_db()
        self.assertEqual(self.auction.current_bid, Decimal("550.00"))
        self.assertEqual(self.auction.total_bids, 2)

    def test_seller_cannot_bid_on_own_auction(self):
        """Anti-shill bidding: Vendor cannot bid on their own item."""
        with self.assertRaises(AuctionBiddingError) as ctx:
            AuctionEngine.place_bid(self.auction.id, self.seller, Decimal("600.00"))
        self.assertIn("prohibited", str(ctx.exception).lower())

    def test_anti_sniping_soft_close_extension(self):
        """Bids placed in the final 2 minutes trigger end_time auto-extension."""
        now = timezone.now()
        # Set auction to expire in 60 seconds (within the 120s threshold)
        self.auction.end_time = now + timedelta(seconds=60)
        self.auction.save()

        original_end = self.auction.end_time
        res = AuctionEngine.place_bid(self.auction.id, self.buyer1, Decimal("500.00"))

        self.assertTrue(res["extended"])
        self.auction.refresh_from_db()
        # Should have extended by 3 minutes (180s)
        self.assertGreater(self.auction.end_time, original_end)

    def test_buy_now_concludes_auction(self):
        """Buy Now purchases immediately and marks auction as sold."""
        res = AuctionEngine.execute_buy_now(self.auction.id, self.buyer1)
        self.assertTrue(res["success"])
        self.auction.refresh_from_db()
        self.assertEqual(self.auction.status, "sold")
        self.assertEqual(self.auction.winner, self.buyer1)
        self.assertEqual(self.auction.winning_bid_amount, Decimal("2000.00"))

    def test_reserve_not_met_outcome(self):
        """If highest bid is below reserve price ($1,200), auction seals as reserve_not_met."""
        AuctionEngine.place_bid(self.auction.id, self.buyer1, Decimal("800.00"))
        evaluated = AuctionEngine.evaluate_and_close(self.auction.id)
        self.assertEqual(evaluated.status, "reserve_not_met")
        self.assertIsNone(evaluated.winner)

    def test_reserve_met_outcome(self):
        """If highest bid meets or exceeds reserve ($1,200), auction seals as sold."""
        AuctionEngine.place_bid(self.auction.id, self.buyer1, Decimal("1300.00"))
        evaluated = AuctionEngine.evaluate_and_close(self.auction.id)
        self.assertEqual(evaluated.status, "sold")
        self.assertEqual(evaluated.winner, self.buyer1)
        self.assertEqual(evaluated.winning_bid_amount, Decimal("1300.00"))

    def test_live_feed_state_masking(self):
        """Live feed provides masked usernames for public privacy."""
        AuctionEngine.place_bid(self.auction.id, self.buyer1, Decimal("500.00"))
        state = AuctionEngine.get_live_state(self.auction.id, current_user=self.buyer1)
        self.assertTrue(state["success"])
        self.assertEqual(state["total_bids"], 1)
        self.assertTrue(state["user_is_winning"])
        # buyer_one masked should be b***e
        self.assertEqual(state["recent_bids"][0]["bidder_masked"], "b***e")
