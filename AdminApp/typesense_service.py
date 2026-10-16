"""
Typesense Intelligent Search Service for Surplus Market.
Handles connection pooling, collection schema lifecycle, document normalization,
transactional outbox fallback, multi-currency conversion, and faceted search queries.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import typesense
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# Currency conversion rates relative to USD (1 USD = rate target)
# Synchronized with frontend CurrencyContext.tsx
RATES_TO_USD: Dict[str, float] = {
    "USD": 1.0,
    "AED": 3.67,
    "SAR": 3.75,
    "QAR": 3.64,
    "INR": 83.5,
    "EUR": 0.92,
    "GBP": 0.79,
}


def to_usd(amount: Optional[Any], currency: Optional[str]) -> float:
    """
    Normalizes an amount in any supported marketplace currency to USD.
    """
    if amount is None:
        return 0.0
    try:
        val = Decimal(str(amount))
        curr = (currency or "USD").upper().strip()
        rate = Decimal(str(RATES_TO_USD.get(curr, 1.0)))
        if rate <= 0:
            rate = Decimal("1.0")
        usd_val = val / rate
        return float(round(usd_val, 2))
    except Exception as e:
        logger.debug(f"Error converting {amount} {currency} to USD: {e}")
        return 0.0


def from_usd(amount_usd: Optional[Any], target_currency: Optional[str]) -> float:
    """
    Converts a USD amount to the target marketplace currency.
    """
    if amount_usd is None:
        return 0.0
    try:
        val = Decimal(str(amount_usd))
        curr = (target_currency or "USD").upper().strip()
        rate = Decimal(str(RATES_TO_USD.get(curr, 1.0)))
        res = val * rate
        return float(round(res, 2))
    except Exception:
        return float(amount_usd)


_typesense_client: Optional[typesense.Client] = None


def get_typesense_client() -> typesense.Client:
    """
    Singleton factory for official Typesense Python Client.
    Configured via Django settings (backed by environment variables).
    """
    global _typesense_client
    if _typesense_client is None:
        host = getattr(settings, "TYPESENSE_HOST", "localhost")
        port = str(getattr(settings, "TYPESENSE_PORT", 8108))
        protocol = getattr(settings, "TYPESENSE_PROTOCOL", "http")
        api_key = getattr(settings, "TYPESENSE_API_KEY", "surplus_typesense_dev_key_123")
        timeout = float(getattr(settings, "TYPESENSE_TIMEOUT", 3.0))

        _typesense_client = typesense.Client({
            "nodes": [{
                "host": host,
                "port": port,
                "protocol": protocol,
            }],
            "api_key": api_key,
            "connection_timeout_seconds": timeout,
        })
    return _typesense_client


def get_collection_name() -> str:
    return getattr(settings, "TYPESENSE_COLLECTION_NAME", "surplus_listings")


def is_typesense_available() -> Tuple[bool, str]:
    """
    Quick non-blocking healthcheck to determine if Typesense is reachable.
    """
    try:
        client = get_typesense_client()
        # Ping the /health endpoint or list collections
        client.operations.is_healthy()
        return True, "Healthy"
    except Exception as e:
        err_msg = str(e)
        logger.warning(f"Typesense health check failed: {err_msg}")
        return False, err_msg


def get_collection_schema() -> Dict[str, Any]:
    """
    Unified marketplace listings schema covering both individual Products and wholesale Lots.
    """
    return {
        "name": get_collection_name(),
        "fields": [
            {"name": "id", "type": "string"},
            {"name": "item_type", "type": "string", "facet": True},
            {"name": "is_lot", "type": "bool", "facet": True},
            {"name": "db_id", "type": "int64"},
            {"name": "title", "type": "string"},
            {"name": "product_name", "type": "string", "optional": True},
            {"name": "description", "type": "string", "optional": True},
            {"name": "category", "type": "string", "facet": True, "optional": True},
            {"name": "category_slug", "type": "string", "facet": True, "optional": True},
            {"name": "subcategory", "type": "string", "facet": True, "optional": True},
            {"name": "subcategory_slug", "type": "string", "facet": True, "optional": True},
            {"name": "brand", "type": "string", "facet": True, "optional": True},
            {"name": "model_no", "type": "string", "optional": True},
            {"name": "condition", "type": "string", "facet": True, "optional": True},
            {"name": "country", "type": "string", "facet": True, "optional": True},
            {"name": "city", "type": "string", "facet": True, "optional": True},
            {"name": "location", "type": "string", "facet": True, "optional": True},
            {"name": "currency", "type": "string", "facet": True},
            {"name": "price", "type": "float"},
            {"name": "price_usd", "type": "float", "facet": True, "sort": True},
            {"name": "msrp", "type": "float", "optional": True},
            {"name": "msrp_usd", "type": "float", "optional": True},
            {"name": "quantity", "type": "int32", "optional": True},
            {"name": "unit_type", "type": "string", "optional": True},
            {"name": "pallet_count", "type": "int32", "optional": True},
            {"name": "distinct_skus", "type": "int32", "optional": True},
            {"name": "source_type", "type": "string", "facet": True, "optional": True},
            {"name": "is_featured", "type": "bool", "facet": True, "optional": True},
            {"name": "is_best_selling", "type": "bool", "facet": True, "optional": True},
            {"name": "is_new_arrival", "type": "bool", "facet": True, "optional": True},
            {"name": "image", "type": "string", "optional": True},
            {"name": "images", "type": "string[]", "optional": True},
            {"name": "listing_url", "type": "string", "optional": True},
            {"name": "sku", "type": "string", "optional": True},
            {"name": "enquiry_status", "type": "string", "facet": True},
            {"name": "is_active", "type": "bool", "facet": True},
            {"name": "created_at", "type": "int64", "sort": True},
            {"name": "views_count", "type": "int32", "optional": True, "sort": True},
        ],
        "default_sorting_field": "created_at"
    }


def init_collection(recreate: bool = False) -> bool:
    """
    Initializes or updates the Typesense collection schema.
    If recreate is True, drops the existing collection before creating.
    """
    client = get_typesense_client()
    coll_name = get_collection_name()

    try:
        existing_collections = [c["name"] for c in client.collections.retrieve()]
        if coll_name in existing_collections:
            if recreate:
                logger.warning(f"Dropping existing Typesense collection: {coll_name}")
                client.collections[coll_name].delete()
            else:
                logger.info(f"Typesense collection {coll_name} already exists.")
                return True

        logger.info(f"Creating Typesense collection: {coll_name}")
        schema = get_collection_schema()
        client.collections.create(schema)
        logger.info(f"Typesense collection {coll_name} created successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Typesense collection {coll_name}: {e}")
        return False


def product_to_document(product) -> Optional[Dict[str, Any]]:
    """
    Transforms a Django Product model instance into a Typesense search document.
    Enforces publication invariant: must be is_active=True and enquiry_status == 'APPROVED'.
    """
    if not product.is_active or str(product.enquiry_status).strip().upper() != "APPROVED":
        return None

    # Resolve images
    all_imgs = []
    try:
        all_imgs = [img.url for img in product.images.all() if getattr(img, "url", None)]
    except Exception:
        pass
    main_img = all_imgs[0] if all_imgs else ""

    # Category & Subcategory
    cat_name = product.category.name if product.category else ""
    cat_slug = product.category.slug if product.category else ""
    sub_name = product.subcategory.name if product.subcategory else ""
    sub_slug = product.subcategory.slug if product.subcategory else ""

    # Price & MSRP calculation
    raw_price = product.liquidating_price or product.current_price or 0.0
    raw_msrp = product.msrp or 0.0
    curr = (product.currency or "USD").upper().strip()

    price_f = float(raw_price)
    msrp_f = float(raw_msrp)
    price_usd_f = to_usd(raw_price, curr)
    msrp_usd_f = to_usd(raw_msrp, curr) if raw_msrp else price_usd_f

    # Created at timestamp (epoch seconds)
    if product.created_at:
        dt = product.created_at if product.created_at.tzinfo else product.created_at.replace(tzinfo=timezone.utc)
        created_epoch = int(dt.timestamp())
    else:
        created_epoch = int(datetime.now(timezone.utc).timestamp())

    # Locations
    loc = product.inventory_location or ""
    country = product.manufacturing_country or ""
    city = ""
    if loc and not country:
        country = loc

    return {
        "id": f"product_{product.id}",
        "item_type": "product",
        "is_lot": False,
        "db_id": int(product.id),
        "title": product.product_name or "",
        "product_name": product.product_name or "",
        "description": product.description or "",
        "category": cat_name,
        "category_slug": cat_slug,
        "subcategory": sub_name,
        "subcategory_slug": sub_slug,
        "brand": product.brand_name or "",
        "model_no": product.model_no or "",
        "condition": "Surplus",
        "country": country,
        "city": city,
        "location": loc or country,
        "currency": curr,
        "price": price_f,
        "price_usd": price_usd_f,
        "msrp": msrp_f,
        "msrp_usd": msrp_usd_f,
        "quantity": int(product.quantity or 1),
        "unit_type": "units",
        "pallet_count": 0,
        "distinct_skus": 1,
        "source_type": product.intake_channel or "SURPLUS",
        "is_featured": bool(product.is_featured),
        "is_best_selling": bool(product.is_best_selling),
        "is_new_arrival": bool(product.is_new_arrival),
        "image": main_img,
        "images": all_imgs,
        "listing_url": f"/product/{product.product_id or product.id}",
        "sku": product.product_id or "",
        "enquiry_status": str(product.enquiry_status).strip().upper(),
        "is_active": bool(product.is_active),
        "created_at": created_epoch,
        "views_count": int(product.views_count or 0),
    }


def lot_to_document(lot) -> Optional[Dict[str, Any]]:
    """
    Transforms a Django Lot model instance into a Typesense search document.
    Enforces publication invariant: must be is_active=True and enquiry_status == 'approved'.
    """
    if not lot.is_active or str(lot.enquiry_status).strip().lower() != "approved":
        return None

    # Warehouse images
    imgs = []
    if isinstance(lot.warehouse_images, list):
        imgs = [str(x) for x in lot.warehouse_images if x]
    main_img = imgs[0] if imgs else ""

    # Category allocations
    cat_name = ""
    cat_slug = ""
    if isinstance(lot.category_allocations, list) and lot.category_allocations:
        first_cat = lot.category_allocations[0]
        if isinstance(first_cat, dict):
            cat_name = first_cat.get("category") or first_cat.get("name") or ""
        elif isinstance(first_cat, str):
            cat_name = first_cat
    elif isinstance(lot.category_allocations, dict):
        cat_name = lot.category_allocations.get("category") or ""

    # Price & MSRP calculation
    raw_price = lot.ask_price_surplus_payout or 0.0
    raw_msrp = lot.total_est_retail_value_msrp or 0.0
    curr = (lot.currency or "USD").upper().strip()

    price_f = float(raw_price)
    msrp_f = float(raw_msrp)
    price_usd_f = to_usd(raw_price, curr)
    msrp_usd_f = to_usd(raw_msrp, curr) if raw_msrp else price_usd_f

    # Created at timestamp
    if lot.created_at:
        dt = lot.created_at if lot.created_at.tzinfo else lot.created_at.replace(tzinfo=timezone.utc)
        created_epoch = int(dt.timestamp())
    else:
        created_epoch = int(datetime.now(timezone.utc).timestamp())

    # Location details
    country = getattr(lot, "inventory_country", None) or lot.inventory_location or ""
    city = getattr(lot, "inventory_city", None) or ""
    loc_combined = f"{city}, {country}".strip(" ,") if city else country

    # Units and pallets
    total_units = int(lot.total_units_quantity or 0)
    pallets = int(lot.pallet_count or 0)
    distinct_skus = int(lot.number_of_distinct_skus or 1)

    return {
        "id": f"lot_{lot.id}",
        "item_type": "lot",
        "is_lot": True,
        "db_id": int(lot.id),
        "title": lot.title or f"Lot #{lot.lot_number}",
        "product_name": lot.title or "",
        "description": lot.description or "",
        "category": cat_name,
        "category_slug": cat_slug,
        "subcategory": "",
        "subcategory_slug": "",
        "brand": lot.key_brands_included or "",
        "model_no": "",
        "condition": lot.condition or "Liquidation Lot",
        "country": country,
        "city": city,
        "location": loc_combined,
        "currency": curr,
        "price": price_f,
        "price_usd": price_usd_f,
        "msrp": msrp_f,
        "msrp_usd": msrp_usd_f,
        "quantity": total_units,
        "unit_type": lot.primary_unit_type or "units",
        "pallet_count": pallets,
        "distinct_skus": distinct_skus,
        "source_type": lot.source_type or "LIQUIDATION",
        "is_featured": False,
        "is_best_selling": False,
        "is_new_arrival": False,
        "image": main_img,
        "images": imgs,
        "listing_url": f"/lots/{lot.lot_number or lot.id}",
        "sku": lot.lot_number or "",
        "enquiry_status": str(lot.enquiry_status).strip().upper(),
        "is_active": bool(lot.is_active),
        "created_at": created_epoch,
        "views_count": int(lot.views_count or 0),
    }


def enqueue_sync(entity_type: str, entity_id: int, action: str, error_msg: str = "") -> None:
    """
    Appends an entry to TypesenseSyncQueue table for later re-processing by background cron.
    Guaranteed not to throw an exception to keep calling PostgreSQL transactions safe.
    """
    try:
        from .models import TypesenseSyncQueue
        TypesenseSyncQueue.objects.update_or_create(
            entity_type=entity_type,
            entity_id=entity_id,
            processed=False,
            defaults={
                "action": action,
                "last_error": error_msg[:1000] if error_msg else "",
            }
        )
    except Exception as e:
        logger.error(f"Failed to record Typesense outbox item ({entity_type} {entity_id}): {e}")


def index_product(product) -> bool:
    """
    Indexes or updates a single Product in Typesense.
    If the product is not active or not approved, it is deleted from Typesense.
    If Typesense fails or is unreachable, enqueues to TypesenseSyncQueue.
    """
    doc = product_to_document(product)
    if doc is None:
        return delete_product(product.id)

    client = get_typesense_client()
    coll_name = get_collection_name()
    try:
        client.collections[coll_name].documents.upsert(doc)
        logger.debug(f"Typesense indexed product #{product.id}")
        return True
    except Exception as e:
        err = str(e)
        logger.warning(f"Failed indexing product #{product.id} to Typesense: {err}")
        enqueue_sync("product", product.id, "upsert", err)
        return False


def delete_product(product_id: int) -> bool:
    """
    Deletes a product document from Typesense.
    """
    client = get_typesense_client()
    coll_name = get_collection_name()
    doc_id = f"product_{product_id}"
    try:
        client.collections[coll_name].documents[doc_id].delete()
        logger.debug(f"Typesense deleted product doc: {doc_id}")
        return True
    except typesense.exceptions.ObjectNotFound:
        return True
    except Exception as e:
        err = str(e)
        logger.warning(f"Failed deleting product #{product_id} from Typesense: {err}")
        enqueue_sync("product", product_id, "delete", err)
        return False


def index_lot(lot) -> bool:
    """
    Indexes or updates a single Lot in Typesense.
    If the lot is not active or not approved, it is deleted from Typesense.
    If Typesense fails or is unreachable, enqueues to TypesenseSyncQueue.
    """
    doc = lot_to_document(lot)
    if doc is None:
        return delete_lot(lot.id)

    client = get_typesense_client()
    coll_name = get_collection_name()
    try:
        client.collections[coll_name].documents.upsert(doc)
        logger.debug(f"Typesense indexed lot #{lot.id}")
        return True
    except Exception as e:
        err = str(e)
        logger.warning(f"Failed indexing lot #{lot.id} to Typesense: {err}")
        enqueue_sync("lot", lot.id, "upsert", err)
        return False


def delete_lot(lot_id: int) -> bool:
    """
    Deletes a lot document from Typesense.
    """
    client = get_typesense_client()
    coll_name = get_collection_name()
    doc_id = f"lot_{lot_id}"
    try:
        client.collections[coll_name].documents[doc_id].delete()
        logger.debug(f"Typesense deleted lot doc: {doc_id}")
        return True
    except typesense.exceptions.ObjectNotFound:
        return True
    except Exception as e:
        err = str(e)
        logger.warning(f"Failed deleting lot #{lot_id} from Typesense: {err}")
        enqueue_sync("lot", lot_id, "delete", err)
        return False


def bulk_index_documents(documents: List[Dict[str, Any]], batch_size: int = 100) -> Tuple[int, int]:
    """
    Imports a list of documents in batches into Typesense using the documents.import_ endpoint.
    Returns (success_count, error_count).
    """
    if not documents:
        return 0, 0

    client = get_typesense_client()
    coll_name = get_collection_name()
    total_success = 0
    total_error = 0

    for i in range(0, len(documents), batch_size):
        chunk = documents[i:i + batch_size]
        try:
            results = client.collections[coll_name].documents.import_(chunk, {"action": "upsert"})
            for r in results:
                if isinstance(r, dict) and r.get("success"):
                    total_success += 1
                else:
                    total_error += 1
                    logger.warning(f"Typesense import error for doc: {r}")
        except Exception as e:
            logger.error(f"Bulk import chunk failed: {e}")
            total_error += len(chunk)

    return total_success, total_error
