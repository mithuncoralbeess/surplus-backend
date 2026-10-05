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
    profile_completion_percentage = serializers.IntegerField(read_only=True)
    is_profile_complete = serializers.BooleanField(read_only=True)
    missing_fields_labels = serializers.SerializerMethodField()

    def get_missing_fields_labels(self, obj):
        details = obj.get_profile_completion_details()
        return details.get("missing_fields_labels", [])

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
            "account_entity_type",
            "business_location",
            "business_address",
            "tax_registration_number",
            "business_type",
            "category_interested",
            "user_type",
            "status",
            "session_version",
            "profile_completion_percentage",
            "is_profile_complete",
            "missing_fields_labels",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "vendor_id", "formatted_id", "session_version",
            "profile_completion_percentage", "is_profile_complete",
            "missing_fields_labels", "created_at", "updated_at"
        ]



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
    vendor_id = serializers.SerializerMethodField()
    listing_title = serializers.CharField(source="title", required=False, allow_blank=True)
    lot_description_and_notes = serializers.CharField(source="description", required=False, allow_blank=True)
    manifest_file = serializers.JSONField(source="manifest_file_info", required=False)

    class Meta:
        from .models import Lot
        model = Lot
        fields = [
            "id",
            "vendor_id",
            "lot_number",
            "title",
            "listing_title",
            "description",
            "lot_description_and_notes",
            "key_brands_included",
            "product_and_warehouse_images_or_videos",
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
            "category_name",
            "total_price",
            "currency",
            "total_est_retail_value_msrp",
            "ask_price_surplus_payout",
            "offer",
            "allow_counter_offers",
            "excluded_export_countries",
            "sale_method",
            "manifest_file",
            "manifest_file_info",
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

    def get_vendor_id(self, obj):
        if hasattr(obj, 'formatted_vendor_id') and obj.formatted_vendor_id:
            return obj.formatted_vendor_id
        if hasattr(obj, 'vendor') and obj.vendor:
            return obj.vendor.user_id
        return ""

    def get_products(self, obj):
        if isinstance(obj.raw_data, dict):
            return obj.raw_data.get("products", []) or obj.raw_data.get("manifest_items", [])
        return []

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime("%b %d, %Y %H:%M") if obj.created_at else ""

    def get_file_url(self, obj):
        if hasattr(obj, 'file') and obj.file:
            return obj.file.url
        return None

    def to_internal_value(self, data):
        import json
        import re
        data_copy = data.copy() if hasattr(data, 'copy') else dict(data)

        def _parse_num(val):
            if val is None or val == "":
                return "0.00"
            if isinstance(val, (int, float)):
                return f"{val:.2f}"
            if isinstance(val, str):
                cleaned = re.sub(r'[^\d.-]', '', val.strip())
                if cleaned and cleaned != '.':
                    try:
                        return f"{float(cleaned):.2f}"
                    except Exception:
                        pass
            return "0.00"

        def _parse_int(val):
            if isinstance(val, int):
                return val
            if isinstance(val, float):
                return int(val)
            if isinstance(val, str):
                cleaned = re.sub(r'[^\d-]', '', val.strip())
                if cleaned:
                    try:
                        return int(cleaned)
                    except Exception:
                        pass
            return 0

        # Sanitize null/None values to safe default primitive types
        str_fields = [
            'title', 'description', 'listing_title', 'lot_description_and_notes',
            'key_brands_included', 'condition', 'source_type', 'inventory_stock_age',
            'primary_unit_type', 'total_weight', 'load_type', 'shipping_size',
            'lot_size', 'shipping_terms', 'currency', 'offer', 'sale_method',
            'reason_to_sell', 'category_name', 'inventory_location'
        ]
        for field in str_fields:
            if field in data_copy and data_copy[field] is None:
                data_copy[field] = ""

        json_list_fields = [
            'category_allocations',
            'product_and_warehouse_images_or_videos',
            'third_party_documents',
            'excluded_export_countries',
        ]
        for field in json_list_fields:
            if field in data_copy and data_copy[field] is None:
                data_copy[field] = []

        json_dict_fields = ['manifest_file_info', 'manifest_file']
        for field in json_dict_fields:
            if field in data_copy and data_copy[field] is None:
                data_copy[field] = {}

        for field in ['third_party_certificate_available', 'allow_counter_offers']:
            if field in data_copy and data_copy[field] is None:
                data_copy[field] = False

        for field in ['number_of_distinct_skus', 'total_units_quantity', 'pallet_count']:
            if field in data_copy and data_copy[field] is None:
                data_copy[field] = 0

        for field in ['total_est_retail_value_msrp', 'ask_price_surplus_payout', 'total_price']:
            if field in data_copy and data_copy[field] is None:
                data_copy[field] = 0.0

        # Map listing_title / aliases to title
        for t_alias in ['listing_title', 'lot_title', 'name', 'title']:
            if t_alias in data_copy and data_copy[t_alias] and ('title' not in data_copy or not data_copy.get('title')):
                data_copy['title'] = str(data_copy[t_alias])

        # Map lot_description_and_notes / aliases to description
        for d_alias in ['lot_description_and_notes', 'notes', 'lot_notes']:
            if d_alias in data_copy and data_copy[d_alias] and ('description' not in data_copy or not data_copy.get('description')):
                data_copy['description'] = str(data_copy[d_alias])

        # Handle manifest_file / manifest aliases (could be dict, stringified JSON, or uploaded file object)
        for mf_key in ['manifest_file', 'manifest', 'manifest_file_info']:
            if mf_key in data_copy:
                mf = data_copy[mf_key]
                if hasattr(mf, 'read'):
                    if 'file' not in data_copy or not data_copy.get('file'):
                        data_copy['file'] = mf
                elif isinstance(mf, str):
                    try:
                        parsed = json.loads(mf)
                        if isinstance(parsed, dict) and ('manifest_file_info' not in data_copy or not data_copy.get('manifest_file_info')):
                            data_copy['manifest_file_info'] = parsed
                    except Exception:
                        pass
                elif isinstance(mf, dict) and ('manifest_file_info' not in data_copy or not data_copy.get('manifest_file_info')):
                    data_copy['manifest_file_info'] = mf

        # Fallback default title if still empty
        if 'title' not in data_copy or not str(data_copy.get('title', '')).strip():
            manifest_info = data_copy.get('manifest_file_info', {})
            fname = manifest_info.get('file_name', '') if isinstance(manifest_info, dict) else ''
            if fname:
                data_copy['title'] = f"Surplus Lot ({fname})"
            else:
                data_copy['title'] = "Surplus Lot Inventory Package"

        # Clean and parse decimal fields with alias support
        price_aliases = ['ask_price_surplus_payout', 'asking_price', 'ask_price', 'price']
        parsed_payout = None
        for alias in price_aliases:
            if alias in data_copy and data_copy[alias] not in (None, ""):
                parsed_payout = _parse_num(data_copy[alias])
                break
        data_copy['ask_price_surplus_payout'] = parsed_payout if parsed_payout is not None else "0.00"

        msrp_aliases = ['total_est_retail_value_msrp', 'total_retail_value', 'retail_value', 'msrp']
        parsed_msrp = None
        for alias in msrp_aliases:
            if alias in data_copy and data_copy[alias] not in (None, ""):
                parsed_msrp = _parse_num(data_copy[alias])
                break
        data_copy['total_est_retail_value_msrp'] = parsed_msrp if parsed_msrp is not None else "0.00"

        total_price_aliases = ['total_price', 'ask_price_surplus_payout', 'asking_price', 'ask_price', 'price']
        parsed_tot_price = None
        for alias in total_price_aliases:
            if alias in data_copy and data_copy[alias] not in (None, ""):
                parsed_tot_price = _parse_num(data_copy[alias])
                break
        data_copy['total_price'] = parsed_tot_price if parsed_tot_price is not None else "0.00"

        # Map quantity / SKUs / pallets aliases using robust integer cleaner
        for q_alias in ['total_units_quantity', 'total_units', 'total_quantity', 'quantity']:
            if q_alias in data_copy and data_copy[q_alias] is not None and data_copy[q_alias] != "":
                data_copy['total_units_quantity'] = _parse_int(data_copy[q_alias])

        for sku_alias in ['number_of_distinct_skus', 'distinct_skus', 'skus_count']:
            if sku_alias in data_copy and data_copy[sku_alias] is not None and data_copy[sku_alias] != "":
                data_copy['number_of_distinct_skus'] = _parse_int(data_copy[sku_alias])

        for pal_alias in ['pallet_count', 'pallets', 'no_of_pallets']:
            if pal_alias in data_copy and data_copy[pal_alias] is not None and data_copy[pal_alias] != "":
                data_copy['pallet_count'] = _parse_int(data_copy[pal_alias])

        # Parse stringified JSON fields if passed from FormData
        for field in json_list_fields + ['manifest_file_info']:
            if field in data_copy and isinstance(data_copy[field], str):
                val_str = data_copy[field].strip()
                if val_str:
                    try:
                        data_copy[field] = json.loads(val_str)
                    except Exception:
                        pass

        # Parse boolean fields if passed as string "true"/"false"
        for field in ['third_party_certificate_available', 'allow_counter_offers']:
            if field in data_copy:
                val = data_copy[field]
                if isinstance(val, str):
                    data_copy[field] = val.lower() in ('true', '1', 'yes')

        return super().to_internal_value(data_copy)


class LotBatchEnquirySerializer(LotSerializer):
    """
    Alias serializer for backward compatibility.
    """
    pass


