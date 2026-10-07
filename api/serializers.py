from rest_framework import serializers
from .models import Item


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = [
            "id",
            "title",
            "description",
            "quantity",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

class SendRegistrationOTPSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    mobile_number = serializers.CharField(max_length=20)

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

class CompleteProfileSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    mobile_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_entity_type = serializers.ChoiceField(choices=(("INDIVIDUAL", "Individual"), ("COMPANY", "Company/Business")), required=False)
    company_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    business_location = serializers.CharField(max_length=255, required=False, allow_blank=True)
    business_address = serializers.CharField(required=False, allow_blank=True)
    tax_registration_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    business_type = serializers.CharField(max_length=100, required=False, allow_blank=True)
    user_type = serializers.ChoiceField(choices=(("BUYER", "Buyer"), ("SELLER", "Seller"), ("BOTH", "Both")), required=False)
    category_interested = serializers.JSONField(required=False, default=list)

class SendLoginOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

from AdminApp.models import PartnershipEnquiry, ContactUsEnquiry, AnalyticsViewLog, PageViewLog, Product, Lot

class PageViewLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageViewLog
        fields = [
            'id',
            'entity_type',
            'entity_id',
            'entity_slug',
            'path',
            'ip_address',
            'user_agent',
            'referrer',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

class AnalyticsViewLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = AnalyticsViewLog
        fields = [
            'id',
            'entity_type',
            'entity_id',
            'entity_slug',
            'path',
            'referrer',
            'user_agent',
            'ip_address',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

class ContactUsEnquirySerializer(serializers.ModelSerializer):

    fullName = serializers.CharField(source='full_name', required=False)
    enquiryType = serializers.CharField(source='enquiry_type', required=False)

    class Meta:
        model = ContactUsEnquiry
        fields = [
            'id',
            'full_name',
            'fullName',
            'email',
            'phone',
            'enquiry_type',
            'enquiryType',
            'message',
            'status',
            'is_blocked',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class PartnershipEnquirySerializer(serializers.ModelSerializer):
    location = serializers.CharField(write_only=True, required=False, allow_blank=True)
    interest = serializers.CharField(write_only=True, required=False, allow_blank=True)
    message = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = PartnershipEnquiry
        fields = [
            'id',
            'name', 
            'email', 
            'business_location', 
            'partnership_interest', 
            'subject', 
            'collaboration_details',
            'location',
            'interest',
            'message',
            'status',
            'created_at'
        ]
        read_only_fields = ['id', 'status', 'created_at']

    def to_internal_value(self, data):
        data_copy = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'location' in data_copy and 'business_location' not in data_copy:
            data_copy['business_location'] = data_copy.get('location', '')
        if 'interest' in data_copy and 'partnership_interest' not in data_copy:
            data_copy['partnership_interest'] = data_copy.get('interest', '')
        if 'message' in data_copy and 'collaboration_details' not in data_copy:
            data_copy['collaboration_details'] = data_copy.get('message', '')
        return super().to_internal_value(data_copy)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        exclude = ['is_active', 'enquiry_status']
        read_only_fields = ['product_id', 'created_at', 'updated_at']

class SellerProductEnquirySerializer(ProductSerializer):
    pass

class LotSerializer(serializers.ModelSerializer):
    manifest_data = serializers.SerializerMethodField()
    vendor_id = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Lot
        fields = [
            "id",
            "vendor_id",
            "lot_number",
            "title",
            "description",
            "key_brands_included",
            "warehouse_images",
            "category_allocations",
            "condition",
            "source_type",
            "inventory_stock_age",
            "third_party_certificate_available",
            "third_party_documents",
            "inventory_location",
            "number_of_distinct_skus",
            "total_units_quantity",
            "primary_unit_type",
            "total_weight",
            "load_type",
            "shipping_size",
            "lot_size",
            "pallet_count",
            "shipping_terms",
            "currency",
            "total_est_retail_value_msrp",
            "ask_price_surplus_payout",
            "offer",
            "excluded_export_countries",
            "sale_method",
            "file",
            "file_url",
            "manifest_data",
            "enquiry_status",
            "active_status",
            "is_active",
            "views_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["lot_number", "manifest_data", "file_url", "vendor_id", "created_at", "updated_at"]

    def get_vendor_id(self, obj):
        if hasattr(obj, 'vendor') and obj.vendor:
            return getattr(obj.vendor, 'user_id', None) or f"USR-{obj.vendor.id:04d}"
        return ""

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None

    def get_manifest_data(self, obj):
        """Return parsed Excel manifest rows stored in raw_data."""
        if not isinstance(obj.raw_data, dict):
            return []
        for key in ("manifest_items", "parsed_items", "preview_items", "products_list", "products"):
            rows = obj.raw_data.get(key)
            if rows and isinstance(rows, list):
                return rows
        return []


# Alias kept for backward-compatibility with views that import LotBatchEnquirySerializer
LotBatchEnquirySerializer = LotSerializer


from AdminApp.models import VendorNotification
from django.utils.timesince import timesince

class VendorNotificationSerializer(serializers.ModelSerializer):
    vendor_id = serializers.SerializerMethodField()
    created_at_formatted = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = VendorNotification
        fields = [
            "id",
            "vendor_id",
            "title",
            "message",
            "notification_type",
            "action_url",
            "is_read",
            "created_at",
            "created_at_formatted",
            "time_ago",
        ]
        read_only_fields = ["id", "vendor_id", "created_at", "created_at_formatted", "time_ago"]

    def get_vendor_id(self, obj):
        if obj.vendor:
            return obj.vendor.vendor_id or f"USR-{obj.vendor.id:04d}"
        return ""

    def get_created_at_formatted(self, obj):
        if obj.created_at:
            return obj.created_at.strftime("%b %d, %Y %I:%M %p")
        return ""

    def get_time_ago(self, obj):
        if obj.created_at:
            return f"{timesince(obj.created_at)} ago"
        return ""


