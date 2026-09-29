# Surplus Platform Database Structure & Data Guide

This document explains the data structure of the **Surplus** platform in clear, simple terms. It describes how information about users, products, categories, bulk lots, seller submissions, and website content is stored and organized.

---

## 💡 Overview of How the Platform Works

```
                     ┌────────────────────────────────────────┐
                     │          Categories & Brands           │
                     └───────────────────┬────────────────────┘
                                         │
                                         ▼
┌────────────────────────┐      ┌─────────────────┐      ┌────────────────────────┐
│     Sellers / Users    │ ───► │    Products     │ ◄─── │    Buyers & Offers     │
└────────────────────────┘      └────────┬────────┘      └────────────────────────┘
            │                            │
            ▼                            ▼
┌────────────────────────┐      ┌─────────────────┐
│ Bulk Lot Excel Uploads │ ───► │  Lot Packages   │
└────────────────────────┘      └─────────────────┘
```

1. **Users & Authentication**: Stores accounts for platform Admins, Sellers, and Buyers, along with security verification codes (OTPs).
2. **Product Catalog**: Organizes items into Main Categories and Sub-Categories.
3. **Products & Marketplace**: Manages single item listings, pricing rules, stock count, and images.
4. **Bulk Lots**: Stores large inventories sold together as a single batch/lot.
5. **Seller Submissions**: Holds new product and lot requests submitted by sellers until approved by an Admin.
6. **Website & Content Management (CMS)**: Powers custom web pages, SEO details, blog posts, partner brands, and popup banners.
7. **System & Pricing Controls**: Stores global operational fees, maintenance mode settings, and records of price changes.

---

## 1. Users & Security Module

### 1.1 Admin Accounts (`AdminDetails`)
Stores login accounts for platform managers and administrators.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `username` | Text | Admin login username |
| `email` | Email Address | Admin contact & notification email |
| `account_type` | Choice | Admin role (`SuperAdmin`, `Admin`, or `XLSX Admin`) |
| `status` | Yes / No | Account status (`Active` or `Disabled`) |
| `web_is_active` | Text | Controls site-wide operational mode (`live` or `maintenance`) |
| `created_at` | Date & Time | Date when the admin account was created |

---

### 1.2 Seller & Buyer Accounts (`VendorDetails`)
Stores accounts for platform users (Buyers, Sellers, or both).

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `username` | Text | Unique user handle or username |
| `email` | Email Address | User email address |
| `mobile_number` | Phone Number | Contact mobile number |
| `account_entity_type` | Choice | Type of business entity (`Individual` or `Company/Business`) |
| `company_name` | Text | Registered company or business name |
| `business_location` | Text | City, state, or country of operation |
| `category_interested`| List | Product categories the user is interested in buying or selling |
| `user_type` | Choice | User role (`Buyer`, `Seller`, or `Both`) |
| `status` | Yes / No | Account status (`Active` or `Disabled`) |
| `created_at` | Date & Time | Date when the account was registered |

---

### 1.3 Security OTP Codes (`VendorOTP` & `AdminPasswordResetOTP`)
Stores short-lived 6-digit verification codes sent via email for secure login and password resets.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `email` | Email Address | Recipient email address |
| `otp` | 6-Digit Code | Security code (e.g. `123456`) |
| `is_used` | Yes / No | Whether the code has already been redeemed |
| `created_at` | Date & Time | Time sent (codes expire after 10 minutes) |

---

## 2. Product Categories & Catalog

### 2.1 Top-Level Categories (`MainCategory`)
Primary product groupings (e.g., *Industrial Equipment*, *Electronics*, *Consumer Goods*).

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `name` | Text | Category title displayed on the website |
| `slug` | Web Address Slug | Friendly URL link (e.g., `industrial-equipment`) |
| `description` | Text | Brief overview of items under this category |
| `image` | Picture File | Category banner image |
| `is_active` | Yes / No | Controls whether category is visible to visitors |

---

### 2.2 Sub-Categories (`SubCategory`)
Specific categories nested under a Main Category (e.g., *Motors & Pumps* under *Industrial Equipment*).

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `main_category` | Category Link | Parent Main Category |
| `name` | Text | Sub-category title |
| `slug` | Web Address Slug | Friendly URL link |
| `description` | Text | Summary of sub-category contents |
| `image` | Picture File | Sub-category thumbnail picture |
| `is_active` | Yes / No | Controls visibility on the store |

---

## 3. Products & Bulk Lots Engine

### 3.1 Individual Marketplace Products (`Product`)
Individual items listed for sale on the marketplace.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `product_id` | Unique ID | Auto-generated product code (e.g., `PRO-00042`) |
| `product_name` | Text | Item title |
| `model_no` | Text | Model number, Part number, or SKU |
| `brand` | Text | Manufacturer or brand name |
| `description` | Text | Full item specifications & description |
| `liquidating_price` | Currency Amount | Base seller listing price |
| `current_price` | Currency Amount | Final selling price (Auto-calculated: `Base Price + 10% Markup`) |
| `previous_price` | Currency Amount | Original retail price or previous discounted price |
| `stock_quantity` | Whole Number | Available units in stock |
| `condition` | Text | Item state (e.g., *Brand New*, *Refurbished*, *Used*) |
| `inventory_location` | Text | Warehouse or storage location |
| `manufacturing_country`| Country Name | Country where the product was made |
| `manufacturing_year` | Year Number | Year of production |
| `dimensions` | Text | Size and physical dimensions |
| `currency` | Currency Code | Currency (Default: `USD`) |
| `warranty` | Text | Warranty coverage details |
| `third_party_certificate`| Document File | Uploaded quality certificate or inspection report |
| `image` | Picture File | Main product featured image |
| `enquiry_status` | Choice | Review state (`Pending`, `Approved`, or `Declined`) |
| `is_active` | Yes / No | Visible for sale on website (`Yes` or `No`) |

---

### 3.2 Product Gallery Images (`ProductImage`)
Extra photos attached to a product listing.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `product` | Product Link | The product this image belongs to |
| `image` | Picture File | High-resolution product photo |
| `uploaded_at` | Date & Time | Upload date |

---

### 3.3 Bulk Lot Packages (`Lot` & `LotProduct`)
Large inventories or inventory packages sold as one bulk batch.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `lot_number` | Unique ID | Lot code (e.g., `LOT-00015`) |
| `title` | Text | Bulk package title |
| `description` | Text | Manifest summary and description |
| `total_price` | Currency Amount | Total asking price for the whole package |
| `inventory_location` | Text | Stock warehouse location |
| `file` | Excel / File | Original uploaded inventory spreadsheet (.xlsx) |
| `enquiry_status` | Choice | Review state (`Pending`, `Approved`, or `Declined`) |
| `is_active` | Yes / No | Controls if lot is visible for purchase |

---

## 4. Seller Submissions (Enquiries)

### 4.1 Seller Item Submissions (`SellerProductEnquiry`)
Forms submitted by sellers wanting to list a single product. Held in review until approved by an Admin.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `product_id` | Unique ID | Reference code (e.g., `PRO-00102`) |
| `vendor` | User Link | The seller submitting the item |
| `title` | Text | Item title |
| `price` | Currency Amount | Expected selling price |
| `stock_quantity` | Whole Number | Available units |
| `brand` | Text | Brand name |
| `reason_to_sell` | Text | Reason for liquidating stock |
| `enquiry_status` | Choice | Admin decision (`Pending`, `Approved`, `Declined`) |

---

### 4.2 Seller Bulk Excel Submissions (`LotBatchEnquiry`)
Spreadsheets uploaded by sellers containing hundreds of inventory items.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `batch_id` | Unique ID | Batch code (e.g., `BAT-00008`) |
| `uploaded_by` | User Link | The seller who uploaded the file |
| `file` | Excel Spreadsheet | Uploaded .xlsx / .csv document |
| `total_price` | Currency Amount | Total package value |
| `enquiry_status` | Choice | Admin decision (`Pending`, `Approved`, `Declined`) |

---

## 5. Website Content & Marketing (CMS)

### 5.1 Dynamic Pages (`ContentPage`)
Custom website pages like *Privacy Policy*, *Terms of Service*, *About Us*, and custom landing pages. Includes built-in Google SEO controls.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `title` | Text | Page title (e.g., *Terms and Conditions*) |
| `slug` | Web Link Slug | Page URL (e.g., `/terms-and-conditions/`) |
| `category` | Choice | Page type (`Policy`, `Help`, `Information`, `Custom`) |
| `content` | HTML / Text | Page body content |
| `meta_title` | Text | Google search result title |
| `meta_description` | Text | Google search description summary |
| `show_in_header` | Yes / No | Display link in the main navigation menu |
| `show_in_footer` | Yes / No | Display link in the website footer |
| `status` | Choice | Page status (`Published` or `Draft`) |

---

### 5.2 Articles & Blog Posts (`BlogPost`)
News and articles published on the platform blog.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `title` | Text | Article headline |
| `slug` | Web Link Slug | URL path for the article |
| `author` | Text | Author name |
| `content` | Text / Article | Article body text |
| `image` | Picture File | Cover image |
| `read_time` | Number (Minutes) | Estimated reading duration (e.g. 5 mins) |
| `total_reads` | Number | Total reader views count |
| `status` | Choice | State (`Published` or `Draft`) |

---

### 5.3 Partner Brands (`Brand`)
Logos of featured manufacturers and partner brands displayed on the homepage slider.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `name` | Text | Brand name |
| `image` | Picture File | Uploaded logo image |
| `redirect_link` | Web Address | Link opened when clicking on the brand logo |
| `order` | Number | Display priority order |
| `is_active` | Yes / No | Show on homepage slider |

---

### 5.4 Partnership Inquiries (`PartnershipEnquiry`)
Submissions from companies interested in B2B collaborations.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `name` | Text | Contact person name |
| `email` | Email Address | Contact email |
| `business_location` | Text | Company location |
| `partnership_interest`| Text | Subject / Area of collaboration |
| `collaboration_details`| Text | Message details |
| `status` | Choice | Follow-up status (`Pending`, `Reviewed`, `Contacted`) |

---

## 6. System Settings & Audit Logs

### 6.1 System Settings (`SystemSettings`)
Platform-wide rules controlled by Super Admins.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `operational_charge_percentage` | Percentage (%) | Default commission/markup rate added to product prices |
| `is_maintenance_mode` | Yes / No | Temporary maintenance switch (turns off public browsing) |
| `maintenance_message` | Text | Notice displayed to visitors when maintenance is active |

---

### 6.2 Price Change Audit History (`PriceAdjustmentLog`)
Logs every mass price change or fee adjustment made by admins, including backup snapshots for easy rollbacks.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `admin_name` | Text | Name of the admin who updated prices |
| `action_type` | Text | Operation description (e.g. *Increase Prices*, *Fee Update*) |
| `value` | Number | Adjustment value applied (e.g. `5%` or `$10`) |
| `affected_products_count`| Number | Total number of items updated |
| `backup_snapshot` | Data Snapshot | Saved price backup allowing instant undo/rollback |
| `created_at` | Date & Time | Timestamp of change |

---

### 6.3 Notification Popups (`PopupSetting`)
Announcement popups displayed on the admin portal dashboard.

| Field Name | Simple Data Type | Plain English Description |
| :--- | :--- | :--- |
| `title` | Text | Popup heading title |
| `message` | Text | Announcement message content |
| `popup_type` | Choice | Style (`info`, `warning`, `danger`, `promotion`) |
| `delay_minutes` | Number | Minutes before reminding closed popup again |
| `is_active` | Yes / No | Active status toggle |
