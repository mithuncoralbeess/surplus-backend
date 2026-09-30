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
    class Meta:
        model = PartnershipEnquiry
        fields = [
            'name', 
            'email', 
            'business_location', 
            'partnership_interest', 
            'subject', 
            'collaboration_details'
        ]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        exclude = ['is_active', 'enquiry_status']
        read_only_fields = ['product_id', 'created_at', 'updated_at']

class SellerProductEnquirySerializer(ProductSerializer):
    pass

class LotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lot
        exclude = ['active_status', 'enquiry_status']
        read_only_fields = ['lot_number', 'created_at', 'updated_at']

class LotBatchEnquirySerializer(LotSerializer):
    pass

