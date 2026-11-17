"""
Serializers for Reports Module.
Strictly conforms to the Back-End Reports API Specification response shapes.
"""

from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers

from AdminApp.models import (
    Auction,
    Lot,
    LotProduct,
    Product,
    RfqEnquiry,
    RfqEnquiryItem,
    VendorDetails,
)


class ProductReportSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="product_name", read_only=True)
    category = serializers.SerializerMethodField()
    subcategory = serializers.SerializerMethodField()
    brand = serializers.CharField(source="brand_name", read_only=True)
    qty = serializers.IntegerField(source="quantity", read_only=True)
    buyer_price = serializers.DecimalField(source="current_price", max_digits=12, decimal_places=2, read_only=True)
    status = serializers.CharField(source="enquiry_status", read_only=True)
    vendor = serializers.SerializerMethodField()
    age_days = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "product_id",
            "name",
            "category",
            "subcategory",
            "brand",
            "qty",
            "buyer_price",
            "msrp",
            "offer",
            "currency",
            "inventory_country",
            "age_days",
            "status",
            "is_active",
            "vendor",
            "images",
            "created_at",
            "date_approved",
        ]

    def get_category(self, obj):
        return obj.category.name if obj.category else None

    def get_subcategory(self, obj):
        return obj.subcategory.name if obj.subcategory else None

    def get_vendor(self, obj):
        if not obj.vendor:
            return None
        return obj.vendor.company_name or obj.vendor.full_name or obj.vendor.username

    def get_age_days(self, obj):
        if not obj.created_at:
            return 0
        diff = timezone.now() - obj.created_at
        return max(0, diff.days)

    def get_images(self, obj):
        images_rel = getattr(obj, "images", None)
        if not images_rel:
            return []
        try:
            return [
                {
                    "id": img.id,
                    "url": img.image.url if getattr(img, "image", None) else "",
                    "is_primary": getattr(img, "is_primary", False),
                }
                for img in images_rel.all()[:4]
            ]
        except Exception:
            return []


class LotReportSerializer(serializers.ModelSerializer):
    pct_of_retail = serializers.SerializerMethodField()
    vendor = serializers.SerializerMethodField()
    age_days = serializers.SerializerMethodField()

    class Meta:
        model = Lot
        fields = [
            "id",
            "lot_number",
            "title",
            "condition",
            "source_type",
            "sale_method",
            "load_type",
            "inventory_country",
            "currency",
            "total_est_retail_value_msrp",
            "ask_price_surplus_payout",
            "pct_of_retail",
            "total_units_quantity",
            "number_of_distinct_skus",
            "pallet_count",
            "inventory_stock_age",
            "vendor",
            "enquiry_status",
            "is_active",
            "age_days",
            "created_at",
        ]

    def get_pct_of_retail(self, obj):
        msrp = obj.total_est_retail_value_msrp
        ask = obj.ask_price_surplus_payout
        if msrp and msrp > 0 and ask is not None:
            try:
                return round(float(ask / msrp) * 100.0, 1)
            except Exception:
                return 0.0
        return 0.0

    def get_vendor(self, obj):
        if not obj.vendor:
            return None
        return obj.vendor.company_name or obj.vendor.full_name or obj.vendor.username

    def get_age_days(self, obj):
        if not obj.created_at:
            return 0
        return max(0, (timezone.now() - obj.created_at).days)


class LotProductDrilldownSerializer(serializers.ModelSerializer):
    class Meta:
        model = LotProduct
        fields = [
            "id",
            "lot_id",
            "product_id",
            "product_name",
            "quantity",
            "condition",
            "raw_data",
            "created_at",
        ]


class UserReportSerializer(serializers.ModelSerializer):
    entity = serializers.CharField(source="account_entity_type", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = VendorDetails
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "mobile_number",
            "company_name",
            "user_type",
            "entity",
            "country",
            "business_location",
            "business_type",
            "category_interested",
            "status",
            "created_at",
        ]

    def get_status(self, obj):
        return "active" if obj.status else "inactive"


class RfqReportSerializer(serializers.ModelSerializer):
    buyer = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = RfqEnquiry
        fields = [
            "id",
            "reference",
            "buyer",
            "company_name",
            "contact_person",
            "email",
            "phone",
            "country",
            "destination_port",
            "incoterm",
            "payment_method",
            "estimated_value",
            "currency",
            "total_units",
            "item_count",
            "status",
            "created_at",
        ]

    def get_buyer(self, obj):
        if obj.buyer:
            return obj.buyer.company_name or obj.buyer.full_name or obj.buyer.username
        return obj.company_name or "Anonymous"


class RfqItemDrilldownSerializer(serializers.ModelSerializer):
    class Meta:
        model = RfqEnquiryItem
        fields = [
            "id",
            "rfq_id",
            "item_type",
            "title",
            "sku",
            "category",
            "quantity",
            "unit_price",
            "target_price",
            "notes",
            "created_at",
        ]


# Alias for compatibility
RfqEnquiryItemSerializer = RfqItemDrilldownSerializer


class AuctionReportSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()
    vendor = serializers.SerializerMethodField()

    class Meta:
        model = Auction
        fields = [
            "id",
            "auction_id",
            "title",
            "item_type",
            "category",
            "vendor",
            "currency",
            "starting_bid",
            "current_bid",
            "reserve_price",
            "bid_increment",
            "buy_now_price",
            "total_bids",
            "views_count",
            "status",
            "start_time",
            "end_time",
            "created_at",
        ]

    def get_category(self, obj):
        return obj.category.name if obj.category else None

    def get_vendor(self, obj):
        if not obj.vendor:
            return None
        return obj.vendor.company_name or obj.vendor.full_name or obj.vendor.username
