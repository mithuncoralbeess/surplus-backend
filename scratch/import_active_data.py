import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
import pandas as pd
from decimal import Decimal
from django.utils import timezone
from django.utils.text import slugify
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from AdminApp.models import Product, MainCategory, SubCategory, VendorDetails

print("Clearing existing Product records...")
Product.objects.all().delete()

print("Caching vendors from database...")
vendor_cache = {}
for v in VendorDetails.objects.all():
    if v.email:
        vendor_cache[v.email.strip().lower()] = v
print(f"Cached {len(vendor_cache)} vendors by email.")

excel_path = 'active data.xlsx'
print(f"Loading {excel_path}...")
df = pd.read_excel(excel_path)
print(f"Total rows in Excel: {len(df)}")

def clean_str(val, max_len=None):
    if pd.isna(val) or val is None:
        return ""
    val_str = str(val).strip()
    if val_str.lower() in ("nan", "none", "null"):
        return ""
    if max_len and len(val_str) > max_len:
        return val_str[:max_len]
    return val_str

def clean_decimal(val, default=Decimal("0.00")):
    if pd.isna(val) or val is None:
        return default
    try:
        d = Decimal(str(val)).quantize(Decimal("0.01"))
        return max(Decimal("0.00"), d) if default is not None else d
    except Exception:
        return default

def clean_int(val, default=0):
    if pd.isna(val) or val is None:
        return default
    try:
        res = int(float(val))
        return max(0, res)
    except Exception:
        return default

def clean_date(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val if isinstance(val, datetime.date) else val.date()
    try:
        dt = pd.to_datetime(val)
        return dt.date() if pd.notna(dt) else None
    except Exception:
        return None

def clean_datetime(val):
    if pd.isna(val) or val is None:
        return timezone.now()
    if isinstance(val, datetime.datetime):
        return timezone.make_aware(val) if timezone.is_naive(val) else val
    try:
        dt = pd.to_datetime(val)
        if pd.notna(dt):
            dt_obj = dt.to_pydatetime()
            return timezone.make_aware(dt_obj) if timezone.is_naive(dt_obj) else dt_obj
    except Exception:
        pass
    return timezone.now()

category_cache = {}
subcategory_cache = {}

def get_category(cat_name, subcat_name):
    cat_name = clean_str(cat_name, max_len=150)
    subcat_name = clean_str(subcat_name, max_len=150)
    
    cat_obj = None
    subcat_obj = None
    
    if cat_name:
        if cat_name not in category_cache:
            slug = slugify(cat_name) or "cat"
            base_slug = slug[:140]
            counter = 1
            while MainCategory.objects.filter(slug=slug).exclude(name=cat_name).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            c_obj, _ = MainCategory.objects.get_or_create(
                name=cat_name,
                defaults={'slug': slug}
            )
            category_cache[cat_name] = c_obj
        cat_obj = category_cache[cat_name]
        
    if cat_obj and subcat_name:
        cache_key = (cat_name, subcat_name)
        if cache_key not in subcategory_cache:
            sub_slug = slugify(f"{cat_name}-{subcat_name}") or "subcat"
            base_sub_slug = sub_slug[:140]
            counter = 1
            while SubCategory.objects.filter(slug=sub_slug).exclude(main_category=cat_obj, name=subcat_name).exists():
                sub_slug = f"{base_sub_slug}-{counter}"
                counter += 1
            sc_obj, _ = SubCategory.objects.get_or_create(
                main_category=cat_obj,
                name=subcat_name,
                defaults={'slug': sub_slug}
            )
            subcategory_cache[cache_key] = sc_obj
        subcat_obj = subcategory_cache[cache_key]
        
    return cat_obj, subcat_obj

products_to_create = []

for idx, row in df.iterrows():
    prod_code = clean_str(row.get('Product Code'), max_len=30)
    prod_name = clean_str(row.get('Product Name'), max_len=255)
    if not prod_name and not prod_code:
        continue
        
    cat_obj, subcat_obj = get_category(row.get('Category'), row.get('Subcategory'))
    
    brand = clean_str(row.get('Brand'), max_len=255)
    model_no = clean_str(row.get('Model / Part No'), max_len=255)
    
    # Original Price -> liquidating_price
    liquidating_price = clean_decimal(row.get('Original Price'), default=Decimal("0.00"))
    
    # Market Price -> previous_price
    previous_price = clean_decimal(row.get('Market Price'), default=None)
    
    # Price -> current_price
    excel_price = clean_decimal(row.get('Price'), default=None)
    if excel_price is not None and excel_price > Decimal("0.00"):
        current_price = excel_price
    elif liquidating_price > Decimal("0.00"):
        current_price = (liquidating_price * Decimal("1.10")).quantize(Decimal("0.01"))
    else:
        current_price = Decimal("0.00")
        
    currency = clean_str(row.get('Currency'), max_len=10) or "USD"
    stock_qty = clean_int(row.get('Quantity'), default=0)
    condition = clean_str(row.get('Condition'), max_len=255)
    description = clean_str(row.get('Description'))
    mfg_country = clean_str(row.get('Manufacturing Country'), max_len=100)
    warranty = clean_str(row.get('Warranty'), max_len=255)
    dimensions = clean_str(row.get('Dimensions'), max_len=100)
    expiry_date = clean_date(row.get('Expiry Date'))
    reason_to_sell = clean_str(row.get('Reason to Sell'))
    created_at = clean_datetime(row.get('Date Added'))
    
    ex_countries_raw = clean_str(row.get('Excluded Countries'))
    excluded_countries = [c.strip() for c in ex_countries_raw.split(',')] if ex_countries_raw else []
    
    featured_img_url = clean_str(row.get('Featured Image URL'))
    third_party_cert = clean_str(row.get('Third Party Certificate'))
    documents = clean_str(row.get('Documents'))
    
    email = clean_str(row.get('Email')).lower()
    vendor_obj = vendor_cache.get(email) if email else None
    
    raw_data = {}
    if featured_img_url:
        raw_data['featured_image_url'] = featured_img_url
    if third_party_cert:
        raw_data['third_party_certificate'] = third_party_cert
    if documents:
        raw_data['documents'] = documents
    
    if not prod_code:
        prod_code = f"PRO-{idx+1:05d}"
    else:
        prod_code = prod_code[:30]

    p = Product(
        product_id=prod_code,
        vendor=vendor_obj,
        product_name=prod_name or "Unnamed Product",
        category=cat_obj,
        subcategory=subcat_obj,
        brand=brand,
        model_no=model_no,
        liquidating_price=liquidating_price,
        previous_price=previous_price,
        current_price=current_price,
        currency=currency,
        stock_quantity=stock_qty,
        condition=condition,
        description=description,
        manufacturing_country=mfg_country,
        warranty=warranty,
        dimensions=dimensions,
        expiry_date=expiry_date,
        reason_to_sell=reason_to_sell,
        excluded_countries=excluded_countries,
        raw_data=raw_data,
        is_active=True,
        enquiry_status='APPROVED',
        created_at=created_at,
        date_approved=created_at
    )
    if featured_img_url:
        p.image.name = featured_img_url[:100]
    
    products_to_create.append(p)

print(f"Prepared {len(products_to_create)} products for saving...")

# Bulk create all products
batch_size = 2000
for i in range(0, len(products_to_create), batch_size):
    batch = products_to_create[i:i + batch_size]
    Product.objects.bulk_create(batch)
    print(f"Bulk saved products {i + 1} to {min(i + batch_size, len(products_to_create))}...")

print(f"Import completed successfully! Total products in DB: {Product.objects.count()}")

