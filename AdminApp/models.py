import uuid
import hashlib
import hmac
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from datetime import timedelta


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
        Hashes password using salted SHA-256: <hash>:<salt>
        """
        salt = uuid.uuid4().hex
        enc_pass = hashlib.sha256(salt.encode() + raw_password.encode()).hexdigest() + ":" + salt
        return enc_pass

    def check_password(self, raw_password: str) -> bool:
        """
        Verifies salted SHA-256 password hash using constant-time comparison.
        Prevents timing side-channel attacks.
        """
        try:
            stored_hash, salt = self.pass_word.split(":")
            computed_hash = hashlib.sha256(salt.encode() + raw_password.encode()).hexdigest()
            return hmac.compare_digest(computed_hash, stored_hash)
        except (ValueError, AttributeError):
            return False

    def set_password(self, raw_password: str):
        self.pass_word = self.hash_password(raw_password)

    def get_salt(self) -> str:
        return self.pass_word.split(":")[1] if ":" in self.pass_word else ""


class VendorDetails(models.Model):
    USER_TYPE_CHOICES = (
        ("BUYER", "Buyer"),
        ("SELLER", "Seller"),
        ("BOTH", "Both"),
    )
    
    username = models.CharField(max_length=150, unique=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    mobile_number = models.CharField(max_length=20, blank=True, default="")
    
    ENTITY_TYPE_CHOICES = (
        ("INDIVIDUAL", "Individual"),
        ("COMPANY", "Company/Business"),
    )
    account_entity_type = models.CharField(max_length=20, choices=ENTITY_TYPE_CHOICES, default="COMPANY")
    
    company_name = models.CharField(max_length=255, blank=True, default="")
    business_location = models.CharField(max_length=255, blank=True, default="")
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
        Hashes password using salted SHA-256: <hash>:<salt>
        """
        salt = uuid.uuid4().hex
        enc_pass = hashlib.sha256(salt.encode() + raw_password.encode()).hexdigest() + ":" + salt
        return enc_pass

    def check_password(self, raw_password: str) -> bool:
        """
        Verifies raw_password against stored hash
        """
        if not self.pass_word:
            return False
        try:
            stored_hash, salt = self.pass_word.split(":")
            check_hash = hashlib.sha256(salt.encode() + raw_password.encode()).hexdigest()
            return check_hash == stored_hash
        except ValueError:
            return False

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
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    brand = models.CharField(max_length=255, blank=True, default="")
    category_name = models.CharField(max_length=255, blank=True, default="")  # Using name since they might not pick an exact SubCategory ID in the form initially
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    manufacturing_country = models.CharField(max_length=100, blank=True, default="")
    manufacturing_year = models.PositiveIntegerField(null=True, blank=True)
    dimensions = models.CharField(max_length=100, blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    excluded_countries = models.JSONField(default=list, blank=True)
    reason_to_sell = models.TextField(blank=True, default="")
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

    def save(self, *args, **kwargs):
        if not self.product_id:
            last_item = SellerProductEnquiry.objects.order_by("-id").first()
            next_num = (last_item.id + 1) if last_item else 1
            self.product_id = f"PRO-{next_num:05d}"
            
        super().save(*args, **kwargs)

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
    category_name = models.CharField(max_length=255, blank=True, default="")
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=10, default="USD")
    reason_to_sell = models.TextField(blank=True, default="")
    
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

    def save(self, *args, **kwargs):
        if not self.batch_id:
            last_item = LotBatchEnquiry.objects.order_by("-id").first()
            next_num = (last_item.id + 1) if last_item else 1
            self.batch_id = f"BAT-{next_num:05d}"
            
        if self.enquiry_status == 'approved':
            self.active_status = 'active'
        else:
            self.active_status = 'inactive'
            
        super().save(*args, **kwargs)

    @property
    def lot_number(self):
        return self.batch_id

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
    category_name = models.CharField(max_length=255, blank=True, default="")
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=10, default="USD")
    reason_to_sell = models.TextField(blank=True, default="")
    
    file = models.FileField(upload_to="lot_enquiries/%Y/%m/", null=True, blank=True)
    enquiry_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    active_status = models.CharField(max_length=20, choices=ACTIVE_STATUS_CHOICES, default="inactive", db_index=True)
    is_active = models.BooleanField(default=False, db_index=True)
    raw_data = models.JSONField(default=dict, blank=True, help_text="Flexible storage for extra lot specifications and product manifest")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lot"
        verbose_name_plural = "Lots"
        db_table = "lots"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.lot_number:
            last_item = Lot.objects.order_by("-id").first()
            next_num = (last_item.id + 1) if last_item else 1
            self.lot_number = f"LOT-{next_num:05d}"
            
        if self.active_status == 'active':
            self.is_active = True
        else:
            self.is_active = False

        super().save(*args, **kwargs)

    @property
    def batch_id(self):
        return self.lot_number

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

    def save(self, *args, **kwargs):
        if not self.product_id:
            last_item = LotProduct.objects.order_by("-id").first()
            next_num = (last_item.id + 1) if last_item else 1
            self.product_id = f"BLK-{next_num:05d}"
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
    model_no = models.CharField(max_length=255, blank=True, default="", db_index=True, help_text="Model No. / Part No.")
    description = models.TextField(blank=True, default="")
    
    liquidating_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True)
    previous_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True, help_text="Auto-calculated: Liquidating Price * 1.10")
    stock_quantity = models.PositiveIntegerField(default=0)
    brand = models.CharField(max_length=255, blank=True, default="")
    
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
    is_available_for_offers = models.BooleanField(default=True, db_index=True)
    
    # Specific Fields
    condition = models.CharField(max_length=255, blank=True, default="", db_index=True, help_text="Product condition e.g. Brand New, Refurbished, Used")
    inventory_location = models.CharField(max_length=255, blank=True, default="")
    manufacturing_country = models.CharField(max_length=100, blank=True, default="")
    manufacturing_year = models.PositiveIntegerField(null=True, blank=True)
    dimensions = models.CharField(max_length=100, blank=True, default="")
    expiry_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    excluded_countries = models.JSONField(default=list, blank=True, help_text="List of excluded country codes")
    reason_to_sell = models.TextField(blank=True, default="")
    warranty = models.CharField(max_length=255, blank=True, default="")
    third_party_certificate = models.FileField(upload_to="products/certificates/", null=True, blank=True)

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

    image = models.ImageField(upload_to="products/images/", null=True, blank=True)
    is_active = models.BooleanField(default=False, db_index=True)
    date_approved = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when product enquiry status was set to APPROVED")
    raw_data = models.JSONField(default=dict, blank=True, help_text="Flexible storage for extra product fields and seller contact details")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"
        db_table = "products"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.product_id:
            last_item = Product.objects.order_by("-id").first()
            next_num = (last_item.id + 1) if last_item else 1
            self.product_id = f"PRO-{next_num:05d}"
            
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

    @property
    def sku(self):
        return self.model_no or self.product_id

    @property
    def price(self):
        return self.current_price

    @property
    def discount_price(self):
        return self.previous_price

    @property
    def active_status(self):
        return "active" if self.is_active else "inactive"

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
    image = models.ImageField(upload_to="products/images/gallery/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.product.product_name}"


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



