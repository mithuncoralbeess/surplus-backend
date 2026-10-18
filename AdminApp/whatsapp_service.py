import re
import json
import logging
import urllib.parse
from decimal import Decimal
from typing import List, Dict, Any, Optional

import requests
from django.utils import timezone
from django.conf import settings
from django.db.models import Q

from AdminApp.models import (
    WhatsAppAlertSubscriber,
    WhatsAppBroadcast,
    WhatsAppInboundMessage,
    WhatsAppApiConfig,
    Lot,
    Product,
    ContactUsEnquiry,
)

logger = logging.getLogger(__name__)


def clean_phone_number(phone_raw: str) -> str:
    """
    Normalizes a phone string into an international E.164-compatible digit string (without + or spaces).
    Example: '+971 50 123-4567' -> '971501234567'
    """
    if not phone_raw:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone_raw).strip())
    # Strip leading double zeros if international prefix format (00971...)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def format_lot_liquidation_alert(
    lot: Lot,
    custom_url: Optional[str] = None,
    custom_notes: Optional[str] = None
) -> str:
    """
    Generates a high-converting, formatted WhatsApp deal broadcast message
    with emojis, discount math, location, and a direct RFQ / manifest link.
    """
    title = (lot.title or "Bulk Inventory Liquidation Package").strip()
    currency = lot.currency or "USD"
    ask_price = float(lot.ask_price_surplus_payout or 0.0)
    msrp = float(lot.total_est_retail_value_msrp or 0.0)
    units = lot.total_units_quantity or 0
    pallets = lot.pallet_count or 1
    location = lot.inventory_location or "Verified Warehouse"
    condition = lot.condition or "Surplus Stock"
    stock_age = lot.inventory_stock_age or "Current"

    # Category name resolution
    categories = []
    if hasattr(lot, "category_allocations") and lot.category_allocations:
        try:
            alloc_data = lot.category_allocations
            if isinstance(alloc_data, str):
                alloc_data = json.loads(alloc_data)
            if isinstance(alloc_data, list):
                for item in alloc_data:
                    cname = item.get("category_name")
                    if cname and cname not in categories:
                        categories.append(cname)
        except Exception:
            pass
    if not categories and getattr(lot, "category_name", None):
        categories.append(lot.category_name)
    category_str = ", ".join(categories) if categories else "General Surplus"

    # Discount calculation
    discount_pct = 0
    if msrp > 0 and ask_price > 0:
        discount_pct = round(((msrp - ask_price) / msrp) * 100)

    # Unit price calculation
    unit_price_str = ""
    if units > 0 and ask_price > 0:
        unit_ask = ask_price / units
        unit_msrp = (msrp / units) if msrp > 0 else 0
        if unit_msrp > 0:
            unit_price_str = f" (~{currency} {unit_ask:,.2f} / unit vs MSRP {currency} {unit_msrp:,.2f})"
        else:
            unit_price_str = f" (~{currency} {unit_ask:,.2f} / unit)"

    # Base link to lot
    lot_slug_or_id = lot.lot_number or f"LOT-{lot.id:05d}"
    site_url = getattr(settings, "SITE_URL", "https://surplus.coralbees.com").rstrip("/")
    target_link = custom_url or f"{site_url}/lots/{lot_slug_or_id}/"

    msg_lines = [
        "🔥 *NEW SURPLUS LIQUIDATION ALERT* 🔥",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📦 *{title}*",
        f"🏷️ *Category:* {category_str}",
        f"📊 *Quantity:* {units:,} Units ({pallets} Pallet{'s' if pallets != 1 else ''})",
        f"📍 *Location:* {location}",
        "",
        f"💰 *Liquidation Ask:* *{currency} {ask_price:,.2f}*{unit_price_str}",
    ]

    if msrp > 0:
        msg_lines.append(f"🏷️ *Original MSRP:* {currency} {msrp:,.2f}")

    if discount_pct > 0:
        msg_lines.append(f"⚡ *Liquidation Discount:* *{discount_pct}% OFF MSRP*")

    msg_lines.extend([
        f"🛡️ *Condition:* {condition} ({stock_age})",
    ])

    if lot.key_brands_included:
        msg_lines.append(f"🏷️ *Brands:* {lot.key_brands_included}")

    if custom_notes:
        msg_lines.extend(["", f"📝 *Admin Note:* {custom_notes}"])

    msg_lines.extend([
        "",
        "🔗 *Review Manifest & Submit RFQ:*",
        target_link,
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💬 *Reply 'OFFER' or 'RFQ' to negotiate directly with wholesale desk.*"
    ])

    return "\n".join(msg_lines)


def format_product_liquidation_alert(product: Product, custom_url: Optional[str] = None) -> str:
    """
    Generates a WhatsApp alert for an individual high-discount product.
    """
    title = (product.product_name or "Surplus Item").strip()
    currency = product.currency or "USD"
    price = float(product.liquidating_price or 0.0)
    msrp = float(product.msrp or 0.0)
    qty = product.quantity or 1
    location = product.inventory_location or "Warehouse"
    cat_name = product.category.name if product.category else "Surplus"

    discount_pct = 0
    if msrp > 0 and price > 0:
        discount_pct = round(((msrp - price) / msrp) * 100)

    site_url = getattr(settings, "SITE_URL", "https://surplus.coralbees.com").rstrip("/")
    prod_id = product.product_id or f"PRO-{product.id:05d}"
    target_link = custom_url or f"{site_url}/products/{prod_id}/"

    msg_lines = [
        "⚡ *FLASH SURPLUS DEAL ALERT* ⚡",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📦 *{title}*",
        f"🏷️ *Category:* {cat_name}",
        f"📊 *Available Quantity:* {qty:,} units",
        f"📍 *Location:* {location}",
        "",
        f"💰 *Liquidation Price:* *{currency} {price:,.2f}* / unit",
    ]
    if msrp > 0:
        msg_lines.append(f"🏷️ *Original Retail MSRP:* {currency} {msrp:,.2f}")
    if discount_pct > 0:
        msg_lines.append(f"⚡ *Discount:* *{discount_pct}% OFF MSRP*")

    msg_lines.extend([
        "",
        "🔗 *View Item & Request Quote:*",
        target_link,
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💬 *Reply to this message for immediate order assistance.*"
    ])
    return "\n".join(msg_lines)


def get_eligible_subscribers(
    category: Optional[str] = None,
    location: Optional[str] = None,
    min_discount_pct: Optional[int] = None
) -> List[WhatsAppAlertSubscriber]:
    """
    Matches active subscribers based on category interest, location preference, and discount threshold.
    """
    qs = WhatsAppAlertSubscriber.objects.filter(is_active=True)

    if min_discount_pct is not None and min_discount_pct > 0:
        qs = qs.filter(min_discount_pct__lte=min_discount_pct)

    subscribers = list(qs)
    matched = []

    for sub in subscribers:
        # Category filtering
        if category and category.lower() != "all":
            sub_cats = [c.lower() for c in sub.categories] if sub.categories else []
            if sub_cats and (category.lower() not in sub_cats and "all" not in sub_cats):
                continue

        # Location filtering
        if location and location.lower() != "all" and sub.preferred_location:
            sub_loc = sub.preferred_location.lower()
            if sub_loc != "worldwide" and location.lower() not in sub_loc and sub_loc not in location.lower():
                continue

        matched.append(sub)

    return matched


def generate_whatsapp_web_link(phone: str, text: str) -> Dict[str, str]:
    """
    Builds both `wa.me` mobile deep link and `web.whatsapp.com` desktop browser link.
    100% free, requires zero API keys.
    """
    clean_p = clean_phone_number(phone)
    encoded_text = urllib.parse.quote(text)
    return {
        "clean_phone": clean_p,
        "wa_me_link": f"https://wa.me/{clean_p}?text={encoded_text}" if clean_p else f"https://wa.me/?text={encoded_text}",
        "whatsapp_web_link": f"https://web.whatsapp.com/send?phone={clean_p}&text={encoded_text}" if clean_p else f"https://web.whatsapp.com/send?text={encoded_text}",
    }


def send_cloud_api_message(recipient_phone: str, message_text: str) -> Dict[str, Any]:
    """
    Sends an automated message via Meta WhatsApp Cloud API (if configured by admin).
    Falls back gracefully if Cloud API is disabled or unconfigured.
    """
    config = WhatsAppApiConfig.get_config()
    if not config.is_cloud_api_enabled:
        return {"success": False, "mode": "FREE_MODE", "error": "Cloud API is not enabled in settings."}

    clean_p = clean_phone_number(recipient_phone)
    if not clean_p:
        return {"success": False, "error": "Invalid recipient phone number."}

    if not config.phone_number_id or not config.access_token:
        return {"success": False, "error": "Missing Meta Cloud API credentials in settings."}

    url = f"https://graph.facebook.com/v19.0/{config.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {config.access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_p,
        "type": "text",
        "text": {
            "preview_url": True,
            "body": message_text
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code in (200, 201):
            return {"success": True, "mode": "CLOUD_API", "data": resp.json()}
        else:
            logger.warning(f"Meta Cloud API error: {resp.status_code} - {resp.text}")
            return {"success": False, "mode": "CLOUD_API", "status_code": resp.status_code, "error": resp.text}
    except Exception as e:
        logger.error(f"WhatsApp Cloud API request exception: {e}")
        return {"success": False, "mode": "CLOUD_API", "error": str(e)}


def process_inbound_message(
    sender_phone: str,
    message_text: str,
    sender_name: str = "",
    media_url: str = "",
    media_type: str = ""
) -> Dict[str, Any]:
    """
    Ingests an inbound message received via WhatsApp Webhook or manual simulation.
    Automatically categorizes seller offers vs RFQs, logs to WhatsAppInboundMessage,
    and alerts administrators.
    """
    clean_p = clean_phone_number(sender_phone)
    text = (message_text or "").strip()
    lower_text = text.lower()

    # Heuristic intent classification
    seller_keywords = ["sell", "liquidate", "lot", "pallet", "stock", "manifest", "excess", "inventory", "warehouse"]
    buyer_keywords = ["buy", "rfq", "price", "quote", "discount", "offer", "interested", "purchase"]

    if any(k in lower_text for k in seller_keywords):
        intake_type = "SELLER_OFFER"
    elif any(k in lower_text for k in buyer_keywords):
        intake_type = "BUYER_RFQ"
    else:
        intake_type = "GENERAL"

    inbound_obj = WhatsAppInboundMessage.objects.create(
        sender_phone=clean_p or sender_phone,
        sender_name=sender_name or "WhatsApp Contact",
        message_text=text,
        media_url=media_url or "",
        media_type=media_type or "",
        intake_type=intake_type,
        status="NEW"
    )

    # Trigger admin alert notification
    try:
        from AdminApp.services import create_admin_notification
        create_admin_notification(
            title=f"New WhatsApp {intake_type.replace('_', ' ').title()}",
            message=f"From {sender_name or clean_p}: \"{text[:80]}\"",
            notification_type="ENQUIRY",
            action_url="/admin/whatsapp/?tab=inbound"
        )
    except Exception:
        pass

    # Auto acknowledgement text
    ref_code = f"WAS-{inbound_obj.id:04d}"
    auto_reply = (
        f"Hello from *Surplus Wholesale Desk*! 👋\n"
        f"Your inquiry has been received (Ref: *#{ref_code}*).\n\n"
        f"Our procurement specialists are reviewing your request. "
        f"If you have an Excel manifest, photos, or target pricing, please reply directly to this chat.\n\n"
        f"🌐 Surplus Platform — B2B Wholesale Liquidation Hub"
    )

    return {
        "success": True,
        "message_id": inbound_obj.id,
        "ref_code": ref_code,
        "intake_type": intake_type,
        "auto_reply": auto_reply
    }
