# Surplus Backend Database Schema

This document provides a comprehensive overview of the database schema for the **Surplus Backend** application built on Django.

---

## 1. User & Authentication Module

### `admin_details` ([`AdminDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L10))
Stores administrative user accounts for managing the platform.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key, Auto-increment | Internal Unique Identifier |
| `username` | CharField(150) | `unique=True`, `db_index=True` | Admin login username |
| `email` | EmailField | `unique=True`, `db_index=True` | Admin contact/login email |
| `pass_word` | CharField(255) | | Salted SHA-256 hash (`hash:salt`) |
| `account_type` | CharField(50) | Default: `"Admin"`, Choices: `SuperAdmin`, `Admin`, `XLSXAdmin` | Role/Permission level |
| `status` | BooleanField | Default: `True`, `db_index=True` | Account active/inactive status |
| `session_version` | PositiveIntegerField | Default: `1` | Session invalidation counter |
| `web_is_active` | CharField(50) | Default: `"live"` | Controls global site maintenance state |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Account creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last update timestamp |

---

### `vendor_details` ([`VendorDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L86))
Stores buyer and seller accounts operating on the platform.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Internal Unique Identifier |
| `username` | CharField(150) | `unique=True`, `db_index=True` | Vendor username |
| `email` | EmailField | `unique=True`, `db_index=True` | Vendor email address |
| `mobile_number` | CharField(20) | Blank, Default: `""` | Vendor contact number |
| `account_entity_type` | CharField(20) | Default: `"COMPANY"`, Choices: `INDIVIDUAL`, `COMPANY` | Account classification |
| `company_name` | CharField(255) | Blank | Registered business/company name |
| `business_location` | CharField(255) | Blank | Registered operating location |
| `category_interested`| JSONField | Default: `list`, Blank | Interested product categories |
| `user_type` | CharField(20) | Default: `"BUYER"`, Choices: `BUYER`, `SELLER`, `BOTH` | Role on marketplace |
| `pass_word` | CharField(255) | Null, Blank | Salted SHA-256 hash (`hash:salt`) |
| `status` | BooleanField | Default: `True`, `db_index=True` | Active/Inactive status |
| `session_version` | PositiveIntegerField | Default: `1` | Invalidation token |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Account creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last update timestamp |

---

### `vendor_otps` ([`VendorOTP`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L179))
Stores one-time passwords for vendor login & registration.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Identifier |
| `email` | EmailField | `db_index=True` | Targeted vendor email |
| `otp` | CharField(6) | | 6-digit verification code |
| `is_used` | BooleanField | Default: `False`, `db_index=True` | Flag indicating usage |
| `vendor` | ForeignKey | FK to [`VendorDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L86), `on_delete=CASCADE`, Null | Linked vendor account |
| `registration_data`| JSONField | Null, Blank | Temporary registration details |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Expiry validation window (10 mins) |

---

### `admin_password_reset_otp` ([`AdminPasswordResetOTP`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L211))
OTP records for password resets on Admin accounts.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Identifier |
| `admin` | ForeignKey | FK to [`AdminDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L10), `on_delete=CASCADE` | Targeted admin user |
| `email` | EmailField | `db_index=True` | Target email address |
| `otp` | CharField(6) | | 6-digit OTP code |
| `is_used` | BooleanField | Default: `False`, `db_index=True` | Usage flag |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Creation timestamp |

---

## 2. Category & Catalog Structure

### `main_categories` ([`MainCategory`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L445))
Top-level product categories.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Category ID |
| `name` | CharField(150) | `unique=True`, `db_index=True` | Display category name |
| `slug` | SlugField(150) | `unique=True`, `db_index=True` | URL slug |
| `description` | TextField | Blank | Overview / text details |
| `image` | ImageField | Upload: `categories/main/`, Null | Category banner/thumbnail |
| `is_active` | BooleanField | Default: `True`, `db_index=True` | Visibility toggle |
| `created_at` | DateTimeField | `auto_now_add=True` | Creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last updated |

---

### `sub_categories` ([`SubCategory`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L467))
Second-tier categories linked to a parent `MainCategory`.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Sub-category ID |
| `main_category` | ForeignKey | FK to [`MainCategory`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L445), `on_delete=CASCADE` | Parent main category |
| `name` | CharField(150) | `db_index=True` | Sub-category name |
| `slug` | SlugField(150) | `unique=True`, `db_index=True` | URL slug |
| `description` | TextField | Blank | Sub-category summary |
| `image` | ImageField | Upload: `categories/sub/`, Null | Thumbnail image |
| `is_active` | BooleanField | Default: `True`, `db_index=True` | Visibility toggle |
| `created_at` | DateTimeField | `auto_now_add=True` | Creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last updated |

---

## 3. Products & Lots Engine

### `products` ([`Product`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L588))
Single product listings and approved marketplace products.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Database primary key |
| `product_id` | CharField(30) | Blank, `db_index=True` | Formatted ID (`PRO-00001`) |
| `vendor` | ForeignKey | FK to [`VendorDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L86), `on_delete=SET_NULL`, Null | Listing owner / seller |
| `product_name` | CharField(255) | `db_index=True` | Item title |
| `model_no` | CharField(255) | Blank, `db_index=True` | Model / Part No / SKU |
| `description` | TextField | Blank | Comprehensive item details |
| `liquidating_price` | Decimal(12,2)| Default: `0.00`, `db_index=True` | Seller base price |
| `previous_price` | Decimal(12,2)| Null, Blank | Original listing or discount price |
| `current_price` | Decimal(12,2)| Default: `0.00`, `db_index=True` | Calculated price (`Liquidating * 1.10`) |
| `stock_quantity` | PositiveInteger | Default: `0` | Available stock count |
| `brand` | CharField(255) | Blank | Manufacturer / Brand name |
| `category` | ForeignKey | FK to [`MainCategory`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L445), `on_delete=SET_NULL`, Null | Primary category |
| `subcategory` | ForeignKey | FK to [`SubCategory`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L467), `on_delete=SET_NULL`, Null | Sub-category |
| `is_available_for_offers`| BooleanField | Default: `True`, `db_index=True` | Allow buyers to submit custom offers |
| `condition` | CharField(255) | Blank, `db_index=True` | e.g. New, Refurbished, Used |
| `inventory_location` | CharField(255) | Blank | Warehouse / stock location |
| `manufacturing_country`| CharField(100) | Blank | Country of Origin |
| `manufacturing_year` | PositiveInteger | Null, Blank | Year of manufacture |
| `dimensions` | CharField(100) | Blank | Physical dimensions |
| `expiry_date` | DateField | Null, Blank | Expiration date if applicable |
| `currency` | CharField(10) | Default: `"USD"` | Currency denomination |
| `excluded_countries` | JSONField | Default: `list`, Blank | Country restriction list |
| `reason_to_sell` | TextField | Blank | Liquidation rationale |
| `warranty` | CharField(255) | Blank | Warranty coverage info |
| `third_party_certificate`| FileField | Upload: `products/certificates/`, Null | Compliance / QC cert files |
| `enquiry_status` | CharField(20) | Default: `'PENDING'`, Choices: `PENDING`, `APPROVED`, `DECLINED` | Moderation status |
| `image` | ImageField | Upload: `products/images/`, Null | Main featured image |
| `is_active` | BooleanField | Default: `False`, `db_index=True` | Display toggle on storefront |
| `date_approved` | DateTimeField | Null, Blank, `db_index=True` | Approval timestamp |
| `raw_data` | JSONField | Default: `dict`, Blank | Extra dynamic properties |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last update timestamp |

---

### `ProductImage` ([`ProductImage`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L728))
Gallery images attached to a [`Product`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L588).

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Image ID |
| `product` | ForeignKey | FK to [`Product`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L588), `on_delete=CASCADE` | Associated product |
| `image` | ImageField | Upload: `products/images/gallery/` | Image file |
| `uploaded_at` | DateTimeField | `auto_now_add=True` | Upload timestamp |

---

### `lots` ([`Lot`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L492))
Bulk product batches and surplus lot packages.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Internal Lot ID |
| `vendor` | ForeignKey | FK to [`VendorDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L86), `on_delete=SET_NULL`, Null | Seller submitting the lot |
| `lot_number` | CharField(30) | `unique=True`, `db_index=True` | Auto-generated ID (`LOT-00001`) |
| `title` | CharField(255) | Blank, `db_index=True` | Bulk package title |
| `description` | TextField | Blank | Lot details & manifest summary |
| `category` | ForeignKey | FK to [`SubCategory`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L467), `on_delete=SET_NULL`, Null | Primary category |
| `category_name` | CharField(255) | Blank | Fallback category name |
| `inventory_location` | CharField(255) | Blank | Stock location |
| `total_price` | Decimal(12,2)| Default: `0.00` | Package total price |
| `currency` | CharField(10) | Default: `"USD"` | Currency code |
| `reason_to_sell` | TextField | Blank | Reason for liquidating |
| `file` | FileField | Upload: `lot_enquiries/%Y/%m/`, Null | Uploaded Excel manifest |
| `enquiry_status` | CharField(20) | Default: `"pending"`, Choices: `pending`, `approved`, `declined` | Moderation state |
| `active_status` | CharField(20) | Default: `"inactive"`, Choices: `active`, `inactive` | Status string |
| `is_active` | BooleanField | Default: `False`, `db_index=True` | Live listing boolean |
| `raw_data` | JSONField | Default: `dict`, Blank | Raw specs / manifest JSON |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last update timestamp |

---

### `lot_products` ([`LotProduct`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L554))
Individual items included inside a bulk [`Lot`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L492) or [`LotBatchEnquiry`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L384).

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Item ID |
| `lot` | ForeignKey | FK to [`Lot`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L492), `on_delete=CASCADE`, Null | Linked active Lot |
| `enquiry` | ForeignKey | FK to [`LotBatchEnquiry`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L384), `on_delete=CASCADE`, Null | Linked raw enquiry batch |
| `product_id` | CharField(30) | `unique=True`, `db_index=True` | Bulk item ID (`BLK-00001`) |
| `product_name` | CharField(255) | Blank | Sub-item name |
| `quantity` | PositiveInteger | Default: `0` | Item quantity within lot |
| `condition` | CharField(255) | Blank | Item condition |
| `raw_data` | JSONField | Default: `dict`, Blank | Extra row details |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Last update timestamp |

---

## 4. Seller Enquiries

### `seller_product_enquiries` ([`SellerProductEnquiry`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L320))
Form submissions from sellers offering single items.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Primary Key |
| `product_id` | CharField(30) | `unique=True`, `db_index=True` | Enquiry ID (`PRO-00001`) |
| `vendor` | ForeignKey | FK to [`VendorDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L86), `on_delete=SET_NULL`, Null | Submitting seller |
| `title` | CharField(255) | `db_index=True` | Item title |
| `sku` | CharField(100) | Blank | SKU / Part number |
| `description` | TextField | Blank | Item description |
| `price` | Decimal(12,2)| Default: `0.00` | Seller target price |
| `discount_price` | Decimal(12,2)| Null, Blank | Discounted price |
| `stock_quantity` | PositiveInteger | Default: `0` | Available stock |
| `brand` | CharField(255) | Blank | Brand |
| `category_name` | CharField(255) | Blank | Raw category string |
| `inventory_location` | CharField(255) | Blank | Stock location |
| `manufacturing_country`| CharField(100) | Blank | Country of origin |
| `manufacturing_year` | PositiveInteger | Null, Blank | Year manufactured |
| `dimensions` | CharField(100) | Blank | Dimensions |
| `expiry_date` | DateField | Null, Blank | Expiration date |
| `currency` | CharField(10) | Default: `"USD"` | Currency |
| `excluded_countries` | JSONField | Default: `list`, Blank | Restricted delivery countries |
| `reason_to_sell` | TextField | Blank | Seller explanation |
| `warranty` | CharField(255) | Blank | Warranty info |
| `third_party_certificate`| FileField | Upload: `enquiries/certificates/`, Null | PDF / Cert uploaded |
| `image` | ImageField | Upload: `enquiries/images/`, Null | Product photo |
| `enquiry_status` | CharField(20) | Default: `"pending"`, Choices: `pending`, `approved`, `declined` | Moderation state |
| `active_status` | CharField(20) | Default: `"inactive"`, Choices: `active`, `inactive` | Listing status |
| `raw_data` | JSONField | Default: `dict`, Blank | Dynamic metadata |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Submission date |
| `updated_at` | DateTimeField | `auto_now=True` | Last update |

---

### `lot_batch_enquiries` ([`LotBatchEnquiry`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L384))
Uploaded bulk lot spreadsheets (.xlsx/.csv) pending verification.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Key |
| `batch_id` | CharField(30) | `unique=True`, `db_index=True` | Batch ID (`BAT-00001`) |
| `uploaded_by` | ForeignKey | FK to [`VendorDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L86), `on_delete=SET_NULL`, Null | Submitting seller |
| `file` | FileField | Upload: `lot_enquiries/%Y/%m/`, Null | Original manifest spreadsheet |
| `title` | CharField(255) | Blank | Batch title |
| `description` | TextField | Blank | Batch description |
| `category_name` | CharField(255) | Blank | Primary category string |
| `inventory_location` | CharField(255) | Blank | Warehouse location |
| `total_price` | Decimal(12,2)| Default: `0.00` | Valuation price |
| `currency` | CharField(10) | Default: `"USD"` | Currency code |
| `reason_to_sell` | TextField | Blank | Seller reason |
| `enquiry_status` | CharField(20) | Default: `"pending"`, Choices: `pending`, `approved`, `declined` | Verification state |
| `active_status` | CharField(20) | Default: `"inactive"`, Choices: `active`, `inactive` | Status |
| `raw_data` | JSONField | Default: `dict`, Blank | Parsed manifest data |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Submission time |
| `updated_at` | DateTimeField | `auto_now=True` | Last updated |

---

## 5. Content Management & Marketing (CMS)

### `content_pages` ([`ContentPage`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L244))
Dynamic CMS landing pages, help guides, and policy documents.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Page ID |
| `title` | CharField(255) | `db_index=True` | Page headline |
| `slug` | SlugField(255) | `unique=True`, `db_index=True` | URL slug |
| `category` | CharField(100) | Default: `"General"`, Choices: `General`, `Policy`, `Information`, `Help`, `Custom` | Section grouping |
| `content` | TextField | Blank | Fallback HTML / Markdown |
| `components` | JSONField | Default: `list`, Blank | Dynamic zone block schemas |
| `focus_keyphrase` | CharField(255) | Blank | Primary SEO keyword |
| `meta_title` | CharField(255) | Blank | `<title>` tag content |
| `meta_description` | TextField | Blank | `<meta name="description">` |
| `meta_keywords` | CharField(255) | Blank | `<meta name="keywords">` |
| `canonical_url` | CharField(500) | Blank | Canonical URL string |
| `robots_index` | CharField(20) | Default: `"index"`, Choices: `index`, `noindex` | Robots index setting |
| `robots_follow` | CharField(20) | Default: `"follow"`, Choices: `follow`, `nofollow` | Robots link follow |
| `robots_advanced` | CharField(100) | Blank | `noarchive`, `nosnippet`, etc. |
| `og_title`, `og_description`, `og_image` | CharField / Text | Blank | OpenGraph meta attributes |
| `twitter_title`, `twitter_description`, `twitter_image` | CharField / Text | Blank | Twitter card meta |
| `schema_type` | CharField(100) | Default: `"WebPage"` | JSON-LD schema type |
| `structured_data` | TextField | Blank | Custom JSON-LD payload |
| `status` | CharField(20) | Default: `"published"`, Choices: `published`, `draft` | Publication state |
| `is_active` | BooleanField | Default: `True`, `db_index=True` | Live toggle |
| `show_in_header` | BooleanField | Default: `False` | Render in navigation bar |
| `show_in_footer` | BooleanField | Default: `False` | Render in footer menu |
| `sort_order` | PositiveInteger | Default: `0` | Display sorting priority |
| `created_by` | ForeignKey | FK to [`AdminDetails`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L10), `on_delete=SET_NULL`, Null | Author |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Created timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Updated timestamp |

---

### `blog_posts` ([`BlogPost`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L765))
Articles and blog posts.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Blog Post ID |
| `title` | CharField(255) | `db_index=True` | Post title |
| `slug` | SlugField(255) | `unique=True`, `db_index=True` | URL path slug |
| `blog_code` | CharField(50) | Blank, `db_index=True` | Reference code |
| `author` | CharField(150) | Default: `"Admin"` | Author name |
| `category_name` | CharField(100) | Default: `"General"`, `db_index=True` | Category |
| `excerpt` | TextField | Blank | Short summary snippet |
| `content` | TextField | Blank | Full article content |
| `image` | ImageField | Upload: `blog_images/`, Null | Uploaded header image |
| `featured_image_url`| CharField(500) | Blank | External image URL |
| `meta_title`, `meta_description`, `meta_keywords` | CharField / Text | Blank | Yoast SEO Meta tags |
| `read_time` | PositiveInteger | Default: `3` | Estimated read time (mins) |
| `total_reads` | PositiveInteger | Default: `0` | View count counter |
| `status` | CharField(20) | Default: `"published"`, Choices: `published`, `draft` | Post status |
| `is_active` | BooleanField | Default: `True`, `db_index=True` | Active status |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Publication date |
| `updated_at` | DateTimeField | `auto_now=True` | Modification date |

---

### `landing_brands` ([`Brand`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L804))
Partner brand logos and links displayed on the homepage.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Brand ID |
| `name` | CharField(255) | `db_index=True` | Brand name |
| `image` | ImageField | Upload: `brand_logos/`, Null | Uploaded logo file |
| `image_url` | CharField(500) | Blank | External logo URL |
| `alt_text` | CharField(255) | Blank | Image alt text |
| `redirect_link` | CharField(500) | Blank | Destination URL on click |
| `description` | TextField | Blank | Brand description |
| `order` | PositiveInteger | Default: `0` | Sort order |
| `is_active` | BooleanField | Default: `True`, `db_index=True` | Display status |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Creation timestamp |

---

### `partnership_enquiries` ([`PartnershipEnquiry`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L737))
B2B Partnership contact form submissions.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | ID |
| `name` | CharField(255) | | Contact person name |
| `email` | EmailField | | Contact email address |
| `business_location` | CharField(255) | Blank | Business location |
| `partnership_interest`| CharField(255) | Blank | Area of interest |
| `subject` | CharField(255) | Blank | Message subject |
| `collaboration_details`| TextField | Blank | Detailed message |
| `status` | CharField(20) | Default: `"PENDING"`, Choices: `PENDING`, `REVIEWED`, `CONTACTED` | Processing status |
| `created_at` | DateTimeField | `auto_now_add=True` | Timestamp |

---

## 6. System Configuration & Audit Logs

### `system_settings` ([`SystemSettings`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L708))
Global application operational parameters.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Identifier |
| `operational_charge_percentage` | Decimal(5,2) | Default: `0.00` | Global platform markup percentage |
| `is_maintenance_mode` | BooleanField | Default: `False`, `db_index=True` | Global maintenance toggle |
| `maintenance_message` | TextField | Default: `"Website is under maintenance..."` | Message displayed to users |
| `updated_at` | DateTimeField | `auto_now=True` | Last modification timestamp |

---

### `price_adjustment_logs` ([`PriceAdjustmentLog`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L826))
Audit log recording bulk price updates and rollback snapshots.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Log ID |
| `admin_name` | CharField(150) | Default: `"Admin"` | Executing administrator |
| `action_type` | CharField(50) | | e.g. "Increase Prices", "Decrease Prices" |
| `adjustment_method` | CharField(50) | Blank | "Percentage (%)", "Fixed Amount" |
| `value` | Decimal(10,2)| Default: `0.00` | Value applied |
| `note` | CharField(255) | Blank | Rationale / admin memo |
| `affected_products_count`| PositiveInteger | Default: `0` | Number of modified products |
| `status` | CharField(20) | Default: `"Applied"` | Status ("Applied", "Rolled Back") |
| `backup_snapshot` | JSONField | Default: `dict`, Blank | `{product_id: old_price}` backup JSON |
| `created_at` | DateTimeField | `auto_now_add=True`, `db_index=True` | Timestamp |

---

### `popup_settings` ([`PopupSetting`](file:///d:/CORALBEES/surplus-backend/AdminApp/models.py#L847))
Admin modal popup settings.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Setting ID |
| `title` | CharField(255) | Default: `"Important Admin Notification"` | Header title |
| `message` | TextField | Default: `"Welcome to Surplus Admin Portal..."` | Message content |
| `popup_type` | CharField(50) | Default: `"info"` | `info`, `warning`, `success`, `danger` |
| `is_active` | BooleanField | Default: `True`, `db_index=True` | Active toggle |
| `delay_minutes` | PositiveInteger | Default: `1` | Reshow delay window in minutes |
| `banner_image` | ImageField | Upload: `popup_banners/`, Null | Banner image |
| `banner_url` | CharField(500) | Blank | Image URL |
| `button_label` | CharField(100) | Blank, Default: `"Got It"` | Action button text |
| `button_link` | CharField(500) | Blank | Action button URL |
| `updated_at` | DateTimeField | `auto_now=True` | Last updated timestamp |

---

### `api_item` ([`Item`](file:///d:/CORALBEES/surplus-backend/api/models.py#L16))
Starter model in `api/models.py`.

| Field Name | Data Type | Constraints / Attributes | Description |
| :--- | :--- | :--- | :--- |
| `id` | BigAutoField | Primary Key | Item ID |
| `title` | CharField(200) | | Item title |
| `description` | TextField | Blank, Default: `""` | Item summary |
| `quantity` | PositiveInteger | Default: `1` | Stock quantity |
| `is_active` | BooleanField | Default: `True` | Active flag |
| `created_at` | DateTimeField | `auto_now_add=True` | Creation timestamp |
| `updated_at` | DateTimeField | `auto_now=True` | Update timestamp |
