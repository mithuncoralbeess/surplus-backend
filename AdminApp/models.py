import uuid
import hashlib
import hmac
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from datetime import timedelta
from pgvector.django import VectorField, HnswIndex


class AdminDetails(models.Model):
    ACCOUNT_TYPE_CHOICES = (
        ("SuperAdmin", "SuperAdmin"),
        ("Admin", "Admin"),
        ("XLSXAdmin", "XLSX Admin"),
    )

    username = models.CharField(max_length=150, unique=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    pass_word = models.CharField(
        max_length=255,
        help_text="Salted SHA-256 hash string (<hash>:<salt>)"
    )
    account_type = models.CharField(
        max_length=50,
        choices=ACCOUNT_TYPE_CHOICES,
        default="Admin",
        db_index=True
    )
    status = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Active/inactive toggle"
    )
    session_version = models.PositiveIntegerField(
        default=1,
        help_text="Incrementing integer used to invalidate active sessions during password reset"
    )
    web_is_active = models.CharField(
        max_length=50,
        default="live",
        help_text="Controls global site maintenance state"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Admin Detail"
        verbose_name_plural = "Admin Details"
        db_table = "admin_details"
        indexes = [
            models.Index(fields=["email", "status"], name="idx_admin_email_status"),
            models.Index(fields=["account_type", "status"], name="idx_admin_role_status"),
        ]

    def __str__(self):
        return f"{self.username} ({self.account_type})"

    @staticmethod
    def hash_password(raw_password: str) -> str:
        """
        Hashes password using Django's standard password hasher (PBKDF2/Argon2).
        """
        from django.contrib.auth.hashers import make_password
        return make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """
        Verifies password against stored hash using constant-time comparison.
        Supports standard PBKDF2 and legacy salted SHA-256 (<hash>:<salt>).
        Auto-upgrades legacy salted SHA-256 hashes to PBKDF2 upon successful check.
        """
        from django.contrib.auth.hashers import check_password as django_check_password, make_password
        if not self.pass_word:
            return False

        # If it's a legacy salted SHA-256 hash (<hash>:<salt>)
        if ":" in self.pass_word and not self.pass_word.startswith(("pbkdf2_", "argon2", "bcrypt")):
            try:
                stored_hash, salt = self.pass_word.split(":", 1)
                computed_hash = hashlib.sha256(salt.encode() + raw_password.encode()).hexdigest()
                if hmac.compare_digest(computed_hash, stored_hash):
                    # Auto-upgrade to PBKDF2
                    self.pass_word = make_password(raw_password)
                    self.save(update_fields=["pass_word"])
                    return True
            except (ValueError, AttributeError):
                pass

        return django_check_password(raw_password, self.pass_word)

    def set_password(self, raw_password: str):
        self.pass_word = self.hash_password(raw_password)

    def get_salt(self) -> str:
        return self.pass_word.split(":")[1] if ":" in self.pass_word else ""

    @property
    def admin_id(self):
        return f"ADM-{self.id:04d}" if self.id else ""

    @property
    def formatted_id(self):
        return self.admin_id


class VendorDetails(models.Model):
    USER_TYPE_CHOICES = (
        ("BUYER", "Buyer"),
        ("SELLER", "Seller"),
        ("BOTH", "Both"),
    )
    
    username = models.CharField(max_length=150, unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(unique=True, db_index=True)
    mobile_number = models.CharField(max_length=20, blank=True, default="")
    
    ENTITY_TYPE_CHOICES = (
        ("INDIVIDUAL", "Individual"),
        ("COMPANY", "Company/Business"),
    )
    account_entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES, default="COMPANY")
    
    company_name = models.CharField(max_length=255, blank=True, default="")
    business_location = models.CharField(max_length=255, blank=True, default="")
    business_address = models.TextField(blank=True, default="")
    tax_registration_number = models.CharField(max_length=100, blank=True, default="")
    business_type = models.CharField(max_length=100, blank=True, default="")
    category_interested = models.JSONField(default=list, blank=True, help_text="Interested categories (supports 1 or more categories)")
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="BUYER")

    @property
    def category_interested_list(self) -> list:
        """
        Returns interested categories as a list of strings (supports 1 or more categories).
        """
        if isinstance(self.category_interested, list):
            return self.category_interested
        if isinstance(self.category_interested, str) and self.category_interested:
            return [c.strip() for c in self.category_interested.split(",") if c.strip()]
        return []

    @property
    def vendor_id(self):
        return f"USR-{self.id:04d}" if self.id else ""

    @property
    def user_id(self):
        return self.vendor_id

    @property
    def formatted_id(self):
        return self.vendor_id

    def get_profile_completion_details(self) -> dict:
        """
        Calculates vendor profile completion percentage, completed fields, and missing fields.
        All required profile fields must be filled for 100% completion.
        """
        required_fields = [
            ("full_name", "Full Name", bool(self.full_name and self.full_name.strip())),
            ("email", "Email Address", bool(self.email and self.email.strip())),
            ("mobile_number", "Mobile Number", bool(self.mobile_number and self.mobile_number.strip())),
            ("account_entity_type", "Account Entity Type", bool(self.account_entity_type and self.account_entity_type.strip())),
            ("business_location", "Business Location", bool(self.business_location and self.business_location.strip())),
            ("business_address", "Business Address", bool(self.business_address and self.business_address.strip())),
            ("tax_registration_number", "Tax / GST Registration Number", bool(self.tax_registration_number and self.tax_registration_number.strip())),
            ("business_type", "Business Type", bool(self.business_type and self.business_type.strip())),
            ("category_interested", "Interested Categories", bool(self.category_interested_list and len(self.category_interested_list) > 0)),
            ("user_type", "User Type", bool(self.user_type and self.user_type.strip())),
        ]

        # For COMPANY accounts, company_name is mandatory
        is_company = str(self.account_entity_type).upper() == "COMPANY"
        if is_company:
            required_fields.append(
                ("company_name", "Company Name", bool(self.company_name and self.company_name.strip()))
            )

        total_fields = len(required_fields)
        completed = [item for item in required_fields if item[2]]
        missing = [item for item in required_fields if not item[2]]

        percentage = round((len(completed) / total_fields) * 100) if total_fields else 100
        is_complete = len(missing) == 0

        return {
            "percentage": percentage,
            "is_complete": is_complete,
            "total_fields": total_fields,
            "completed_count": len(completed),
            "missing_count": len(missing),
            "completed_fields": [item[0] for item in completed],
            "missing_fields": [item[0] for item in missing],
            "missing_fields_labels": [item[1] for item in missing],
        }

    @property
    def profile_completion_percentage(self) -> int:
        return self.get_profile_completion_details()["percentage"]

    @property
    def is_profile_complete(self) -> bool:
        return self.get_profile_completion_details()["is_complete"]
    
    pass_word = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Salted SHA-256 hash string (<hash>:<salt>)"
    )
    status = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Active/inactive toggle"
    )
    session_version = models.PositiveIntegerField(
        default=1,
        help_text="Incrementing integer used to invalidate active sessions during password reset"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vendor Detail"
        verbose_name_plural = "Vendor Details"
        db_table = "vendor_details"
        indexes = [
            models.Index(fields=["email", "status"], name="idx_vendor_email_status"),
        ]

    def __str__(self):
        return f"{self.username} (Vendor)"

    @staticmethod
    def hash_password(raw_password: str) -> str:
        """
        Hashes password using Django's standard password hasher (PBKDF2/Argon2).
        """
        from django.contrib.auth.hashers import make_password
        return make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """
        Verifies raw_password against stored hash (PBKDF2 with legacy SHA-256 fallback).
        """
        from django.contrib.auth.hashers import check_password as django_check_password, make_password
        if not self.pass_word:
            return False

        if ":" in self.pass_word and not self.pass_word.startswith(("pbkdf2_", "argon2", "bcrypt")):
            try:
                stored_hash, salt = self.pass_word.split(":", 1)
                computed_hash = hashlib.sha256(salt.encode() + raw_password.encode()).hexdigest()
                if hmac.compare_digest(computed_hash, stored_hash):
                    self.pass_word = make_password(raw_password)
                    self.save(update_fields=["pass_word"])
                    return True
            except (ValueError, AttributeError):
                pass

        return django_check_password(raw_password, self.pass_word)

    def get_salt(self) -> str:
        if not self.pass_word:
            return ""
        return self.pass_word.split(":")[1] if ":" in self.pass_word else ""

    def set_password(self, raw_password: str):
        self.pass_word = self.hash_password(raw_password)


class VendorOTP(models.Model):
    email = models.EmailField(db_index=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)
    vendor = models.ForeignKey(
        VendorDetails,
        on_delete=models.CASCADE,
        related_name="login_otps",
        null=True,
        blank=True
    )
    
    # Store registration info temporarily if they are not yet a vendor
    registration_data = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "Vendor OTP"
        verbose_name_plural = "Vendor OTPs"
        db_table = "vendor_otps"
        ordering = ["-created_at"]

    def is_valid(self):
        # 10 minute expiration
        from django.utils import timezone
        import datetime
        return not self.is_used and self.created_at >= timezone.now() - datetime.timedelta(minutes=10)

    def __str__(self):
        return f"{self.email} - {self.otp}"


class AdminPasswordResetOTP(models.Model):
    admin = models.ForeignKey(
        AdminDetails,
        on_delete=models.CASCADE,
        related_name="password_otps"
    )
    email = models.EmailField(db_index=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_used = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = "Admin Password Reset OTP"
        verbose_name_plural = "Admin Password Reset OTPs"
        db_table = "admin_password_reset_otp"
        indexes = [
            models.Index(fields=["admin", "is_used", "created_at"], name="idx_otp_validation"),
            models.Index(fields=["email", "is_used"], name="idx_otp_email_used"),
        ]

    def is_valid(self) -> bool:
        """
        OTP is valid if not used and within 10 minutes window.
        """
        if self.is_used:
            return False
        expiry_time = self.created_at + timedelta(minutes=10)
        return timezone.now() <= expiry_time

    def __str__(self):
        return f"OTP for {self.email} ({'Valid' if self.is_valid() else 'Expired/Used'})"


class ContentPage(models.Model):
    STATUS_CHOICES = (
        ("published", "Published"),
        ("draft", "Draft"),
    )

    CATEGORY_CHOICES = (
        ("General", "General"),
        ("Policy", "Policy & Legal"),
        ("Information", "Information & About"),
        ("Help", "Help & Support"),
        ("Custom", "Custom Landing"),
    )

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES, default="General", db_index=True)
    content = models.TextField(blank=True, default="", help_text="Fallback HTML / Markdown page content")
    components = models.JSONField(default=list, blank=True, help_text="Structured dynamic component blocks (Strapi-style Dynamic Zone / Meta Boxes)")
    
    # Core Yoast SEO & Meta Tags
    focus_keyphrase = models.CharField(max_length=255, blank=True, default="", help_text="Main target search keyword")
    meta_title = models.CharField(max_length=255, blank=True, default="")
    meta_description = models.TextField(blank=True, default="")
    meta_keywords = models.CharField(max_length=255, blank=True, default="")
    canonical_url = models.CharField(max_length=500, blank=True, default="", help_text="Canonical URL tag")
    
    # Advanced Robots Control
    robots_index = models.CharField(max_length=20, default="index", choices=(("index", "Index"), ("noindex", "Noindex")))
    robots_follow = models.CharField(max_length=20, default="follow", choices=(("follow", "Follow"), ("nofollow", "Nofollow")))
    robots_advanced = models.CharField(max_length=100, blank=True, default="", help_text="e.g. noarchive, nosnippet, noimageindex")

    # Social Media / Open Graph & Twitter Cards
    og_title = models.CharField(max_length=255, blank=True, default="")
    og_description = models.TextField(blank=True, default="")
    og_image = models.CharField(max_length=500, blank=True, default="")
    twitter_title = models.CharField(max_length=255, blank=True, default="")
    twitter_description = models.TextField(blank=True, default="")
    twitter_image = models.CharField(max_length=500, blank=True, default="")
    
    # Structured Data & Schema
    schema_type = models.CharField(max_length=100, default="WebPage")
    structured_data = models.TextField(blank=True, default="", help_text="Custom JSON-LD schema or custom meta tags")

    # Publishing & Placement
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="published", db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    show_in_header = models.BooleanField(default=False)
    show_in_footer = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        AdminDetails,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_pages"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Content Page"
        verbose_name_plural = "Content Pages"
        db_table = "content_pages"
        ordering = ["sort_order", "-updated_at"]
        indexes = [
            models.Index(fields=["slug", "status"], name="idx_page_slug_status"),
            models.Index(fields=["category", "status"], name="idx_page_cat_status"),
        ]

    def __str__(self):
        return f"{self.title} (/{self.slug}/) - {self.status}"



class SellerProductEnquiry(models.Model):
    """
    Seller individual product enquiries submitted from frontend.
    """
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("declined", "Declined"),
    )

    ACTIVE_STATUS_CHOICES = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )

    product_id = models.CharField(max_length=30, unique=True, db_index=True, editable=False)
    vendor = models.ForeignKey(VendorDetails, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_enquiries")
    
    # Explicit fields
    title = models.CharField(max_length=255, db_index=True)
    sku = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    reason_to_sell = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    brand = models.CharField(max_length=255, blank=True, default="")
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    manufacturing_country = models.CharField(max_length=100, blank=True, default="")
    manufacturing_year = models.PositiveIntegerField(null=True, blank=True)
    dimensions = models.CharField(max_length=100, blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    excluded_countries = models.JSONField(default=list, blank=True)
    warranty = models.CharField(max_length=255, blank=True, default="")
    third_party_certificate = models.FileField(upload_to="enquiries/certificates/", null=True, blank=True)
    image = models.ImageField(upload_to="enquiries/images/", null=True, blank=True)

    enquiry_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    active_status = models.CharField(max_length=20, choices=ACTIVE_STATUS_CHOICES, default="inactive", db_index=True)
    raw_data = models.JSONField(default=dict, blank=True, help_text="Flexible storage for extra fields")
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Seller Product Enquiry"
        verbose_name_plural = "Seller Product Enquiries"
        db_table = "seller_product_enquiries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["enquiry_status", "created_at"], name="idx_seller_enq_status"),
            models.Index(fields=["vendor", "created_at"], name="idx_seller_vendor_created"),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        if not is_new:
            orig = SellerProductEnquiry.objects.filter(pk=self.pk).values("enquiry_status").first()
            if orig:
                old_status = orig.get("enquiry_status")

        if not self.product_id:
            max_id = SellerProductEnquiry.objects.aggregate(max_id=models.Max("id"))["max_id"] or 0
            self.product_id = f"PRO-{(max_id + 1):05d}"
            
        super().save(*args, **kwargs)

        if not is_new and (str(old_status or '').upper() != str(self.enquiry_status).upper()):
            curr_status = str(self.enquiry_status).upper()
            target_vendor = self.vendor
            if not target_vendor and self.vendor_id:
                try:
                    target_vendor = VendorDetails.objects.filter(id=self.vendor_id).first()
                except Exception:
                    target_vendor = None

            recipient_email = None
            recipient_name = "Valued Seller"
            if target_vendor:
                recipient_email = target_vendor.email
                recipient_name = target_vendor.full_name or target_vendor.company_name or target_vendor.username or "Valued Seller"

            if not recipient_email and isinstance(self.raw_data, dict):
                recipient_email = self.raw_data.get("user_email") or self.raw_data.get("email")

            if not recipient_email and hasattr(self, '_user_email') and self._user_email:
                recipient_email = str(self._user_email).strip()

            if curr_status == 'APPROVED':
                profile_info = target_vendor.get_profile_completion_details() if target_vendor else None
                is_prof_complete = profile_info["is_complete"] if profile_info else True
                pct = profile_info["percentage"] if profile_info else 100
                missing_labels = profile_info["missing_fields_labels"] if profile_info else []

                if target_vendor:
                    try:
                        from .services import create_vendor_notification
                        if not is_prof_complete:
                            notif_title = "Listing Approved - Profile Incomplete"
                            notif_msg = (
                                f"Your lot '{self.title}' has been approved! However, your profile is only {pct}% complete. "
                                f"To list your product for public visibility, you must complete all your user details."
                            )
                        else:
                            notif_title = "Listing Approved"
                            notif_msg = f"Your lot '{self.title}' has been approved and published to the marketplace."

                        create_vendor_notification(
                            vendor=target_vendor,
                            title=notif_title,
                            message=notif_msg,
                            notification_type="LISTING",
                            action_url="/profile"
                        )
                    except Exception:
                        pass

                if recipient_email:
                    try:
                        from .services import EmailService
                        EmailService.send_product_approved_email(
                            to_email=recipient_email,
                            product=self,
                            recipient_name=recipient_name,
                            is_profile_complete=is_prof_complete,
                            profile_completion_percentage=pct,
                            missing_fields_labels=missing_labels
                        )
                    except Exception:
                        pass

            elif curr_status == 'DECLINED':
                decline_reason = getattr(self, '_decline_reason', '')
                if target_vendor:
                    try:
                        from .services import create_vendor_notification
                        msg = f"Your product '{self.title}' was not approved."
                        if decline_reason:
                            msg += f" Reason: {decline_reason}"
                        else:
                            msg += " Please review your listing specifications."
                        create_vendor_notification(
                            vendor=target_vendor,
                            title="Listing Declined",
                            message=msg,
                            notification_type="LISTING",
                            action_url="/profile"
                        )
                    except Exception:
                        pass

                if recipient_email:
                    try:
                        from .services import EmailService
                        EmailService.send_product_declined_email(
                            to_email=recipient_email,
                            product=self,
                            recipient_name=recipient_name,
                            reason=decline_reason
                        )
                    except Exception:
                        pass

    def __str__(self):
        return f"{self.product_id} - {self.enquiry_status}"


class LotBatchEnquiry(models.Model):
    """
    Lot batch enquiries submitted with .xlsx / .csv file upload.
    """
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("declined", "Declined"),
    )

    ACTIVE_STATUS_CHOICES = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )

    batch_id = models.CharField(max_length=30, unique=True, db_index=True, editable=False)
    uploaded_by = models.ForeignKey(VendorDetails, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_lots")
    file = models.FileField(upload_to="lot_enquiries/%Y/%m/", null=True, blank=True)
    
    # Explicit fields for the Lot itself
    title = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=50, default="USD")

    # Extended structured fields matching frontend lot payload
    key_brands_included = models.TextField(blank=True, default="")
    category_allocations = models.JSONField(default=list, blank=True)
    condition = models.CharField(max_length=255, blank=True, default="")
    source_type = models.CharField(max_length=255, blank=True, default="")
    inventory_stock_age = models.CharField(max_length=255, blank=True, default="")
    warehouse_images = models.JSONField(default=list, blank=True, help_text="List of Warehouse image URLs")
    videos = models.JSONField(default=list, blank=True, help_text="List of Video URLs")
    third_party_certificate_available = models.BooleanField(default=False)
    third_party_documents = models.JSONField(default=list, blank=True)
    number_of_distinct_skus = models.PositiveIntegerField(default=0, null=True, blank=True)
    total_units_quantity = models.PositiveIntegerField(default=0, null=True, blank=True)
    primary_unit_type = models.CharField(max_length=100, blank=True, default="")
    total_weight = models.CharField(max_length=100, blank=True, default="")
    load_type = models.CharField(max_length=100, blank=True, default="")
    shipping_size = models.CharField(max_length=100, blank=True, default="")
    lot_size = models.CharField(max_length=100, blank=True, default="")
    pallet_count = models.PositiveIntegerField(default=0, null=True, blank=True)
    shipping_terms = models.CharField(max_length=255, blank=True, default="")
    total_est_retail_value_msrp = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    ask_price_surplus_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    offer = models.CharField(max_length=100, blank=True, default="")
    allow_counter_offers = models.BooleanField(default=True)
    excluded_export_countries = models.JSONField(default=list, blank=True)
    sale_method = models.CharField(max_length=50, blank=True, default="offer")
    
    enquiry_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    active_status = models.CharField(max_length=20, choices=ACTIVE_STATUS_CHOICES, default="inactive", db_index=True)
    raw_data = models.JSONField(default=dict, blank=True, help_text="Flexible storage for extra lot fields")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lot Batch Enquiry"
        verbose_name_plural = "Lot Batch Enquiries"
        db_table = "lot_batch_enquiries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["enquiry_status", "created_at"], name="idx_batch_enq_status"),
            models.Index(fields=["uploaded_by", "created_at"], name="idx_batch_user_created"),
        ]

    def save(self, *args, **kwargs):
        if not self.batch_id:
            max_id = LotBatchEnquiry.objects.aggregate(max_id=models.Max("id"))["max_id"] or 0
            self.batch_id = f"BAT-{(max_id + 1):05d}"
            
        if self.enquiry_status == 'approved':
            self.active_status = 'active'
        else:
            self.active_status = 'inactive'
            
        super().save(*args, **kwargs)

    @property
    def lot_number(self):
        return self.batch_id

    @property
    def listing_title(self):
        return self.title

    @listing_title.setter
    def listing_title(self, value):
        self.title = value or ""

    @property
    def lot_description_and_notes(self):
        return self.description

    @lot_description_and_notes.setter
    def lot_description_and_notes(self, value):
        self.description = value or ""

    def __str__(self):
        return f"{self.batch_id} - {self.enquiry_status}"


class MainCategory(models.Model):
    """
    Top-level categories for products.
    """
    name = models.CharField(max_length=150, unique=True, db_index=True)
    slug = models.SlugField(max_length=150, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="categories/main/", null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Main Category"
        verbose_name_plural = "Main Categories"
        db_table = "main_categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    """
    Second-level categories that belong to a MainCategory.
    """
    main_category = models.ForeignKey(MainCategory, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=150, db_index=True)
    slug = models.SlugField(max_length=150, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="categories/sub/", null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sub Category"
        verbose_name_plural = "Sub Categories"
        db_table = "sub_categories"
        ordering = ["main_category__name", "name"]
        unique_together = ("main_category", "name")

    def __str__(self):
        return f"{self.name} (Sub of {self.main_category.name})"



class Lot(models.Model):
    """
    Unified Lot model representing both surplus lot enquiries and live marketplace listings.
    """
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("declined", "Declined"),
    )

    ACTIVE_STATUS_CHOICES = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )

    vendor = models.ForeignKey(VendorDetails, on_delete=models.SET_NULL, null=True, blank=True, related_name="lots")
    lot_number = models.CharField(max_length=30, unique=True, db_index=True, editable=False)
    title = models.CharField(max_length=255, db_index=True, blank=True, default="")
    description = models.TextField(blank=True, default="")
    
    category = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="lots")
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=50, default="USD")
    
    # Extended structured fields matching frontend lot payload
    key_brands_included = models.TextField(blank=True, default="")
    category_allocations = models.JSONField(default=list, blank=True)
    condition = models.CharField(max_length=255, blank=True, default="")
    source_type = models.CharField(max_length=255, blank=True, default="")
    inventory_stock_age = models.CharField(max_length=255, blank=True, default="")
    warehouse_images = models.JSONField(default=list, blank=True, help_text="List of Warehouse image URLs")
    videos = models.JSONField(default=list, blank=True, help_text="List of Video URLs")
    third_party_certificate_available = models.BooleanField(default=False)
    third_party_documents = models.JSONField(default=list, blank=True)
    number_of_distinct_skus = models.PositiveIntegerField(default=0, null=True, blank=True)
    total_units_quantity = models.PositiveIntegerField(default=0, null=True, blank=True)
    primary_unit_type = models.CharField(max_length=100, blank=True, default="")
    total_weight = models.CharField(max_length=100, blank=True, default="")
    load_type = models.CharField(max_length=100, blank=True, default="")
    shipping_size = models.CharField(max_length=100, blank=True, default="")
    lot_size = models.CharField(max_length=100, blank=True, default="")
    pallet_count = models.PositiveIntegerField(default=0, null=True, blank=True)
    shipping_terms = models.CharField(max_length=255, blank=True, default="")
    total_est_retail_value_msrp = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    ask_price_surplus_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, null=True, blank=True)
    offer = models.CharField(max_length=100, blank=True, default="")
    allow_counter_offers = models.BooleanField(default=True)
    excluded_export_countries = models.JSONField(default=list, blank=True)
    sale_method = models.CharField(max_length=50, blank=True, default="offer")

    file = models.FileField(upload_to="lot_enquiries/%Y/%m/", null=True, blank=True)
    enquiry_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    active_status = models.CharField(max_length=20, choices=ACTIVE_STATUS_CHOICES, default="inactive", db_index=True)
    is_active = models.BooleanField(default=False, db_index=True)
    raw_data = models.JSONField(default=dict, blank=True, help_text="Flexible storage for extra lot specifications and product manifest")
    views_count = models.PositiveIntegerField(default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lot"
        verbose_name_plural = "Lots"
        db_table = "lots"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "enquiry_status"], name="idx_lot_active_status"),
            models.Index(fields=["category", "is_active"], name="idx_lot_cat_active"),
            models.Index(fields=["vendor", "created_at"], name="idx_lot_vendor_created"),
        ]

    def save(self, *args, **kwargs):
        if not self.lot_number:
            max_id = Lot.objects.aggregate(max_id=models.Max("id"))["max_id"] or 0
            self.lot_number = f"LOT-{(max_id + 1):05d}"
            
        if self.active_status == 'active':
            self.is_active = True
        else:
            self.is_active = False

        super().save(*args, **kwargs)

    @property
    def batch_id(self):
        return self.lot_number

    @property
    def formatted_vendor_id(self):
        if self.vendor:
            return self.vendor.user_id
        if self.vendor_id:
            return f"USR-{self.vendor_id:04d}"
        return ""

    @property
    def vendor_user_id(self):
        return self.formatted_vendor_id

    def __str__(self):
        return f"{self.title or self.lot_number} ({self.lot_number}) - {self.enquiry_status}"

class LotProduct(models.Model):
    """
    Individual lot products inside a Lot.
    """
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="products", null=True, blank=True)
    enquiry = models.ForeignKey(LotBatchEnquiry, on_delete=models.CASCADE, related_name="products", null=True, blank=True)
    product_id = models.CharField(max_length=30, unique=True, db_index=True, editable=False)
    
    product_name = models.CharField(max_length=255, blank=True, default="")
    quantity = models.PositiveIntegerField(default=0)
    condition = models.CharField(max_length=255, blank=True, default="")
    
    raw_data = models.JSONField(default=dict, blank=True, help_text="Flexible storage for individual lot fields")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lot Product"
        verbose_name_plural = "Lot Products"
        db_table = "lot_products"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lot", "created_at"], name="idx_lotprod_lot_created"),
            models.Index(fields=["enquiry", "created_at"], name="idx_lotprod_enq_created"),
        ]

    def save(self, *args, **kwargs):
        if not self.product_id:
            max_id = LotProduct.objects.aggregate(max_id=models.Max("id"))["max_id"] or 0
            self.product_id = f"BLK-{(max_id + 1):05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_id} (Lot {self.lot.lot_number if self.lot else 'None'})"



class Product(models.Model):
    """
    Core Product model for single item listings and seller enquiries.
    """
    product_id = models.CharField(max_length=30, blank=True, default="", db_index=True)
    vendor = models.ForeignKey(
        VendorDetails, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="products"
    )
    product_name = models.CharField(max_length=255, db_index=True)
    
    category = models.ForeignKey(
        MainCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="products"
    )
    subcategory = models.ForeignKey(
        SubCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="products"
    )
    brand_name = models.CharField(max_length=255, blank=True, default="", db_index=True)
    model_no = models.CharField(max_length=255, blank=True, default="", db_index=True, help_text="Model No. / Part Number")
    
    manufacturing_country = models.CharField(max_length=100, blank=True, default="")
    inventory_location = models.CharField(max_length=255, blank=True, default="", help_text="Warehouse / stock location")
    manufacturing_year = models.PositiveIntegerField(null=True, blank=True)
    dimensions = models.CharField(max_length=100, blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)
    excluded_countries = models.JSONField(default=list, blank=True, help_text="List of excluded country codes")
    
    quantity = models.PositiveIntegerField(default=0, db_index=True)
    currency = models.CharField(max_length=10, default="USD")
    liquidating_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True, help_text="Liquidating Price per unit")
    msrp = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="MSRP / Original Retail Price")
    current_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True, help_text="Auto-calculated buyer price")
    offer = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Offer / discount percentage")
    
    description = models.TextField(blank=True, default="")
    reason_to_sell = models.TextField(blank=True, default="")
    warranty = models.CharField(max_length=255, blank=True, default="")
    warranty_attachment = models.CharField(max_length=1000, blank=True, default="", help_text="Cloudflare S3 PDF link")
    
    third_party_certificate = models.BooleanField(default=False, db_index=True, help_text="3rd Party Certificate as boolean value")
    third_party_documents = models.CharField(max_length=1000, blank=True, default="", help_text="Cloudflare S3 documents link")
    
    ENQUIRY_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('DECLINED', 'Declined'),
    ]
    
    enquiry_status = models.CharField(
        max_length=20, 
        choices=ENQUIRY_STATUS_CHOICES, 
        default='PENDING',
        db_index=True
    )
    is_active = models.BooleanField(default=False, db_index=True)
    date_approved = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when product enquiry status was set to APPROVED")
    views_count = models.PositiveIntegerField(default=0, db_index=True)

    # Collection & Showcase Flags
    is_featured = models.BooleanField(default=False, db_index=True, help_text="Featured Deal showcase")
    is_best_selling = models.BooleanField(default=False, db_index=True, help_text="Best Selling showcase")
    is_new_arrival = models.BooleanField(default=False, db_index=True, help_text="New Arrival showcase")

    # Ordering / Sequences (lower number appears first, e.g. 1, 2, 3...)
    display_order = models.PositiveIntegerField(default=0, db_index=True, help_text="General display order")
    featured_order = models.PositiveIntegerField(default=0, db_index=True, help_text="Order in Featured Deals")
    best_selling_order = models.PositiveIntegerField(default=0, db_index=True, help_text="Order in Best Selling")
    new_arrival_order = models.PositiveIntegerField(default=0, db_index=True, help_text="Order in New Arrivals")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def active_status(self) -> str:
        return "active" if self.is_active else "inactive"

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        db_table = "products"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(liquidating_price__gte=0), name="check_product_liquidating_price_gte_0"),
            models.CheckConstraint(condition=models.Q(current_price__gte=0), name="check_product_current_price_gte_0"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="check_product_quantity_gte_0"),
        ]
        indexes = [
            models.Index(fields=["is_active", "enquiry_status"], name="idx_prod_active_status"),
            models.Index(fields=["category", "is_active"], name="idx_prod_cat_active"),
            models.Index(fields=["subcategory", "is_active"], name="idx_prod_subcat_active"),
            models.Index(fields=["vendor", "created_at"], name="idx_prod_vendor_created"),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_status = None
        if not is_new:
            orig = Product.objects.filter(pk=self.pk).values("enquiry_status").first()
            if orig:
                old_status = orig.get("enquiry_status")

        if not self.product_id:
            max_id = Product.objects.aggregate(max_id=models.Max("id"))["max_id"] or 0
            self.product_id = f"PRO-{(max_id + 1):05d}"
            
        # Calculate current_price = Liquidating Price * 1.10
        if self.liquidating_price:
            val = Decimal(str(self.liquidating_price)) * Decimal("1.10")
            self.current_price = val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            self.current_price = Decimal("0.00")

        # Auto-set date_approved when status becomes APPROVED
        if str(self.enquiry_status).upper() == 'APPROVED':
            if not self.date_approved:
                self.date_approved = timezone.now()
        else:
            self.date_approved = None

        super().save(*args, **kwargs)

        # Trigger notification and email if status transitioned to APPROVED or DECLINED
        if not is_new and (str(old_status or '').upper() != str(self.enquiry_status).upper()):
            curr_status = str(self.enquiry_status).upper()
            target_vendor = self.vendor
            if not target_vendor and self.vendor_id:
                try:
                    target_vendor = VendorDetails.objects.filter(id=self.vendor_id).first()
                except Exception:
                    target_vendor = None

            if not target_vendor and hasattr(self, 'raw_data') and isinstance(self.raw_data, dict):
                raw_vid = self.raw_data.get('vendor_id') or self.raw_data.get('user_id')
                if raw_vid:
                    v_clean = str(raw_vid).strip()
                    if v_clean.upper().startswith("USR-"):
                        v_clean = v_clean[4:].strip()
                    if v_clean.isdigit():
                        target_vendor = VendorDetails.objects.filter(id=int(v_clean)).first()
                    if not target_vendor:
                        target_vendor = VendorDetails.objects.filter(email__iexact=str(raw_vid).strip()).first()

            recipient_email = None
            recipient_name = "Valued Seller"
            if target_vendor:
                recipient_email = target_vendor.email
                recipient_name = target_vendor.full_name or target_vendor.company_name or target_vendor.username or "Valued Seller"

            if not recipient_email and hasattr(self, '_user_email') and self._user_email:
                recipient_email = str(self._user_email).strip()

            if curr_status == 'APPROVED':
                profile_info = target_vendor.get_profile_completion_details() if target_vendor else None
                is_prof_complete = profile_info["is_complete"] if profile_info else True
                pct = profile_info["percentage"] if profile_info else 100
                missing_labels = profile_info["missing_fields_labels"] if profile_info else []

                if target_vendor:
                    try:
                        from .services import create_vendor_notification
                        if not is_prof_complete:
                            notif_title = "Listing Approved - Profile Incomplete"
                            notif_msg = (
                                f"Your product '{self.product_name}' has been approved! However, your profile is only {pct}% complete. "
                                f"To list your product for public visibility, you must complete all your user details."
                            )
                        else:
                            notif_title = "Listing Approved"
                            notif_msg = f"Your product '{self.product_name}' has been approved and published to the marketplace."

                        create_vendor_notification(
                            vendor=target_vendor,
                            title=notif_title,
                            message=notif_msg,
                            notification_type="LISTING",
                            action_url="/profile"
                        )
                    except Exception:
                        pass

                if recipient_email:
                    try:
                        from .services import EmailService
                        EmailService.send_product_approved_email(
                            to_email=recipient_email,
                            product=self,
                            recipient_name=recipient_name,
                            is_profile_complete=is_prof_complete,
                            profile_completion_percentage=pct,
                            missing_fields_labels=missing_labels
                        )
                    except Exception:
                        pass

            elif curr_status == 'DECLINED':
                decline_reason = getattr(self, '_decline_reason', '')
                if target_vendor:
                    try:
                        from .services import create_vendor_notification
                        msg = f"Your product '{self.product_name}' was not approved."
                        if decline_reason:
                            msg += f" Reason: {decline_reason}"
                        else:
                            msg += " Please review your listing specifications."
                        create_vendor_notification(
                            vendor=target_vendor,
                            title="Listing Declined",
                            message=msg,
                            notification_type="LISTING",
                            action_url="/profile"
                        )
                    except Exception:
                        pass

                if recipient_email:
                    try:
                        from .services import EmailService
                        EmailService.send_product_declined_email(
                            to_email=recipient_email,
                            product=self,
                            recipient_name=recipient_name,
                            reason=decline_reason
                        )
                    except Exception:
                        pass

        # Auto-sync pgvector embedding for semantic natural language search
        try:
            from .semantic_search import sync_product_embedding
            sync_product_embedding(self)
        except Exception:
            pass


    @property
    def sku(self):
        return self.model_no or self.product_id

    @property
    def brand(self):
        return self.brand_name

    @brand.setter
    def brand(self, val):
        self.brand_name = val

    @property
    def stock_quantity(self):
        return self.quantity

    @stock_quantity.setter
    def stock_quantity(self, val):
        self.quantity = val

    @property
    def previous_price(self):
        return self.msrp

    @previous_price.setter
    def previous_price(self, val):
        self.msrp = val

    @property
    def price(self):
        return self.current_price

    @property
    def discount_price(self):
        return self.msrp

    @property
    def image(self):
        first_img = self.images.first()
        return first_img.image if first_img else None

    @property
    def raw_data(self):
        first_url = self.images.first().url if self.images.exists() else ""
        return {
            "product_name": self.product_name,
            "title": self.product_name,
            "price": self.liquidating_price,
            "quantity": self.quantity,
            "description": self.description,
            "reason_to_sell": self.reason_to_sell,
            "warranty": self.warranty,
            "warranty_attachment": self.warranty_attachment,
            "warranty_document": self.warranty_attachment,
            "third_party_certificate": self.third_party_certificate,
            "third_party_documents": self.third_party_documents,
            "certificate_document": self.third_party_documents,
            "image": first_url,
            "featured_image_url": first_url,
            "product_image": first_url,
        }

    @property
    def condition(self):
        return ""

    @property
    def is_available_for_offers(self):
        return False

    @property
    def warranty_document(self):
        return self.warranty_attachment

    @property
    def certificate_document(self):
        return self.third_party_documents

    @property
    def formatted_vendor_id(self):
        if self.vendor:
            return self.vendor.user_id
        if self.vendor_id:
            return f"USR-{self.vendor_id:04d}"
        return ""

    @property
    def vendor_user_id(self):
        return self.formatted_vendor_id

    def __str__(self):
        return f"{self.product_name} ({self.product_id or self.model_no}) - {self.enquiry_status}"



class SystemSettings(models.Model):
    """
    Global system settings, such as Operational Charges and Maintenance Mode.
    """
    operational_charge_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    is_maintenance_mode = models.BooleanField(default=False, db_index=True)
    maintenance_message = models.TextField(default="Website is under maintenance. Please check back later.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Settings"
        verbose_name_plural = "System Settings"
        db_table = "system_settings"

    def __str__(self):
        status_str = "Maintenance ON" if self.is_maintenance_mode else "Live"
        return f"Global Config ({status_str}, Charge: {self.operational_charge_percentage}%)"



class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/images/gallery/", null=True, blank=True)
    image_url = models.CharField(max_length=1000, blank=True, default="", help_text="Direct Cloudflare S3/R2 image link")
    is_real_photo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True = actual product photo taken by seller. False = stock/catalog/placeholder."
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Product Image"
        verbose_name_plural = "Product Images"
        ordering = ["-is_real_photo", "-uploaded_at"]

    def __str__(self):
        photo_type = "Real Photo" if self.is_real_photo else "Stock/Catalog"
        return f"{photo_type} for {self.product.product_name}"

    @property
    def url(self):
        if self.image_url:
            return self.image_url
        if self.image:
            try:
                return self.image.url
            except Exception:
                return ""
        return ""



class PartnershipEnquiry(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField()
    business_location = models.CharField(max_length=255, blank=True, default="")
    partnership_interest = models.CharField(max_length=255, blank=True, default="")
    subject = models.CharField(max_length=255, blank=True, default="")
    collaboration_details = models.TextField(blank=True, default="")
    
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("REVIEWED", "Reviewed"),
        ("CONTACTED", "Contacted"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Partnership Enquiry"
        verbose_name_plural = "Partnership Enquiries"
        db_table = "partnership_enquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.partnership_interest}"


class ContactUsEnquiry(models.Model):
    full_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, default="")
    enquiry_type = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField(blank=True, default="")
    
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("REVIEWED", "Reviewed"),
        ("CONTACTED", "Contacted"),
        ("BLOCKED", "Blocked"),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    is_blocked = models.BooleanField(default=False, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contact Us Enquiry"
        verbose_name_plural = "Contact Us Enquiries"
        db_table = "contact_us_enquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} ({self.email}) - {self.enquiry_type}"


class AnalyticsViewLog(models.Model):
    ENTITY_TYPE_CHOICES = (
        ("blog", "Blog Post"),
        ("product", "Product"),
        ("lot", "Lot Batch"),
        ("page", "Page"),
        ("other", "Other"),
    )

    entity_type = models.CharField(max_length=50, choices=ENTITY_TYPE_CHOICES, default="other", db_index=True)
    entity_id = models.IntegerField(null=True, blank=True, db_index=True)
    entity_slug = models.CharField(max_length=255, blank=True, default="", db_index=True)
    path = models.CharField(max_length=500, blank=True, default="", db_index=True)
    referrer = models.CharField(max_length=500, blank=True, default="")
    user_agent = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(VendorDetails, on_delete=models.SET_NULL, null=True, blank=True, related_name="view_logs")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Analytics View Log"
        verbose_name_plural = "Analytics View Logs"
        db_table = "analytics_view_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"], name="idx_view_type_id"),
            models.Index(fields=["entity_type", "entity_slug"], name="idx_view_type_slug"),
        ]

class PageViewLog(models.Model):
    ENTITY_TYPE_CHOICES = (
        ("lot", "Lot Batch"),
        ("product", "Product"),
        ("blog", "Blog Post"),
        ("page", "Page"),
    )

    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES, db_index=True)
    entity_id = models.IntegerField(null=True, blank=True, db_index=True)
    entity_slug = models.CharField(max_length=255, blank=True, default="", db_index=True)
    path = models.CharField(max_length=500, blank=True, default="", db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(blank=True, default="")
    referrer = models.CharField(max_length=500, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(default=0, db_index=True, help_text="Time spent on page in seconds")
    session_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    visitor_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    is_stuck = models.BooleanField(default=False, db_index=True, help_text="Flagged if user stayed unusually long without converting")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Page View Log"
        verbose_name_plural = "Page View Logs"
        db_table = "page_view_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "ip_address", "created_at"], name="idx_page_view_dedup_id"),
            models.Index(fields=["entity_type", "entity_slug", "ip_address", "created_at"], name="idx_page_view_dedup_slug"),
        ]

    def __str__(self):
        return f"{self.entity_type} ({self.entity_slug or self.entity_id}) - {self.ip_address} @ {self.created_at}"


class BlogPost(models.Model):
    STATUS_CHOICES = (
        ("published", "Published"),
        ("draft", "Draft"),
    )

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    blog_code = models.CharField(max_length=50, blank=True, default="", db_index=True)
    author = models.CharField(max_length=150, blank=True, default="Admin")
    category_name = models.CharField(max_length=100, blank=True, default="General", db_index=True)
    excerpt = models.TextField(blank=True, default="")
    content = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="blog_images/", blank=True, null=True)
    featured_image_url = models.CharField(max_length=500, blank=True, default="")
    
    # Yoast SEO & Meta Tags
    meta_title = models.CharField(max_length=255, blank=True, default="")
    meta_description = models.TextField(blank=True, default="")
    meta_keywords = models.CharField(max_length=255, blank=True, default="")
    
    # Metrics & Status
    read_time = models.PositiveIntegerField(default=3)
    total_reads = models.PositiveIntegerField(default=0)
    views_count = models.PositiveIntegerField(default=0, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="published", db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Blog Post"
        verbose_name_plural = "Blog Posts"
        db_table = "blog_posts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.blog_code}) - {self.status}"


class Brand(models.Model):
    name = models.CharField(max_length=255, db_index=True)
    image = models.ImageField(upload_to="brand_logos/", blank=True, null=True)
    image_url = models.CharField(max_length=500, blank=True, default="")
    alt_text = models.CharField(max_length=255, blank=True, default="")
    redirect_link = models.CharField(max_length=500, blank=True, default="")
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"
        db_table = "landing_brands"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.name}"


class PriceAdjustmentLog(models.Model):
    admin_name = models.CharField(max_length=150, default="Admin")
    action_type = models.CharField(max_length=50) # "Increase Prices", "Decrease Prices", "Global Charge Update"
    adjustment_method = models.CharField(max_length=50, blank=True, default="") # "Percentage (%)", "Fixed Amount"
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    note = models.CharField(max_length=255, blank=True, default="")
    affected_products_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="Applied") # "Applied", "Rolled Back"
    backup_snapshot = models.JSONField(default=dict, blank=True) # {product_id: old_price, ...}
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Price Adjustment Log"
        verbose_name_plural = "Price Adjustment Logs"
        db_table = "price_adjustment_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action_type} - {self.value} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class PopupSetting(models.Model):
    title = models.CharField(max_length=255, default="Important Admin Notification")
    message = models.TextField(default="Welcome to Surplus Admin Portal. Please check your pending seller and lot enquiries.")
    popup_type = models.CharField(max_length=50, default="info") # info, warning, success, danger, promotion
    is_active = models.BooleanField(default=True, db_index=True)
    delay_minutes = models.PositiveIntegerField(default=1, help_text="Minutes before re-showing popup after closing")
    banner_image = models.ImageField(upload_to="popup_banners/", blank=True, null=True)
    banner_url = models.CharField(max_length=500, blank=True, default="")
    button_label = models.CharField(max_length=100, blank=True, default="Got It")
    button_link = models.CharField(max_length=500, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Popup Setting"
        verbose_name_plural = "Popup Settings"
        db_table = "popup_settings"

    def __str__(self):
        status = "Active" if self.is_active else "Disabled"
        return f"{self.title} ({status}, Delay: {self.delay_minutes}m)"


class Auction(models.Model):
    """
    Independent, model-agnostic Auction model for competitive bidding.
    Can auction any inventory (custom liquidation batches, products, or lot manifests)
    via snapshot item_metadata and generic references without tight schema coupling.
    """
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("live", "Live"),
        ("ended", "Ended"),
        ("sold", "Sold"),
        ("reserve_not_met", "Reserve Not Met"),
        ("cancelled", "Cancelled"),
    )

    ITEM_TYPE_CHOICES = (
        ("custom", "Custom Surplus Batch"),
        ("lot", "Lot Manifest"),
        ("product", "Product"),
    )

    auction_id = models.CharField(max_length=30, unique=True, db_index=True)
    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")

    item_type = models.CharField(max_length=30, choices=ITEM_TYPE_CHOICES, default="custom", db_index=True)
    item_reference_id = models.CharField(max_length=100, blank=True, default="", db_index=True, help_text="Optional reference ID like lot_number or product_id")
    item_metadata = models.JSONField(default=dict, blank=True, help_text="Point-in-time snapshot of item specifications, manifests, condition, and origin")

    category = models.ForeignKey(MainCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="auctions")
    vendor = models.ForeignKey(VendorDetails, on_delete=models.SET_NULL, null=True, blank=True, related_name="auctions", help_text="Seller / Consignor")

    currency = models.CharField(max_length=10, default="USD")
    starting_bid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    current_bid = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True)
    reserve_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Confidential minimum price. If not met, auction ends as reserve_not_met")
    bid_increment = models.DecimalField(max_digits=10, decimal_places=2, default=25.00)
    buy_now_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Instant buyout price if enabled")

    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    original_end_time = models.DateTimeField(null=True, blank=True)

    # Anti-sniping soft close settings
    auto_extend_minutes = models.PositiveIntegerField(default=3, help_text="Minutes to extend if a bid is placed in the final window")
    auto_extend_threshold_seconds = models.PositiveIntegerField(default=120, help_text="Window before end_time (in seconds) that triggers auto-extension")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft", db_index=True)
    total_bids = models.PositiveIntegerField(default=0, db_index=True)
    views_count = models.PositiveIntegerField(default=0)

    winner = models.ForeignKey(VendorDetails, on_delete=models.SET_NULL, null=True, blank=True, related_name="won_auctions")
    winning_bid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Auction"
        verbose_name_plural = "Auctions"
        db_table = "auctions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "start_time", "end_time"], name="idx_auction_status_times"),
            models.Index(fields=["item_type", "item_reference_id"], name="idx_auction_item_ref"),
        ]

    def save(self, *args, **kwargs):
        if not self.auction_id:
            self.auction_id = f"AUC-{uuid.uuid4().hex[:8].upper()}"
        if not self.original_end_time and self.end_time:
            self.original_end_time = self.end_time
        if self.current_bid == Decimal("0.00") and self.starting_bid > Decimal("0.00"):
            self.current_bid = self.starting_bid
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.auction_id} - {self.title} ({self.status})"

    @property
    def is_live(self):
        now = timezone.now()
        return self.status == "live" or (self.status == "scheduled" and self.start_time <= now <= self.end_time)

    @property
    def time_remaining_seconds(self):
        now = timezone.now()
        if now >= self.end_time:
            return 0
        return int((self.end_time - now).total_seconds())

    @property
    def minimum_next_bid(self):
        if self.total_bids == 0:
            return self.starting_bid
        return self.current_bid + self.bid_increment

    @property
    def is_reserve_met(self):
        if not self.reserve_price or self.reserve_price <= Decimal("0.00"):
            return True
        return self.current_bid >= self.reserve_price

    def sync_status(self):
        """
        Dynamically transitions auction status based on current timestamp.
        """
        now = timezone.now()
        changed = False

        if self.status == "scheduled" and now >= self.start_time:
            if now < self.end_time:
                self.status = "live"
                changed = True
            else:
                self.status = "ended"
                changed = True

        if self.status == "live" and now >= self.end_time:
            self.status = "ended"
            changed = True

        if changed:
            self.save(update_fields=["status", "updated_at"])
        return self.status


class AuctionBid(models.Model):
    """
    Immutable ledger of placed bids.
    """
    BID_TYPE_CHOICES = (
        ("manual", "Manual Bid"),
        ("proxy", "Proxy / Auto Bid"),
        ("buy_now", "Buy Now"),
    )

    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="bids")
    bidder = models.ForeignKey(VendorDetails, on_delete=models.CASCADE, related_name="auction_bids")
    amount = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)
    max_proxy_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bid_type = models.CharField(max_length=20, choices=BID_TYPE_CHOICES, default="manual")
    is_winning = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Auction Bid"
        verbose_name_plural = "Auction Bids"
        db_table = "auction_bids"
        ordering = ["-amount", "-created_at"]
        indexes = [
            models.Index(fields=["auction", "amount"], name="idx_bid_auction_amount"),
            models.Index(fields=["bidder", "created_at"], name="idx_bid_bidder_date"),
        ]

    def __str__(self):
        return f"{self.bidder.username} - {self.amount} ({self.auction.auction_id})"


class AuctionImage(models.Model):
    """
    Image gallery for an auction listing.
    """
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="auctions/%Y/%m/", null=True, blank=True)
    image_url = models.CharField(max_length=500, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auction Image"
        verbose_name_plural = "Auction Images"
        db_table = "auction_images"
        ordering = ["display_order", "-is_primary", "id"]

    def __str__(self):
        return f"Image for {self.auction.auction_id}"

    @property
    def url(self):
        if self.image:
            return self.image.url
        return self.image_url


class AuctionWatchlist(models.Model):
    """
    Buyer watchlist tracking for notifications and quick access.
    """
    auction = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="watchlists")
    user = models.ForeignKey(VendorDetails, on_delete=models.CASCADE, related_name="auction_watchlists")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Auction Watchlist"
        verbose_name_plural = "Auction Watchlists"
        db_table = "auction_watchlists"
        unique_together = ("auction", "user")

    def __str__(self):
        return f"{self.user.username} watching {self.auction.auction_id}"


class VendorNotification(models.Model):
    """
    In-app notification system for vendors / registered users.
    Tracks status updates, listings, RFQs, auctions, orders, and system alerts.
    """
    NOTIFICATION_TYPE_CHOICES = (
        ("LISTING", "Listing"),
        ("RFQ", "RFQ"),
        ("AUCTION", "Auction"),
        ("SYSTEM", "System"),
        ("ORDER", "Order"),
    )

    vendor = models.ForeignKey(
        VendorDetails,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPE_CHOICES,
        default="SYSTEM",
        db_index=True
    )
    action_url = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Frontend redirection route, e.g. /profile or /browse"
    )
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Vendor Notification"
        verbose_name_plural = "Vendor Notifications"
        db_table = "vendor_notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor", "is_read"], name="idx_vnotif_v_read"),
            models.Index(fields=["vendor", "-created_at"], name="idx_vnotif_v_created"),
        ]

    def __str__(self):
        v_label = getattr(self.vendor, "vendor_id", str(self.vendor_id))
        return f"[{v_label}] {self.title} ({'Read' if self.is_read else 'Unread'})"


class ProductEmbedding(models.Model):
    """
    Vector embeddings for Semantic Natural Language Search using pgvector in Neon DB.
    Enables conversational queries (e.g. 'Show me 2U rackmount servers under $500 in Maharashtra').
    """
    product = models.OneToOneField(
        'Product',
        on_delete=models.CASCADE,
        related_name="vector_embedding",
        db_index=True
    )
    embedding = VectorField(dimensions=768, null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    embedded_text = models.TextField(blank=True, default="")
    model_name = models.CharField(max_length=100, default="surplus-semantic-v1")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product Vector Embedding"
        verbose_name_plural = "Product Vector Embeddings"
        db_table = "product_embeddings"
        indexes = [
            HnswIndex(
                name="idx_prod_embed_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            )
        ]

    def __str__(self):
        return f"Embedding for Product #{self.product_id}"
