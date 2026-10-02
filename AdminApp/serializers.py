from rest_framework import serializers
from .models import AdminDetails, VendorDetails


class AdminRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    firstname = serializers.CharField(max_length=150, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    lastname = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    confirm_password = serializers.CharField(write_only=True, required=False)
    confirm_pass = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)

    def validate(self, attrs):
        username = attrs.get("username")
        email = attrs.get("email")

        # Resolve password
        password = attrs.get("confirm_password") or attrs.get("confirm_pass") or attrs.get("password")
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})
        attrs["resolved_password"] = password

        # Resolve names
        attrs["resolved_first_name"] = attrs.get("firstname") or attrs.get("first_name", "")
        attrs["resolved_last_name"] = attrs.get("lastname") or attrs.get("last_name", "")

        if AdminDetails.objects.filter(username=username).exists():
            raise serializers.ValidationError({"username": "Username is already taken."})
        if AdminDetails.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Email is already registered."})

        return attrs


class AdminLoginSerializer(serializers.Serializer):
    user_email = serializers.CharField(required=False)
    email = serializers.CharField(required=False)
    username = serializers.CharField(required=False)
    user_pass = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)

    def validate(self, attrs):
        identifier = attrs.get("user_email") or attrs.get("email") or attrs.get("username")
        password = attrs.get("user_pass") or attrs.get("password")

        if not identifier:
            raise serializers.ValidationError({"email": "Email or Username is required."})
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})

        attrs["resolved_identifier"] = identifier
        attrs["resolved_password"] = password
        return attrs


class AdminDetailsSerializer(serializers.ModelSerializer):
    admin_id = serializers.CharField(read_only=True)
    formatted_id = serializers.CharField(read_only=True)

    class Meta:
        model = AdminDetails
        fields = [
            "id",
            "admin_id",
            "formatted_id",
            "username",
            "email",
            "account_type",
            "status",
            "session_version",
            "web_is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "admin_id", "formatted_id", "session_version", "created_at", "updated_at"]


class VendorRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    mobile_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    confirm_password = serializers.CharField(write_only=True, required=False)
    confirm_pass = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False)

    def validate(self, attrs):
        username = attrs.get("username")
        email = attrs.get("email")

        # Resolve password
        password = attrs.get("confirm_password") or attrs.get("confirm_pass") or attrs.get("password")
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})
        attrs["resolved_password"] = password

        attrs["resolved_mobile_number"] = attrs.get("mobile_number", "")

        if VendorDetails.objects.filter(username=username).exists():
            raise serializers.ValidationError({"username": "Username is already taken."})
        if VendorDetails.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Email is already registered."})

        return attrs


class VendorDetailsSerializer(serializers.ModelSerializer):
    vendor_id = serializers.CharField(read_only=True)
    formatted_id = serializers.CharField(read_only=True)

    class Meta:
        model = VendorDetails
        fields = [
            "id",
            "vendor_id",
            "formatted_id",
            "username",
            "email",
            "full_name",
            "mobile_number",
            "company_name",
            "user_type",
            "status",
            "session_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "vendor_id", "formatted_id", "session_version", "created_at", "updated_at"]



class SuperAdminPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SuperAdminVerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs.get("new_password") != attrs.get("confirm_password"):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs


class ContentPageSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    seo = serializers.SerializerMethodField()

    class Meta:
        from .models import ContentPage
        model = ContentPage
        fields = [
            "id",
            "title",
            "slug",
            "category",
            "content",
            "components",
            "seo",
            "status",
            "is_active",
            "show_in_header",
            "show_in_footer",
            "sort_order",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by_name"]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.username
        return "System Admin"

    def get_seo(self, obj):
        return {
            "focus_keyphrase": obj.focus_keyphrase or "",
            "meta_title": obj.meta_title or obj.title or "",
            "meta_description": obj.meta_description or "",
            "meta_keywords": obj.meta_keywords or "",
            "canonical_url": obj.canonical_url or f"https://surplus.com/{obj.slug}/",
            "robots_index": obj.robots_index or "index",
            "robots_follow": obj.robots_follow or "follow",
            "robots_advanced": obj.robots_advanced or "",
            "og_title": obj.og_title or "",
            "og_description": obj.og_description or "",
            "og_image": obj.og_image or "",
            "twitter_title": obj.twitter_title or "",
            "twitter_description": obj.twitter_description or "",
            "twitter_image": obj.twitter_image or "",
            "schema_type": obj.schema_type or "WebPage",
            "structured_data": obj.structured_data or {},
        }

    def to_internal_value(self, data):
        if isinstance(data, dict) and "seo" in data and isinstance(data["seo"], dict):
            data = data.copy()
            seo_dict = data.pop("seo")
            for key, val in seo_dict.items():
                if key not in data:
                    data[key] = val
        return super().to_internal_value(data)




class SellerProductEnquirySerializer(serializers.ModelSerializer):
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        from .models import SellerProductEnquiry
        model = SellerProductEnquiry
        fields = [
            "id",
            "product_id",
            "status",
            "raw_data",
            "created_at",
            "created_at_formatted",
            "updated_at",
        ]
        read_only_fields = ["id", "product_id", "created_at", "created_at_formatted", "updated_at"]

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime("%b %d, %Y %H:%M") if obj.created_at else ""


class LotSerializer(serializers.ModelSerializer):
    created_at_formatted = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()

    class Meta:
        from .models import Lot
        model = Lot
        fields = [
            "id",
            "lot_number",
            "title",
            "description",
            "category_name",
            "inventory_location",
            "total_price",
            "currency",
            "reason_to_sell",
            "file",
            "file_url",
            "products",
            "enquiry_status",
            "active_status",
            "is_active",
            "raw_data",
            "created_at",
            "created_at_formatted",
            "updated_at",
        ]
        read_only_fields = ["id", "lot_number", "file_url", "created_at", "created_at_formatted", "updated_at"]

    def get_products(self, obj):
        if isinstance(obj.raw_data, dict):
            return obj.raw_data.get("products", []) or obj.raw_data.get("manifest_items", [])
        return []

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime("%b %d, %Y %H:%M") if obj.created_at else ""

    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url
        return None


class LotBatchEnquirySerializer(LotSerializer):
    """
    Alias serializer for backward compatibility.
    """
    pass

