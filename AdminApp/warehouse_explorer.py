"""
AdminApp/warehouse_explorer.py
Core engine for the Interactive Virtual Warehouse Explorer (Lot SKU Grid).
Processes wholesale inventory lots and manifest items to deliver:
- Standardized 32-column SKU rows
- Aggregated financial intelligence (MSRP, Ask, Blended Liquidation Discount %)
- Brand distribution and % share of lot value
- Condition and category allocations
- Top 5-10 "Profit Drivers" spotlight
"""

import json
from lots.importer import clean_lot_product_item


def _safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("$", "").replace("€", "").replace("£", "").replace("₹", "").replace(",", "")
    if not s or s.lower() in ("nil", "none", "nan", "-", "n/a", "null"):
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _safe_int(val, default=1):
    if val is None:
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    s = str(val).strip().replace(",", "")
    if not s or s.lower() in ("nil", "none", "nan", "-", "n/a", "null"):
        return default
    try:
        f = float(s)
        return int(f)
    except (ValueError, TypeError):
        return default


def get_lot_warehouse_explorer_data(lot, items_override=None):
    """
    Extracts SKU items and aggregates warehouse analytics for a given Lot instance.
    Checks DB LotProduct records first, falling back to parsed manifest raw_data.
    If items_override is provided, uses those cleaned items directly (useful for previewing newly parsed spreadsheets).
    """
    from .models import LotProduct

    raw_items = []
    is_saved_to_db = False

    if items_override is not None and isinstance(items_override, list):
        raw_items = items_override
        is_saved_to_db = False
    else:
        # 1. Fetch from database LotProduct records
        db_products = list(LotProduct.objects.filter(lot=lot).order_by("id"))
        if db_products:
            is_saved_to_db = True
            for idx, p in enumerate(db_products, 1):
                p_data = p.raw_data if isinstance(p.raw_data, dict) else {}
                cleaned = clean_lot_product_item(p_data, row_counter=idx)
                if not cleaned:
                    cleaned = {
                        "s_no": idx,
                        "product_name": p.product_name or f"SKU Item #{idx}",
                        "product_description": "-",
                        "product_category": "-",
                        "subcategory": "-",
                        "brand": "-",
                        "model_part_number": p.product_id or "-",
                        "available_quantity": p.quantity or 1,
                        "original_price": "-",
                        "asking_price": "-",
                        "country_of_origin": "-",
                        "year_of_manufacture": "-",
                        "datasheet_certificate_link": "-",
                        "gross_weight_per_unit": "-",
                        "length": "-",
                        "width": "-",
                        "height": "-",
                        "measurement_unit": "-",
                        "stock_age": "-",
                        "tested_and_verified": "-",
                        "functional_status": "-",
                        "visible_damage": "-",
                        "missing_parts": "-",
                        "warranty_available": "-",
                        "safety_certificate_available": "-",
                        "certificate_type": "-",
                        "regulatory_approval": "-",
                        "hazardous_material": "-",
                        "recyclable": "-",
                        "estimated_product_life_remaining": "-",
                        "seller_custom_field_1": "-",
                        "seller_custom_field_2": "-",
                    }
                raw_items.append(cleaned)

    # 2. Fallback to lot.raw_data parsed manifest items
    if not raw_items and isinstance(lot.raw_data, dict):
        for key in ("products", "manifest_items", "parsed_items", "preview_items", "products_list"):
            candidate = lot.raw_data.get(key)
            if isinstance(candidate, list) and candidate:
                for idx, r in enumerate(candidate, 1):
                    cleaned = clean_lot_product_item(r, row_counter=idx)
                    if cleaned:
                        raw_items.append(cleaned)
                if raw_items:
                    is_saved_to_db = bool(lot.raw_data.get("is_saved_to_db"))
                    break

    # 3. Analyze and enrich each SKU item
    items = []
    brand_counts = {}
    condition_counts = {}
    category_counts = {}

    sum_line_msrp = 0.0
    sum_line_ask = 0.0
    total_units = 0

    for idx, item in enumerate(raw_items, 1):
        qty = _safe_int(item.get("available_quantity"), default=1)
        if qty <= 0:
            qty = 1

        orig_price = _safe_float(item.get("original_price"), default=0.0)
        ask_price = _safe_float(item.get("asking_price"), default=0.0)

        line_msrp = round(orig_price * qty, 2) if orig_price > 0 else 0.0
        line_ask = round(ask_price * qty, 2) if ask_price > 0 else 0.0

        if orig_price > 0 and ask_price > 0 and ask_price < orig_price:
            unit_savings = round(orig_price - ask_price, 2)
            sku_discount_pct = round(((orig_price - ask_price) / orig_price) * 100, 1)
        else:
            unit_savings = 0.0
            sku_discount_pct = 0.0

        sum_line_msrp += line_msrp
        sum_line_ask += line_ask
        total_units += qty

        # Copy item and attach analytics helpers
        enriched = dict(item)
        enriched["s_no"] = enriched.get("s_no") or idx
        enriched["qty_num"] = qty
        enriched["orig_price_num"] = orig_price
        enriched["ask_price_num"] = ask_price
        enriched["line_msrp"] = line_msrp
        enriched["line_ask"] = line_ask
        enriched["unit_savings"] = unit_savings
        enriched["sku_discount_pct"] = sku_discount_pct
        items.append(enriched)

        # Brand aggregation
        raw_brand = str(item.get("brand") or "").strip()
        brand_key = raw_brand if raw_brand and raw_brand != "-" and raw_brand.lower() not in ("none", "nan", "nil") else "General / Unbranded"
        if brand_key not in brand_counts:
            brand_counts[brand_key] = {"brand": brand_key, "skus": 0, "units": 0, "total_value": 0.0}
        brand_counts[brand_key]["skus"] += 1
        brand_counts[brand_key]["units"] += qty
        brand_counts[brand_key]["total_value"] += line_msrp

        # Condition aggregation
        raw_cond = str(item.get("functional_status") or item.get("stock_age") or "Surplus").strip()
        cond_key = raw_cond if raw_cond and raw_cond != "-" else "Surplus"
        if cond_key not in condition_counts:
            condition_counts[cond_key] = {"condition": cond_key, "skus": 0, "units": 0}
        condition_counts[cond_key]["skus"] += 1
        condition_counts[cond_key]["units"] += qty

        # Category aggregation
        raw_cat = str(item.get("product_category") or "General").strip()
        cat_key = raw_cat if raw_cat and raw_cat != "-" else "General"
        if cat_key not in category_counts:
            category_counts[cat_key] = {"category": cat_key, "skus": 0, "units": 0, "total_value": 0.0}
        category_counts[cat_key]["skus"] += 1
        category_counts[cat_key]["units"] += qty
        category_counts[cat_key]["total_value"] += line_msrp

    # 4. Fallback values from parent Lot if SKUs lacked pricing
    lot_msrp = _safe_float(getattr(lot, "total_est_retail_value_msrp", 0.0))
    lot_ask = _safe_float(getattr(lot, "ask_price_surplus_payout", 0.0))

    effective_msrp = sum_line_msrp if sum_line_msrp > 0 else lot_msrp
    effective_ask = sum_line_ask if sum_line_ask > 0 else lot_ask

    if effective_msrp > 0 and effective_ask > 0 and effective_ask < effective_msrp:
        blended_discount = round(((effective_msrp - effective_ask) / effective_msrp) * 100, 1)
    else:
        blended_discount = 0.0

    # 5. Formatted Brand breakdown sorted by volume descending
    brand_list = list(brand_counts.values())
    brand_list.sort(key=lambda b: (b["units"], b["skus"]), reverse=True)
    for b in brand_list:
        b["total_value"] = round(b["total_value"], 2)
        b["pct_of_value"] = round((b["units"] / total_units * 100), 1) if total_units > 0 else 0.0
        b["pct_of_units"] = round((b["units"] / total_units * 100), 1) if total_units > 0 else 0.0

    # Condition breakdown list
    condition_list = list(condition_counts.values())
    condition_list.sort(key=lambda c: c["skus"], reverse=True)

    # Category breakdown list
    category_list = list(category_counts.values())
    category_list.sort(key=lambda c: (c["units"], c["skus"]), reverse=True)
    for c in category_list:
        c["total_value"] = round(c["total_value"], 2)
        c["pct_of_value"] = round((c["units"] / total_units * 100), 1) if total_units > 0 else 0.0

    # 6. Top Inventory SKUs Spotlight (Ranked by available unit volume)
    top_candidates = sorted(items, key=lambda itm: itm.get("qty_num", 0), reverse=True)
    top_profit_drivers = top_candidates[:6] if top_candidates else items[:6]


    return {
        "success": True,
        "lot_id": lot.id,
        "lot_number": lot.lot_number,
        "lot_title": lot.title or lot.lot_number,
        "currency": getattr(lot, "currency", "USD") or "USD",
        "file_url": lot.file.url if getattr(lot, "file", None) and hasattr(lot.file, "url") and lot.file else getattr(lot, "file_url", None),
        "is_saved_to_db": is_saved_to_db,
        "summary": {
            "total_skus": len(items),
            "total_units": total_units,
            "total_msrp": round(effective_msrp, 2),
            "total_ask": round(effective_ask, 2),
            "blended_discount_pct": blended_discount,
            "total_brands": len(brand_list),
            "total_categories": len(category_list),
        },
        "brand_breakdown": brand_list,
        "condition_breakdown": condition_list,
        "category_breakdown": category_list,
        "top_profit_drivers": top_profit_drivers,
        "items": items,
    }
