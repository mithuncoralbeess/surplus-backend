"""
SEO metadata generator for Surplus Market single-product APIs.
Generates structured SEO payloads (`meta_title`, `meta_description`, `url`,
`slug`, `h1`, `product_title`, `short_description`, `product_description`)
from Product records or Typesense document dictionaries with zero DB overhead.
"""

import re
from django.utils.html import strip_tags
from django.utils.text import slugify


def _seo_slug(text: str) -> str:
    if not text:
        return ""
    cleaned = str(text).replace("&", " and ").replace("/", " ")
    return slugify(cleaned)


def _clean_text(text: str) -> str:
    if not text:
        return ""
    plain = strip_tags(str(text))
    return " ".join(plain.split()).strip()


def _extract_key_feature(description: str, max_len: int = 115) -> str:
    plain = _clean_text(description)
    if not plain:
        return ""
    # Take first sentence if it fits cleanly
    first_sent = re.split(r"(?<=[.!?])\s+", plain)[0].strip().rstrip(".!?")
    if len(first_sent) <= max_len:
        return first_sent
    trimmed = first_sent[:max_len].rsplit(" ", 1)[0].strip(" ,;:-")
    return trimmed


def build_product_seo_data(
    *,
    product_name: str = "",
    product_code: str = "",
    brand: str = "",
    category_name: str = "",
    category_slug: str = "",
    subcategory_name: str = "",
    model_no: str = "",
    description: str = "",
    quantity=None,
    warranty: str = "",
    inventory_country: str = "",
    manufacturing_country: str = "",
    reason_to_sell: str = "",
) -> dict:
    name = _clean_text(product_name) or "Surplus Product"
    brand_str = _clean_text(brand)
    cat_name = _clean_text(category_name)
    sub_name = _clean_text(subcategory_name)
    model_str = _clean_text(model_no)
    # Inside SEO, prefer Model No. / Part Number whenever available; fall back to product_code
    code = model_str or _clean_text(product_code)
    desc_clean = _clean_text(description)
    warranty_str = _clean_text(warranty)
    inv_country = _clean_text(inventory_country)
    mfg_country = _clean_text(manufacturing_country)
    reason_str = _clean_text(reason_to_sell)

    # 1. H1 / Product Title: Product Name + Product Code
    h1_title = f"{name} - {code}" if code else name

    # 2. Meta Title: Buy + Product Name + Product Code | Surplus Market
    meta_title = f"Buy {h1_title} | Surplus Market"

    # 3. URL: /buy/product/[category]/[brand]-[product-name]-[product-code]
    cat_seg = _seo_slug(category_slug or category_name) or "products"
    slug_parts = []
    brand_norm = re.sub(r"[^a-z0-9]", "", brand_str.lower())
    name_norm = re.sub(r"[^a-z0-9]", "", name.lower())
    if brand_str and (not brand_norm or not name_norm.startswith(brand_norm)):
        slug_parts.append(brand_str)
    slug_parts.append(name)
    if code and code.lower() not in name.lower():
        slug_parts.append(code)
    item_slug = _seo_slug(" ".join(slug_parts)) or _seo_slug(code) or "product"
    seo_url = f"/buy/product/{cat_seg}/{item_slug}"

    # 4. Short Product Description (1-2 sentences with product name, key feature, brand, and code)
    lead_name = f"{brand_str} {name}" if (brand_str and (not brand_norm or not name_norm.startswith(brand_norm))) else name
    lead_full = f"{lead_name} - {code}" if code else lead_name
    feature_snippet = _extract_key_feature(desc_clean)

    if feature_snippet and feature_snippet.lower() not in lead_full.lower():
        short_desc = f"Buy the {lead_full} featuring {feature_snippet}."
    elif sub_name or cat_name:
        type_label = sub_name or cat_name
        short_desc = f"Buy the {lead_full} ({type_label}) in commercial surplus inventory."
    else:
        short_desc = f"Buy the {lead_full} in verified wholesale surplus stock."

    loc_note = f" ready for dispatch from {inv_country}" if inv_country else ""
    qty_int = int(quantity) if isinstance(quantity, (int, float)) or (isinstance(quantity, str) and quantity.isdigit()) else None
    if qty_int and qty_int > 0:
        short_desc += f" {qty_int:,} units available{loc_note} on Surplus Market."
    else:
        short_desc += f" Verified B2B stock{loc_note} on Surplus Market."

    # 5. Detailed Product Description (product type, features, compatibility/specs, use case, product code)
    detail_sections = []
    product_type_str = " > ".join(p for p in (cat_name, sub_name) if p) or "Commercial Surplus Inventory"

    intro = f"The {lead_full} is a {product_type_str} listing available for wholesale B2B procurement on Surplus Market."
    if brand_str:
        intro += f" Manufactured under the {brand_str} brand"
        if model_str:
            intro += f" (Model / Part No: {model_str})"
        intro += "."
    elif model_str:
        intro += f" Model / Part No: {model_str}."
    detail_sections.append(intro)

    if desc_clean:
        detail_sections.append(f"Product Specifications & Features: {desc_clean}")

    logistics_parts = []
    if code:
        logistics_parts.append(f"Product Code: {code}")
    if qty_int and qty_int > 0:
        logistics_parts.append(f"Available Quantity: {qty_int:,} units")
    if mfg_country:
        logistics_parts.append(f"Country of Manufacture: {mfg_country}")
    if inv_country:
        logistics_parts.append(f"Stock Location: {inv_country}")
    if warranty_str:
        logistics_parts.append(f"Warranty: {warranty_str}")

    use_case = reason_str or "overstock clearance, commercial supply, and wholesale resale"
    detail_sections.append(
        f"Commercial Use Case & Availability: Ideal for {use_case.lower() if reason_str else use_case}. "
        + (" | ".join(logistics_parts) + "." if logistics_parts else "")
    )

    product_description = "\n\n".join(detail_sections)

    return {
        "meta_title": meta_title,
        "meta_description": short_desc,
        "url": seo_url,
        "slug": item_slug,
        "h1": h1_title,
        "product_title": h1_title,
        "short_description": short_desc,
        "product_description": product_description,
    }


def get_product_seo(product) -> dict:
    """Builds the SEO object for a Product model instance or serialized dict."""
    if isinstance(product, dict):
        cat = product.get("category")
        sub = product.get("subcategory")
        cat_name = cat.get("name", "") if isinstance(cat, dict) else (cat or "")
        cat_slug = cat.get("slug", "") if isinstance(cat, dict) else ""
        sub_name = sub.get("name", "") if isinstance(sub, dict) else (sub or "")
        return build_product_seo_data(
            product_name=product.get("product_name") or product.get("title") or "",
            product_code=product.get("product_code") or product.get("product_id") or product.get("sku") or "",
            brand=product.get("brand") or product.get("brand_name") or "",
            category_name=cat_name,
            category_slug=cat_slug,
            subcategory_name=sub_name,
            model_no=product.get("model_no") or product.get("model_number") or "",
            description=product.get("description") or "",
            quantity=product.get("quantity"),
            warranty=product.get("warranty") or "",
            inventory_country=product.get("inventory_country") or "",
            manufacturing_country=product.get("manufacturing_country") or "",
            reason_to_sell=product.get("reason_to_sell") or "",
        )

    cat_obj = getattr(product, "category", None)
    sub_obj = getattr(product, "subcategory", None)
    return build_product_seo_data(
        product_name=getattr(product, "product_name", "") or "",
        product_code=getattr(product, "product_code", "") or getattr(product, "product_id", "") or "",
        brand=getattr(product, "brand_name", "") or getattr(product, "brand", "") or "",
        category_name=getattr(cat_obj, "name", "") if cat_obj else "",
        category_slug=getattr(cat_obj, "slug", "") if cat_obj else "",
        subcategory_name=getattr(sub_obj, "name", "") if sub_obj else "",
        model_no=getattr(product, "model_no", "") or "",
        description=getattr(product, "description", "") or "",
        quantity=getattr(product, "quantity", None),
        warranty=getattr(product, "warranty", "") or "",
        inventory_country=getattr(product, "inventory_country", "") or "",
        manufacturing_country=getattr(product, "manufacturing_country", "") or "",
        reason_to_sell=getattr(product, "reason_to_sell", "") or "",
    )

