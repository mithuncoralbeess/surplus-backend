"""
Modular Data-Table Report Views, Drill-Down APIs, and CSV/Excel Exporters.
Supports the Surplus Market Report Module:
  - Products Report
  - Lots Report (with lot_products drill-down)
  - Users / Vendors Report
  - RFQs Demand Report (with rfq_enquiry_items drill-down)
  - Enquiries & Leads Report (unified live Product/Lot/Partnership/Contact inbox)
  - Auctions Report (with auction_bids drill-down)
"""

import csv
import io
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, F, FloatField, Q, Sum, Value
from django.db.models.functions import Cast, Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

logger = logging.getLogger(__name__)


def _auth_admin(request):
    from .views import _get_authenticated_admin
    return _get_authenticated_admin(request)


def _is_privileged_admin(admin_user) -> bool:
    if not admin_user:
        return False
    acct = getattr(admin_user, "account_type", "")
    return acct in ("SuperAdmin", "Admin") or bool(getattr(admin_user, "is_superuser", False))


def _parse_period_start(period: str):
    now = timezone.now()
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return None


def _parse_decimal(val):
    if val in (None, ""):
        return None
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_int(val):
    if val in (None, ""):
        return None
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _safe_order_by(qs, sort_param: str, allowed_map: dict, default_sort: str):
    raw = (sort_param or "").strip()
    desc = raw.startswith("-")
    key = raw[1:] if desc else raw
    db_field = allowed_map.get(key)
    if not db_field:
        return qs.order_by(default_sort), default_sort
    order_expr = f"-{db_field}" if desc else db_field
    return qs.order_by(order_expr, "-id"), order_expr


def _paginate(qs_or_list, page_num, per_page=50):
    paginator = Paginator(qs_or_list, per_page)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return paginator, page_obj


def _fmt_dt(dt):
    return dt.strftime("%d %b %Y") if dt else "—"


def _fmt_money(amount, currency="USD"):
    if amount is None:
        return "—"
    try:
        val = float(amount)
        return f"{currency or 'USD'} {val:,.2f}"
    except (ValueError, TypeError):
        return "—"


def _col(key, label, align="left", sortable=True, kind="text", visible=True):
    return {
        "key": key,
        "label": label,
        "align": align,
        "sortable": sortable,
        "kind": kind,
        "visible": visible,
    }


def _filter_def(name, label, kind="select", options=None, placeholder=""):
    return {
        "name": name,
        "label": label,
        "kind": kind,
        "options": options or [],
        "placeholder": placeholder,
    }


def _kpi_card(label, value, tone="neutral", sub=""):
    return {"label": label, "value": value, "tone": tone, "sub": sub}


# ==============================================================================
# REPORT BUILDERS
# ==============================================================================

def _build_products_report(request, for_export=False):
    from .models import MainCategory, Product

    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "").strip()
    active_f = request.GET.get("active", "").strip()
    category_f = request.GET.get("category", "").strip()
    country_f = request.GET.get("country", "").strip()
    flag_f = request.GET.get("flag", "").strip()
    cert_f = request.GET.get("certificate", "").strip()
    currency_f = request.GET.get("currency", "").strip()
    period_f = request.GET.get("period", "all").strip()
    approved_f = request.GET.get("approved_period", "all").strip()
    min_price = _parse_decimal(request.GET.get("min_price"))
    max_price = _parse_decimal(request.GET.get("max_price"))
    min_qty = _parse_int(request.GET.get("min_qty"))
    max_qty = _parse_int(request.GET.get("max_qty"))

    qs = Product.objects.select_related("category", "vendor").only(
        "id",
        "product_code",
        "product_id",
        "product_name",
        "brand_name",
        "quantity",
        "msrp",
        "current_price",
        "offer",
        "inventory_country",
        "currency",
        "views_count",
        "enquiry_status",
        "created_at",
        "category__id",
        "category__name",
        "vendor__id",
        "vendor__company_name",
        "vendor__full_name",
        "vendor__username",
    )

    if q:
        qs = qs.filter(
            Q(product_name__icontains=q)
            | Q(product_code__icontains=q)
            | Q(product_id__icontains=q)
            | Q(model_no__icontains=q)
            | Q(brand_name__icontains=q)
            | Q(vendor__company_name__icontains=q)
            | Q(vendor__full_name__icontains=q)
        )
    if status_f:
        qs = qs.filter(enquiry_status__iexact=status_f)
    if active_f == "active":
        qs = qs.filter(is_active=True)
    elif active_f == "inactive":
        qs = qs.filter(is_active=False)
    if category_f:
        qs = qs.filter(category__name__iexact=category_f)
    if country_f:
        qs = qs.filter(Q(inventory_country__iexact=country_f) | Q(manufacturing_country__iexact=country_f))
    if flag_f == "featured":
        qs = qs.filter(is_featured=True)
    elif flag_f == "best_selling":
        qs = qs.filter(is_best_selling=True)
    elif flag_f == "new_arrival":
        qs = qs.filter(is_new_arrival=True)
    if cert_f == "yes":
        qs = qs.filter(third_party_certificate=True)
    elif cert_f == "no":
        qs = qs.filter(third_party_certificate=False)
    if currency_f:
        qs = qs.filter(currency__iexact=currency_f)
    if min_price is not None:
        qs = qs.filter(current_price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(current_price__lte=max_price)
    if min_qty is not None:
        qs = qs.filter(quantity__gte=min_qty)
    if max_qty is not None:
        qs = qs.filter(quantity__lte=max_qty)

    start_dt = _parse_period_start(period_f)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)
    app_dt = _parse_period_start(approved_f)
    if app_dt:
        qs = qs.filter(date_approved__gte=app_dt)

    sort_map = {
        "product_code": "product_code",
        "product_name": "product_name",
        "category": "category__name",
        "brand_name": "brand_name",
        "quantity": "quantity",
        "msrp": "msrp",
        "current_price": "current_price",
        "offer": "offer",
        "inventory_country": "inventory_country",
        "views_count": "views_count",
        "enquiry_status": "enquiry_status",
        "created_at": "created_at",
    }
    qs, active_sort = _safe_order_by(qs, request.GET.get("sort"), sort_map, "-created_at")

    stats = qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(enquiry_status__iexact="PENDING")),
        approved=Count("id", filter=Q(enquiry_status__iexact="APPROVED", is_active=True)),
        declined=Count("id", filter=Q(enquiry_status__iexact="DECLINED")),
        avg_price=Avg("current_price"),
    )
    kpis = [
        _kpi_card("TOTAL PRODUCTS", f"{stats['total'] or 0:,}"),
        _kpi_card("PENDING APPROVAL", f"{stats['pending'] or 0:,}", "warning"),
        _kpi_card("APPROVED / LIVE", f"{stats['approved'] or 0:,}", "success"),
        _kpi_card("DECLINED", f"{stats['declined'] or 0:,}", "danger"),
        _kpi_card("AVG BUYER PRICE", f"{float(stats['avg_price'] or 0):,.2f}", "primary", "Across selected currency rows"),
    ]

    columns = [
        _col("product_code", "Product Code", kind="code"),
        _col("product_name", "Name"),
        _col("category", "Category"),
        _col("brand_name", "Brand"),
        _col("quantity", "Qty", align="right"),
        _col("msrp", "MSRP", align="right"),
        _col("current_price", "Buyer Price", align="right"),
        _col("offer", "Off %", align="right"),
        _col("inventory_country", "Inv. Country"),
        _col("vendor", "Vendor", sortable=False),
        _col("views_count", "Views", align="right"),
        _col("enquiry_status", "Status", kind="badge"),
        _col("created_at", "Created"),
    ]

    categories = cache.get("rpt_prod_cats")
    if categories is None:
        categories = list(MainCategory.objects.filter(is_active=True).order_by("name").values_list("name", flat=True))
        cache.set("rpt_prod_cats", categories, 300)

    countries = cache.get("rpt_prod_countries")
    if countries is None:
        countries = sorted(
            list(
                Product.objects.exclude(inventory_country="")
                .exclude(inventory_country__isnull=True)
                .values_list("inventory_country", flat=True)
                .distinct()
            )
        )
        cache.set("rpt_prod_countries", countries, 300)

    currencies = ["USD", "AED", "EUR", "GBP", "SAR", "INR"]
    filters = [
        _filter_def("q", "Search", "text", placeholder="Name, code, SKU, brand..."),
        _filter_def("status", "Status", "select", [("PENDING", "Pending"), ("APPROVED", "Approved"), ("DECLINED", "Declined"), ("CORRECTION_NEEDED", "Needs Correction")]),
        _filter_def("active", "Active", "select", [("active", "Active"), ("inactive", "Inactive")]),
        _filter_def("category", "Category", "select", [(c, c) for c in categories]),
        _filter_def("country", "Country", "select", [(c, c) for c in countries]),
        _filter_def("flag", "Showcase Flag", "select", [("featured", "Featured"), ("best_selling", "Best Selling"), ("new_arrival", "New Arrival")]),
        _filter_def("certificate", "Has Certificate", "select", [("yes", "Yes"), ("no", "No")]),
        _filter_def("currency", "Currency", "select", [(c, c) for c in currencies]),
        _filter_def("min_price", "Min Price", "number", placeholder="0"),
        _filter_def("max_price", "Max Price", "number", placeholder="Any"),
        _filter_def("min_qty", "Min Qty", "number", placeholder="0"),
        _filter_def("period", "Created", "select", [("7d", "Last 7 Days"), ("30d", "Last 30 Days"), ("90d", "Last 90 Days"), ("all", "All Time")]),
    ]

    def _serialize_row(p):
        vendor_lbl = (p.vendor.company_name or p.vendor.full_name or p.vendor.username) if p.vendor else "Admin / Direct"
        curr = p.currency or "USD"
        return {
            "id": p.id,
            "drill_kind": "product",
            "detail_url": f"/admin/products/{p.id}/",
            "cells": {
                "product_code": p.product_code or p.product_id or f"PRO-{p.id:05d}",
                "product_name": p.product_name,
                "category": p.category.name if p.category else "—",
                "brand_name": p.brand_name or "—",
                "quantity": f"{p.quantity:,}",
                "msrp": _fmt_money(p.msrp, curr) if p.msrp is not None else "—",
                "current_price": _fmt_money(p.current_price, curr),
                "offer": f"{float(p.offer or 0):.0f}%",
                "inventory_country": p.inventory_country or "—",
                "vendor": vendor_lbl,
                "views_count": f"{p.views_count:,}",
                "enquiry_status": p.get_enquiry_status_display(),
                "status_raw": (p.enquiry_status or "").lower(),
                "created_at": _fmt_dt(p.created_at),
            },
        }

    if for_export:
        items = list(qs[:10000])
        return columns, [_serialize_row(p) for p in items]

    paginator, page_obj = _paginate(qs, request.GET.get("page", 1))
    rows = [_serialize_row(p) for p in page_obj]
    return {
        "report_type": "products",
        "title": "Products Report",
        "subtitle": "Every single-product listing across products, categories, and vendors.",
        "kpis": kpis,
        "columns": columns,
        "filters": filters,
        "rows": rows,
        "paginator": paginator,
        "page_obj": page_obj,
        "active_sort": active_sort,
        "dev_note": "Maps to products.*. Buyer price = current_price (liquidating_price x 1.10). Row click opens specs & product image gallery.",
    }


def _build_lots_report(request, for_export=False):
    from .models import Lot

    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "").strip()
    active_f = request.GET.get("active", "").strip()
    condition_f = request.GET.get("condition", "").strip()
    source_f = request.GET.get("source", "").strip()
    sale_f = request.GET.get("sale_method", "").strip()
    country_f = request.GET.get("country", "").strip()
    category_f = request.GET.get("category", "").strip()
    cert_f = request.GET.get("certificate", "").strip()
    period_f = request.GET.get("period", "all").strip()
    min_ask = _parse_decimal(request.GET.get("min_ask"))
    max_ask = _parse_decimal(request.GET.get("max_ask"))
    min_units = _parse_int(request.GET.get("min_units"))

    qs = Lot.objects.select_related("vendor").only(
        "id",
        "lot_number",
        "title",
        "condition",
        "source_type",
        "number_of_distinct_skus",
        "total_units_quantity",
        "total_est_retail_value_msrp",
        "ask_price_surplus_payout",
        "inventory_country",
        "sale_method",
        "enquiry_status",
        "is_active",
        "currency",
        "created_at",
        "vendor__id",
        "vendor__company_name",
        "vendor__email",
    )

    if q:
        qs = qs.filter(
            Q(lot_number__icontains=q)
            | Q(title__icontains=q)
            | Q(key_brands_included__icontains=q)
            | Q(vendor__company_name__icontains=q)
        )
    if status_f:
        qs = qs.filter(enquiry_status__iexact=status_f)
    if active_f == "active":
        qs = qs.filter(is_active=True)
    elif active_f == "inactive":
        qs = qs.filter(is_active=False)
    if condition_f:
        qs = qs.filter(condition__icontains=condition_f)
    if source_f:
        qs = qs.filter(source_type__icontains=source_f)
    if sale_f:
        qs = qs.filter(sale_method__iexact=sale_f)
    if country_f:
        qs = qs.filter(inventory_country__iexact=country_f)
    if category_f:
        qs = qs.filter(
            Q(category_allocations__icontains=category_f)
            | Q(raw_data__icontains=category_f)
        )
    if cert_f == "yes":
        qs = qs.filter(third_party_certificate_available=True)
    elif cert_f == "no":
        qs = qs.filter(third_party_certificate_available=False)
    if min_ask is not None:
        qs = qs.filter(ask_price_surplus_payout__gte=min_ask)
    if max_ask is not None:
        qs = qs.filter(ask_price_surplus_payout__lte=max_ask)
    if min_units is not None:
        qs = qs.filter(total_units_quantity__gte=min_units)

    start_dt = _parse_period_start(period_f)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)

    sort_map = {
        "lot_number": "lot_number",
        "title": "title",
        "condition": "condition",
        "source_type": "source_type",
        "number_of_distinct_skus": "number_of_distinct_skus",
        "total_units_quantity": "total_units_quantity",
        "total_est_retail_value_msrp": "total_est_retail_value_msrp",
        "ask_price_surplus_payout": "ask_price_surplus_payout",
        "inventory_country": "inventory_country",
        "sale_method": "sale_method",
        "enquiry_status": "enquiry_status",
        "created_at": "created_at",
    }
    qs, active_sort = _safe_order_by(qs, request.GET.get("sort"), sort_map, "-created_at")

    stats = qs.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(enquiry_status__iexact="pending")),
        live=Count("id", filter=Q(is_active=True)),
        total_retail=Sum("total_est_retail_value_msrp"),
        total_ask=Sum("ask_price_surplus_payout"),
    )
    tot_ret = float(stats["total_retail"] or 0)
    tot_ask = float(stats["total_ask"] or 0)
    avg_pct = f"{(tot_ask / tot_ret * 100):.0f}%" if tot_ret > 0 else "—"

    kpis = [
        _kpi_card("TOTAL LOTS", f"{stats['total'] or 0:,}"),
        _kpi_card("PENDING", f"{stats['pending'] or 0:,}", "warning"),
        _kpi_card("LIVE", f"{stats['live'] or 0:,}", "success"),
        _kpi_card("TOTAL EST. RETAIL", f"{tot_ret:,.0f}", "primary", "Sum of lot MSRP values"),
        _kpi_card("AVG % OF RETAIL", avg_pct, "neutral"),
    ]

    columns = [
        _col("lot_number", "Lot #", kind="code"),
        _col("title", "Title"),
        _col("condition", "Condition"),
        _col("source_type", "Source"),
        _col("number_of_distinct_skus", "SKUs", align="right"),
        _col("total_units_quantity", "Units", align="right"),
        _col("total_est_retail_value_msrp", "Est. Retail", align="right"),
        _col("ask_price_surplus_payout", "Ask Price", align="right"),
        _col("pct_retail", "% Retail", align="right", sortable=False),
        _col("inventory_country", "Inv. Country"),
        _col("sale_method", "Sale"),
        _col("enquiry_status", "Status", kind="badge"),
        _col("created_at", "Created"),
    ]

    countries = cache.get("rpt_lot_countries")
    if countries is None:
        countries = sorted(
            list(
                Lot.objects.exclude(inventory_country="")
                .exclude(inventory_country__isnull=True)
                .values_list("inventory_country", flat=True)
                .distinct()
            )
        )
        cache.set("rpt_lot_countries", countries, 300)

    filters = [
        _filter_def("q", "Search", "text", placeholder="Lot #, title, brands..."),
        _filter_def("status", "Status", "select", [("pending", "Pending"), ("approved", "Approved"), ("correction_needed", "Needs Correction"), ("declined", "Declined")]),
        _filter_def("active", "Active", "select", [("active", "Active"), ("inactive", "Inactive")]),
        _filter_def("sale_method", "Sale Method", "select", [("offer", "Offer"), ("fixed", "Fixed"), ("auction", "Auction")]),
        _filter_def("country", "Country", "select", [(c, c) for c in countries]),
        _filter_def("condition", "Condition", "text", placeholder="e.g. New, Returns"),
        _filter_def("source", "Source Type", "text", placeholder="e.g. Overstock"),
        _filter_def("category", "Category", "text", placeholder="Category keyword"),
        _filter_def("certificate", "Has Certificate", "select", [("yes", "Yes"), ("no", "No")]),
        _filter_def("min_ask", "Min Ask", "number", placeholder="0"),
        _filter_def("max_ask", "Max Ask", "number", placeholder="Any"),
        _filter_def("min_units", "Min Units", "number", placeholder="0"),
        _filter_def("period", "Created", "select", [("7d", "Last 7 Days"), ("30d", "Last 30 Days"), ("90d", "Last 90 Days"), ("all", "All Time")]),
    ]

    def _serialize_row(l):
        curr = l.currency or "USD"
        ret = float(l.total_est_retail_value_msrp or 0)
        ask = float(l.ask_price_surplus_payout or 0)
        pct_str = f"{(ask / ret * 100):.0f}%" if ret > 0 and ask > 0 else "—"
        return {
            "id": l.id,
            "drill_kind": "lot",
            "detail_url": f"/admin/enquiries/lots/{l.id}/",
            "cells": {
                "lot_number": l.lot_number,
                "title": l.title or f"Lot {l.lot_number}",
                "condition": l.condition or "—",
                "source_type": l.source_type or "—",
                "number_of_distinct_skus": f"{l.number_of_distinct_skus or 0:,}",
                "total_units_quantity": f"{l.total_units_quantity or 0:,}",
                "total_est_retail_value_msrp": _fmt_money(l.total_est_retail_value_msrp, curr) if l.total_est_retail_value_msrp else "—",
                "ask_price_surplus_payout": _fmt_money(l.ask_price_surplus_payout, curr) if l.ask_price_surplus_payout else "—",
                "pct_retail": pct_str,
                "inventory_country": l.inventory_country or "—",
                "sale_method": (l.sale_method or "offer").title(),
                "enquiry_status": (l.enquiry_status or "pending").replace("_", " ").title(),
                "status_raw": (l.enquiry_status or "").lower(),
                "created_at": _fmt_dt(l.created_at),
            },
        }

    if for_export:
        items = list(qs[:10000])
        return columns, [_serialize_row(l) for l in items]

    paginator, page_obj = _paginate(qs, request.GET.get("page", 1))
    return {
        "report_type": "lots",
        "title": "Lots Report",
        "subtitle": "Every bulk lot / pallet. Row click opens the lot_products manifest drill-down.",
        "kpis": kpis,
        "columns": columns,
        "filters": filters,
        "rows": [_serialize_row(l) for l in page_obj],
        "paginator": paginator,
        "page_obj": page_obj,
        "active_sort": active_sort,
        "dev_note": "Maps to lots.*. % Retail = ask_price_surplus_payout / total_est_retail_value_msrp. Row click loads extracted lot_products items.",
    }


def _build_users_report(request, for_export=False):
    from .models import VendorDetails

    q = request.GET.get("q", "").strip()
    utype_f = request.GET.get("user_type", "").strip()
    entity_f = request.GET.get("entity_type", "").strip()
    country_f = request.GET.get("country", "").strip()
    btype_f = request.GET.get("business_type", "").strip()
    status_f = request.GET.get("status", "").strip()
    has_comp_f = request.GET.get("has_company", "").strip()
    period_f = request.GET.get("period", "all").strip()

    qs = VendorDetails.objects.only(
        "id",
        "username",
        "full_name",
        "email",
        "mobile_number",
        "user_type",
        "account_entity_type",
        "company_name",
        "country",
        "category_interested",
        "status",
        "created_at",
    )
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(company_name__icontains=q)
            | Q(mobile_number__icontains=q)
        )
    if utype_f:
        qs = qs.filter(user_type__iexact=utype_f)
    if entity_f:
        qs = qs.filter(account_entity_type__iexact=entity_f)
    if country_f:
        qs = qs.filter(country__iexact=country_f)
    if btype_f:
        qs = qs.filter(business_type__icontains=btype_f)
    if status_f == "active":
        qs = qs.filter(status=True)
    elif status_f == "inactive":
        qs = qs.filter(status=False)
    if has_comp_f == "yes":
        qs = qs.exclude(company_name="").exclude(company_name__isnull=True)
    elif has_comp_f == "no":
        qs = qs.filter(Q(company_name="") | Q(company_name__isnull=True))

    start_dt = _parse_period_start(period_f)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)

    sort_map = {
        "username": "username",
        "full_name": "full_name",
        "email": "email",
        "user_type": "user_type",
        "account_entity_type": "account_entity_type",
        "company_name": "company_name",
        "country": "country",
        "status": "status",
        "created_at": "created_at",
    }
    qs, active_sort = _safe_order_by(qs, request.GET.get("sort"), sort_map, "-created_at")

    stats = qs.aggregate(
        total=Count("id"),
        buyers=Count("id", filter=Q(user_type__iexact="BUYER")),
        sellers=Count("id", filter=Q(user_type__iexact="SELLER")),
        both=Count("id", filter=Q(user_type__iexact="BOTH")),
        companies=Count("id", filter=~Q(company_name="") & ~Q(company_name__isnull=True)),
    )
    kpis = [
        _kpi_card("TOTAL USERS", f"{stats['total'] or 0:,}"),
        _kpi_card("BUYERS", f"{stats['buyers'] or 0:,}", "primary"),
        _kpi_card("SELLERS", f"{stats['sellers'] or 0:,}", "success"),
        _kpi_card("BOTH", f"{stats['both'] or 0:,}", "warning"),
        _kpi_card("COMPANIES", f"{stats['companies'] or 0:,}", "neutral"),
    ]

    columns = [
        _col("username", "Username", kind="code"),
        _col("full_name", "Full Name"),
        _col("email", "Email"),
        _col("mobile_number", "Mobile", sortable=False),
        _col("user_type", "Type"),
        _col("account_entity_type", "Entity"),
        _col("company_name", "Company"),
        _col("country", "Country"),
        _col("category_interested", "Categories Interested", sortable=False),
        _col("status", "Status", kind="badge"),
        _col("created_at", "Created"),
    ]

    countries = cache.get("rpt_user_countries")
    if countries is None:
        countries = sorted(
            list(
                VendorDetails.objects.exclude(country="")
                .exclude(country__isnull=True)
                .values_list("country", flat=True)
                .distinct()
            )
        )
        cache.set("rpt_user_countries", countries, 300)

    filters = [
        _filter_def("q", "Search", "text", placeholder="Name, email, company, username..."),
        _filter_def("user_type", "User Type", "select", [("BUYER", "Buyer"), ("SELLER", "Seller"), ("BOTH", "Both")]),
        _filter_def("entity_type", "Account Entity", "select", [("COMPANY", "Company"), ("INDIVIDUAL", "Individual")]),
        _filter_def("country", "Country", "select", [(c, c) for c in countries]),
        _filter_def("business_type", "Business Type", "text", placeholder="e.g. Trader"),
        _filter_def("status", "Status", "select", [("active", "Active"), ("inactive", "Inactive")]),
        _filter_def("has_company", "Has Company", "select", [("yes", "Yes"), ("no", "No")]),
        _filter_def("period", "Registered", "select", [("7d", "Last 7 Days"), ("30d", "Last 30 Days"), ("90d", "Last 90 Days"), ("all", "All Time")]),
    ]

    def _serialize_row(u):
        cats = u.category_interested if isinstance(u.category_interested, list) else []
        cats_str = ", ".join(str(c) for c in cats[:3]) + (f" +{len(cats)-3}" if len(cats) > 3 else "")
        return {
            "id": u.id,
            "drill_kind": "",
            "detail_url": f"/admin/users/vendors/{u.id}/",
            "cells": {
                "username": u.username,
                "full_name": u.full_name or "—",
                "email": u.email,
                "mobile_number": u.mobile_number or "—",
                "user_type": u.user_type,
                "account_entity_type": (u.account_entity_type or "").title(),
                "company_name": u.company_name or "—",
                "country": u.country or "—",
                "category_interested": cats_str or "—",
                "status": "Active" if u.status else "Inactive",
                "status_raw": "approved" if u.status else "declined",
                "created_at": _fmt_dt(u.created_at),
            },
        }

    if for_export:
        items = list(qs[:10000])
        return columns, [_serialize_row(u) for u in items]

    paginator, page_obj = _paginate(qs, request.GET.get("page", 1))
    return {
        "report_type": "users",
        "title": "Users / Vendors Report",
        "subtitle": "Buyers, sellers, and dual accounts segmented by entity, geography, and interests.",
        "kpis": kpis,
        "columns": columns,
        "filters": filters,
        "rows": [_serialize_row(u) for u in page_obj],
        "paginator": paginator,
        "page_obj": page_obj,
        "active_sort": active_sort,
        "dev_note": "Maps to vendor_details.*. Type={BUYER, SELLER, BOTH}, Entity={INDIVIDUAL, COMPANY}.",
    }


def _build_rfqs_report(request, for_export=False):
    from .models import RfqEnquiry

    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "").strip()
    country_f = request.GET.get("country", "").strip()
    incoterm_f = request.GET.get("incoterm", "").strip()
    payment_f = request.GET.get("payment", "").strip()
    item_type_f = request.GET.get("item_type", "").strip()
    cat_f = request.GET.get("category", "").strip()
    min_val = _parse_decimal(request.GET.get("min_val"))
    max_val = _parse_decimal(request.GET.get("max_val"))
    period_f = request.GET.get("period", "all").strip()

    qs = RfqEnquiry.objects.select_related("buyer").only(
        "id",
        "reference",
        "company_name",
        "contact_person",
        "email",
        "country",
        "destination_port",
        "incoterm",
        "total_units",
        "estimated_value",
        "payment_method",
        "status",
        "currency",
        "created_at",
        "buyer__id",
        "buyer__company_name",
        "buyer__email",
    ).annotate(
        items_count=Count("items", distinct=True)
    )

    if q:
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(company_name__icontains=q)
            | Q(contact_person__icontains=q)
            | Q(email__icontains=q)
        )
    if status_f:
        qs = qs.filter(status__iexact=status_f)
    if country_f:
        qs = qs.filter(country__iexact=country_f)
    if incoterm_f:
        qs = qs.filter(incoterm__iexact=incoterm_f)
    if payment_f:
        qs = qs.filter(payment_method__icontains=payment_f)
    if item_type_f:
        qs = qs.filter(items__item_type__iexact=item_type_f).distinct()
    if cat_f:
        qs = qs.filter(items__category__icontains=cat_f).distinct()
    if min_val is not None:
        qs = qs.filter(estimated_value__gte=min_val)
    if max_val is not None:
        qs = qs.filter(estimated_value__lte=max_val)

    start_dt = _parse_period_start(period_f)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)

    sort_map = {
        "reference": "reference",
        "company_name": "company_name",
        "email": "email",
        "country": "country",
        "destination_port": "destination_port",
        "incoterm": "incoterm",
        "items_count": "items_count",
        "total_units": "total_units",
        "estimated_value": "estimated_value",
        "status": "status",
        "created_at": "created_at",
    }
    qs, active_sort = _safe_order_by(qs, request.GET.get("sort"), sort_map, "-created_at")

    stats = qs.aggregate(
        total=Count("id", distinct=True),
        pending=Count("id", filter=Q(status__iexact="PENDING"), distinct=True),
        quoted=Count("id", filter=Q(status__iexact="QUOTED"), distinct=True),
        accepted=Count("id", filter=Q(status__iexact="ACCEPTED"), distinct=True),
        open_val=Sum("estimated_value", filter=Q(status__in=["PENDING", "QUOTED", "pending", "quoted"])),
    )
    kpis = [
        _kpi_card("TOTAL RFQS", f"{stats['total'] or 0:,}"),
        _kpi_card("PENDING", f"{stats['pending'] or 0:,}", "warning"),
        _kpi_card("QUOTED", f"{stats['quoted'] or 0:,}", "primary"),
        _kpi_card("ACCEPTED", f"{stats['accepted'] or 0:,}", "success"),
        _kpi_card("EST. VALUE (OPEN)", f"{float(stats['open_val'] or 0):,.0f}", "neutral", "Pending + Quoted"),
    ]

    columns = [
        _col("reference", "Reference", kind="code"),
        _col("company_name", "Buyer / Company"),
        _col("email", "Email"),
        _col("country", "Country"),
        _col("destination_port", "Dest. Port"),
        _col("incoterm", "Incoterm"),
        _col("items_count", "Items", align="right"),
        _col("total_units", "Units", align="right"),
        _col("estimated_value", "Est. Value", align="right"),
        _col("payment_method", "Payment", sortable=False),
        _col("status", "Status", kind="badge"),
        _col("created_at", "Created"),
    ]

    countries = cache.get("rpt_rfq_countries")
    if countries is None:
        countries = sorted(
            list(
                RfqEnquiry.objects.exclude(country="")
                .exclude(country__isnull=True)
                .values_list("country", flat=True)
                .distinct()
            )
        )
        cache.set("rpt_rfq_countries", countries, 300)

    filters = [
        _filter_def("q", "Search", "text", placeholder="Ref, company, email..."),
        _filter_def("status", "Status", "select", [("PENDING", "Pending"), ("QUOTED", "Quoted"), ("ACCEPTED", "Accepted"), ("DECLINED", "Declined"), ("CLOSED", "Closed")]),
        _filter_def("country", "Buyer Country", "select", [(c, c) for c in countries]),
        _filter_def("incoterm", "Incoterm", "select", [("EXW", "EXW"), ("FOB", "FOB"), ("CIF", "CIF"), ("DDP", "DDP")]),
        _filter_def("payment", "Payment", "text", placeholder="Escrow, Wire, LC..."),
        _filter_def("item_type", "Item Type", "select", [("product", "Product"), ("lot", "Lot")]),
        _filter_def("category", "Category", "text", placeholder="Item category"),
        _filter_def("min_val", "Min Est. Value", "number", placeholder="0"),
        _filter_def("max_val", "Max Est. Value", "number", placeholder="Any"),
        _filter_def("period", "Created", "select", [("7d", "Last 7 Days"), ("30d", "Last 30 Days"), ("90d", "Last 90 Days"), ("all", "All Time")]),
    ]

    def _serialize_row(r):
        curr = r.currency or "USD"
        buyer_lbl = r.company_name or (r.buyer.company_name if r.buyer else "") or r.contact_person
        return {
            "id": r.id,
            "drill_kind": "rfq",
            "detail_url": f"/admin/rfq-requests/{r.id}/",
            "cells": {
                "reference": r.reference,
                "company_name": buyer_lbl or "—",
                "email": r.email or (r.buyer.email if r.buyer else "—"),
                "country": r.country or "—",
                "destination_port": r.destination_port or "—",
                "incoterm": r.incoterm or "EXW",
                "items_count": f"{getattr(r, 'items_count', 0):,}",
                "total_units": f"{r.total_units:,}",
                "estimated_value": _fmt_money(r.estimated_value, curr),
                "payment_method": r.payment_method or "—",
                "status": (r.status or "PENDING").title(),
                "status_raw": (r.status or "").lower(),
                "created_at": _fmt_dt(r.created_at),
            },
        }

    if for_export:
        items = list(qs[:10000])
        return columns, [_serialize_row(r) for r in items]

    paginator, page_obj = _paginate(qs, request.GET.get("page", 1))
    return {
        "report_type": "rfqs",
        "title": "RFQs Report (Demand)",
        "subtitle": "Consolidated buyer quotation requests. Row click opens requested rfq_enquiry_items.",
        "kpis": kpis,
        "columns": columns,
        "filters": filters,
        "rows": [_serialize_row(r) for r in page_obj],
        "paginator": paginator,
        "page_obj": page_obj,
        "active_sort": active_sort,
        "dev_note": "Maps to rfq_enquiries.* + rfq_enquiry_items. Uses distinct COUNT on items to avoid duplicate rows on JOIN filters.",
    }


def _build_enquiries_report(request, for_export=False):
    """
    Unified inbox across live enquiry sources:
      - Seller Products (products)
      - Bulk Lots (lots)
      - Partnership Enquiries (partnership_enquiries)
      - Contact / Support Enquiries (contact_us_enquiries)
    """
    from .models import ContactUsEnquiry, Lot, PartnershipEnquiry, Product

    q = request.GET.get("q", "").strip()
    type_f = request.GET.get("type", "").strip()
    status_f = request.GET.get("status", "").strip()
    blocked_f = request.GET.get("is_blocked", "").strip()
    period_f = request.GET.get("period", "all").strip()

    start_dt = _parse_period_start(period_f)

    prod_qs = Product.objects.select_related("vendor", "category").only(
        "id", "product_name", "product_code", "product_id", "liquidating_price", "quantity",
        "currency", "enquiry_status", "created_at",
        "vendor__id", "vendor__email", "vendor__mobile_number",
        "category__id", "category__name",
    )
    lot_qs = Lot.objects.select_related("vendor").only(
        "id", "lot_number", "title", "number_of_distinct_skus", "total_units_quantity",
        "ask_price_surplus_payout", "currency", "enquiry_status", "created_at",
        "vendor__id", "vendor__email", "vendor__mobile_number",
    )
    part_qs = PartnershipEnquiry.objects.only(
        "id", "name", "email", "subject", "partnership_interest", "status", "created_at"
    )
    cont_qs = ContactUsEnquiry.objects.only(
        "id", "full_name", "email", "phone", "enquiry_type", "message", "is_blocked", "status", "created_at"
    )

    if start_dt:
        prod_qs = prod_qs.filter(created_at__gte=start_dt)
        lot_qs = lot_qs.filter(created_at__gte=start_dt)
        part_qs = part_qs.filter(created_at__gte=start_dt)
        cont_qs = cont_qs.filter(created_at__gte=start_dt)

    if q:
        prod_qs = prod_qs.filter(Q(product_name__icontains=q) | Q(product_code__icontains=q) | Q(vendor__email__icontains=q))
        lot_qs = lot_qs.filter(Q(title__icontains=q) | Q(lot_number__icontains=q) | Q(vendor__email__icontains=q))
        part_qs = part_qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(subject__icontains=q))
        cont_qs = cont_qs.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(enquiry_type__icontains=q) | Q(message__icontains=q))

    if status_f:
        prod_qs = prod_qs.filter(enquiry_status__iexact=status_f)
        lot_qs = lot_qs.filter(enquiry_status__iexact=status_f)
        part_qs = part_qs.filter(status__iexact=status_f)
        cont_qs = cont_qs.filter(status__iexact=status_f)

    if blocked_f == "yes":
        cont_qs = cont_qs.filter(is_blocked=True)
    elif blocked_f == "no":
        cont_qs = cont_qs.filter(is_blocked=False)

    # Counts per source (applying filters except `type` so KPI breakdown stays clear)
    prod_cnt = prod_qs.count() if not blocked_f else 0
    lot_cnt = lot_qs.count() if not blocked_f else 0
    part_cnt = part_qs.count() if not blocked_f else 0
    cont_cnt = cont_qs.count()

    rows = []
    limit_each = 1000 if for_export else 150

    if type_f in ("", "seller_product") and not blocked_f:
        for p in prod_qs.order_by("-created_at")[:limit_each]:
            v_email = p.vendor.email if p.vendor else "—"
            v_phone = p.vendor.mobile_number if p.vendor else "—"
            val = (p.liquidating_price or Decimal("0")) * (p.quantity or 0)
            rows.append({
                "id": p.id,
                "drill_kind": "product",
                "detail_url": f"/admin/enquiries/seller/{p.id}/",
                "sort_dt": p.created_at,
                "cells": {
                    "type": "Seller Product",
                    "reference": f"{p.product_name} ({p.product_code or p.product_id})",
                    "email": v_email,
                    "phone": v_phone or "—",
                    "subject": f"{p.category.name if p.category else 'General'} · {p.quantity:,} units",
                    "value": _fmt_money(val, p.currency or "USD"),
                    "status": p.get_enquiry_status_display(),
                    "status_raw": (p.enquiry_status or "").lower(),
                    "created_at": _fmt_dt(p.created_at),
                },
            })

    if type_f in ("", "lot") and not blocked_f:
        for l in lot_qs.order_by("-created_at")[:limit_each]:
            v_email = l.vendor.email if l.vendor else "—"
            v_phone = l.vendor.mobile_number if l.vendor else "—"
            rows.append({
                "id": l.id,
                "drill_kind": "lot",
                "detail_url": f"/admin/enquiries/lots/{l.id}/",
                "sort_dt": l.created_at,
                "cells": {
                    "type": "Lot Submission",
                    "reference": f"{l.lot_number} · {l.title or 'Bulk Lot'}",
                    "email": v_email,
                    "phone": v_phone or "—",
                    "subject": f"{l.number_of_distinct_skus or 0} SKUs · {l.total_units_quantity or 0:,} units",
                    "value": _fmt_money(l.ask_price_surplus_payout, l.currency or "USD") if l.ask_price_surplus_payout else "—",
                    "status": (l.enquiry_status or "pending").replace("_", " ").title(),
                    "status_raw": (l.enquiry_status or "").lower(),
                    "created_at": _fmt_dt(l.created_at),
                },
            })

    if type_f in ("", "partnership") and not blocked_f:
        for pe in part_qs.order_by("-created_at")[:limit_each]:
            rows.append({
                "id": pe.id,
                "drill_kind": "",
                "detail_url": "/admin/enquiries/partnership/",
                "sort_dt": pe.created_at,
                "cells": {
                    "type": "Partnership",
                    "reference": pe.name,
                    "email": pe.email,
                    "phone": "—",
                    "subject": pe.subject or pe.partnership_interest or "Partnership",
                    "value": "—",
                    "status": (pe.status or "PENDING").title(),
                    "status_raw": (pe.status or "").lower(),
                    "created_at": _fmt_dt(pe.created_at),
                },
            })

    if type_f in ("", "contact"):
        for ce in cont_qs.order_by("-created_at")[:limit_each]:
            rows.append({
                "id": ce.id,
                "drill_kind": "",
                "detail_url": "/admin/enquiries/contact-us/",
                "sort_dt": ce.created_at,
                "cells": {
                    "type": "Contact",
                    "reference": ce.full_name,
                    "email": ce.email,
                    "phone": ce.phone or "—",
                    "subject": ce.enquiry_type or (ce.message[:45] if ce.message else "General"),
                    "value": "—",
                    "status": "Blocked" if ce.is_blocked else (ce.status or "PENDING").title(),
                    "status_raw": "declined" if ce.is_blocked else (ce.status or "").lower(),
                    "created_at": _fmt_dt(ce.created_at),
                },
            })

    sort_param = request.GET.get("sort", "-created_at")
    reverse = sort_param != "created_at"
    rows.sort(key=lambda r: r["sort_dt"].timestamp() if r["sort_dt"] else 0, reverse=reverse)

    total_all = prod_cnt + lot_cnt + part_cnt + cont_cnt
    kpis = [
        _kpi_card("ALL ENQUIRIES", f"{total_all:,}"),
        _kpi_card("SELLER PRODUCTS", f"{prod_cnt:,}", "primary"),
        _kpi_card("BULK LOTS", f"{lot_cnt:,}", "warning"),
        _kpi_card("PARTNERSHIP", f"{part_cnt:,}", "success"),
        _kpi_card("CONTACT / SUPPORT", f"{cont_cnt:,}", "neutral"),
    ]

    columns = [
        _col("type", "Type", sortable=False),
        _col("reference", "Reference / Name", sortable=False),
        _col("email", "Email", sortable=False),
        _col("phone", "Phone", sortable=False),
        _col("subject", "Subject / Interest", sortable=False),
        _col("value", "Est. Value", align="right", sortable=False),
        _col("status", "Status", kind="badge", sortable=False),
        _col("created_at", "Created", sortable=True),
    ]

    filters = [
        _filter_def("q", "Search", "text", placeholder="Name, email, subject, code..."),
        _filter_def("type", "Source Type", "select", [("seller_product", "Seller Product"), ("lot", "Lot Submission"), ("partnership", "Partnership"), ("contact", "Contact / Support")]),
        _filter_def("status", "Status", "select", [("PENDING", "Pending"), ("APPROVED", "Approved"), ("DECLINED", "Declined"), ("CORRECTION_NEEDED", "Needs Correction"), ("REVIEWED", "Reviewed"), ("CONTACTED", "Contacted")]),
        _filter_def("is_blocked", "Blocked (Contact)", "select", [("yes", "Blocked Only"), ("no", "Not Blocked")]),
        _filter_def("period", "Created", "select", [("7d", "Last 7 Days"), ("30d", "Last 30 Days"), ("90d", "Last 90 Days"), ("all", "All Time")]),
    ]

    if for_export:
        return columns, rows

    paginator, page_obj = _paginate(rows, request.GET.get("page", 1))
    return {
        "report_type": "enquiries",
        "title": "Enquiries & Leads Report",
        "subtitle": "Unified inbox across live Seller Products, Bulk Lots, Partnership leads, and Contact enquiries.",
        "kpis": kpis,
        "columns": columns,
        "filters": filters,
        "rows": list(page_obj),
        "paginator": paginator,
        "page_obj": page_obj,
        "active_sort": "-created_at" if reverse else "created_at",
        "dev_note": "Combines live products, lots, partnership_enquiries, and contact_us_enquiries (unlike legacy seller_product_enquiries / lot_batch_enquiries).",
    }


def _build_auctions_report(request, is_privileged=True, for_export=False):
    from .models import Auction, AuctionBid, MainCategory

    q = request.GET.get("q", "").strip()
    status_f = request.GET.get("status", "").strip()
    itype_f = request.GET.get("item_type", "").strip()
    cat_f = request.GET.get("category", "").strip()
    buy_now_f = request.GET.get("buy_now", "").strip()
    min_bid = _parse_decimal(request.GET.get("min_bid"))
    max_bid = _parse_decimal(request.GET.get("max_bid"))
    period_f = request.GET.get("period", "all").strip()

    qs = Auction.objects.select_related("category", "vendor", "winner").only(
        "id",
        "auction_id",
        "title",
        "item_type",
        "starting_bid",
        "current_bid",
        "reserve_price",
        "total_bids",
        "views_count",
        "currency",
        "status",
        "end_time",
        "created_at",
        "category__id",
        "category__name",
        "vendor__id",
        "vendor__company_name",
        "winner__id",
        "winner__username",
        "winner__email",
    )

    if q:
        qs = qs.filter(
            Q(auction_id__icontains=q)
            | Q(title__icontains=q)
            | Q(item_reference_id__icontains=q)
        )
    if status_f:
        qs = qs.filter(status__iexact=status_f)
    if itype_f:
        qs = qs.filter(item_type__iexact=itype_f)
    if cat_f:
        qs = qs.filter(category__name__iexact=cat_f)
    if buy_now_f == "yes":
        qs = qs.filter(buy_now_price__isnull=False, buy_now_price__gt=0)
    elif buy_now_f == "no":
        qs = qs.filter(Q(buy_now_price__isnull=True) | Q(buy_now_price=0))
    if min_bid is not None:
        qs = qs.filter(current_bid__gte=min_bid)
    if max_bid is not None:
        qs = qs.filter(current_bid__lte=max_bid)

    start_dt = _parse_period_start(period_f)
    if start_dt:
        qs = qs.filter(created_at__gte=start_dt)

    sort_map = {
        "auction_id": "auction_id",
        "title": "title",
        "item_type": "item_type",
        "category": "category__name",
        "starting_bid": "starting_bid",
        "current_bid": "current_bid",
        "reserve_price": "reserve_price",
        "total_bids": "total_bids",
        "status": "status",
        "end_time": "end_time",
    }
    qs, active_sort = _safe_order_by(qs, request.GET.get("sort"), sort_map, "-created_at")

    stats = qs.aggregate(
        total=Count("id"),
        live=Count("id", filter=Q(status__iexact="live")),
        scheduled=Count("id", filter=Q(status__iexact="scheduled")),
        ended_sold=Count("id", filter=Q(status__in=["ended", "sold", "reserve_not_met"])),
        bids_sum=Sum("total_bids"),
    )
    kpis = [
        _kpi_card("TOTAL AUCTIONS", f"{stats['total'] or 0:,}"),
        _kpi_card("LIVE", f"{stats['live'] or 0:,}", "success"),
        _kpi_card("SCHEDULED", f"{stats['scheduled'] or 0:,}", "warning"),
        _kpi_card("ENDED / SOLD", f"{stats['ended_sold'] or 0:,}", "neutral"),
        _kpi_card("TOTAL BIDS", f"{stats['bids_sum'] or 0:,}", "primary"),
    ]

    columns = [
        _col("auction_id", "Auction #", kind="code"),
        _col("title", "Title"),
        _col("item_type", "Item Type"),
        _col("category", "Category"),
        _col("starting_bid", "Start Bid", align="right"),
        _col("current_bid", "Current Bid", align="right"),
    ]
    if is_privileged:
        columns.append(_col("reserve_price", "Reserve", align="right"))
    columns.extend([
        _col("total_bids", "Bids", align="right"),
        _col("winner", "Winner", sortable=False),
        _col("status", "Status", kind="badge"),
        _col("end_time", "Ends"),
    ])

    categories = cache.get("rpt_prod_cats")
    if categories is None:
        categories = list(MainCategory.objects.filter(is_active=True).order_by("name").values_list("name", flat=True))
        cache.set("rpt_prod_cats", categories, 300)

    filters = [
        _filter_def("q", "Search", "text", placeholder="Auction #, title, ref..."),
        _filter_def("status", "Status", "select", [("draft", "Draft"), ("scheduled", "Scheduled"), ("live", "Live"), ("ended", "Ended"), ("sold", "Sold"), ("reserve_not_met", "Reserve Not Met"), ("cancelled", "Cancelled")]),
        _filter_def("item_type", "Item Type", "select", [("custom", "Custom"), ("lot", "Lot"), ("product", "Product")]),
        _filter_def("category", "Category", "select", [(c, c) for c in categories]),
        _filter_def("buy_now", "Buy-Now", "select", [("yes", "Enabled"), ("no", "Disabled")]),
        _filter_def("min_bid", "Min Bid", "number", placeholder="0"),
        _filter_def("max_bid", "Max Bid", "number", placeholder="Any"),
        _filter_def("period", "Created", "select", [("7d", "Last 7 Days"), ("30d", "Last 30 Days"), ("90d", "Last 90 Days"), ("all", "All Time")]),
    ]

    def _serialize_row(a):
        curr = a.currency or "USD"
        winner_lbl = (a.winner.company_name or a.winner.full_name or a.winner.username) if a.winner else "—"
        cells = {
            "auction_id": a.auction_id,
            "title": a.title,
            "item_type": (a.item_type or "custom").title(),
            "category": a.category.name if a.category else "—",
            "starting_bid": _fmt_money(a.starting_bid, curr),
            "current_bid": _fmt_money(a.current_bid, curr),
            "total_bids": f"{a.total_bids:,}",
            "winner": winner_lbl,
            "status": a.get_status_display(),
            "status_raw": (a.status or "").lower(),
            "end_time": _fmt_dt(a.end_time),
        }
        if is_privileged:
            cells["reserve_price"] = _fmt_money(a.reserve_price, curr)
        return {
            "id": a.id,
            "drill_kind": "auction",
            "detail_url": f"/admin/auctions/{a.id}/",
            "cells": cells,
        }

    if for_export:
        items = list(qs[:10000])
        return columns, [_serialize_row(a) for a in items]

    paginator, page_obj = _paginate(qs, request.GET.get("page", 1))
    return {
        "report_type": "auctions",
        "title": "Auctions Report",
        "subtitle": "Auction listings and competitive bidding activity. Row click opens bid ledger.",
        "kpis": kpis,
        "columns": columns,
        "filters": filters,
        "rows": [_serialize_row(a) for a in page_obj],
        "paginator": paginator,
        "page_obj": page_obj,
        "active_sort": active_sort,
        "dev_note": "Maps to auctions.* + auction_bids. Reserve price is restricted to Admin/SuperAdmin roles.",
    }


# ==============================================================================
# VIEW ENDPOINTS & DRILL-DOWNS
# ==============================================================================

REPORT_BUILDERS = {
    "products": _build_products_report,
    "lots": _build_lots_report,
    "users": _build_users_report,
    "rfqs": _build_rfqs_report,
    "enquiries": _build_enquiries_report,
}


def report_table_view(request, report_type: str):
    admin_user = _auth_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    is_priv = _is_privileged_admin(admin_user)
    if report_type == "auctions":
        ctx_data = _build_auctions_report(request, is_privileged=is_priv, for_export=False)
    elif report_type in REPORT_BUILDERS:
        ctx_data = REPORT_BUILDERS[report_type](request, for_export=False)
    else:
        return redirect("reports_dashboard")

    # Pre-resolve ordered cells & sort targets for fast, clean Django template rendering
    cols = ctx_data.get("columns", [])
    active_sort = ctx_data.get("active_sort", "-created_at")
    for c in cols:
        if c.get("sortable"):
            c["is_asc"] = (active_sort == c["key"])
            c["is_desc"] = (active_sort == f"-{c['key']}")
            c["next_sort"] = f"-{c['key']}" if c["is_asc"] else c["key"]

    for r in ctx_data.get("rows", []):
        cells = r.get("cells", {})
        s_raw = cells.get("status_raw", "")
        r["ordered_cells"] = [
            {
                "key": c["key"],
                "value": cells.get(c["key"], "—"),
                "align": c.get("align", "left"),
                "kind": c.get("kind", "text"),
                "status_raw": s_raw,
            }
            for c in cols
        ]

    # Pre-attach current value onto filter definitions for clean template rendering
    for flt in ctx_data.get("filters", []):
        flt["value"] = request.GET.get(flt["name"], "")

    # Preserve active filter params cleanly for pagination & export links
    query_dict = request.GET.copy()
    query_dict.pop("page", None)
    base_qs = query_dict.urlencode()

    ctx_data.update({
        "admin": admin_user,
        "is_super_admin": getattr(admin_user, "account_type", "") == "SuperAdmin",
        "base_qs": base_qs,
    })
    return render(request, "report_table.html", ctx_data)


def report_drilldown_api(request, kind: str, obj_id: int):
    admin_user = _auth_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    if kind == "lot":
        from .models import Lot
        lot = Lot.objects.filter(id=obj_id).first()
        if not lot:
            return JsonResponse({"success": False, "message": "Lot not found."}, status=404)
        items = list(
            lot.products.all().order_by("id")[:200]
        )
        return JsonResponse({
            "success": True,
            "title": f"Lot Manifest: {lot.lot_number} — {lot.title}",
            "detail_url": f"/admin/enquiries/lots/{lot.id}/",
            "headers": ["Product ID", "Product Name", "Quantity", "Condition"],
            "rows": [
                [it.product_id, it.product_name or "—", f"{it.quantity:,}", it.condition or "—"]
                for it in items
            ],
        })

    if kind == "rfq":
        from .models import RfqEnquiry
        rfq = RfqEnquiry.objects.filter(id=obj_id).first()
        if not rfq:
            return JsonResponse({"success": False, "message": "RFQ not found."}, status=404)
        items = list(rfq.items.all().order_by("id")[:200])
        curr = rfq.currency or "USD"
        return JsonResponse({
            "success": True,
            "title": f"RFQ Line Items: {rfq.reference}",
            "detail_url": f"/admin/rfq-requests/{rfq.id}/",
            "headers": ["Item", "Type", "SKU / Code", "Qty", "Unit Price", "Target Price"],
            "rows": [
                [
                    it.title,
                    (it.item_type or "product").title(),
                    it.sku or "—",
                    f"{it.quantity:,}",
                    _fmt_money(it.unit_price, curr),
                    _fmt_money(it.target_price, curr) if it.target_price is not None else "—",
                ]
                for it in items
            ],
        })

    if kind == "auction":
        from .models import Auction
        auction = Auction.objects.filter(id=obj_id).first()
        if not auction:
            return JsonResponse({"success": False, "message": "Auction not found."}, status=404)
        bids = list(auction.bids.select_related("bidder").order_by("-amount", "-created_at")[:200])
        curr = auction.currency or "USD"
        return JsonResponse({
            "success": True,
            "title": f"Bid Ledger: {auction.auction_id} — {auction.title}",
            "detail_url": f"/admin/auctions/{auction.id}/",
            "headers": ["Bidder", "Amount", "Bid Type", "Winning", "Placed At"],
            "rows": [
                [
                    (b.bidder.company_name or b.bidder.full_name or b.bidder.email) if b.bidder else "—",
                    _fmt_money(b.amount, curr),
                    (b.bid_type or "manual").title(),
                    "Winning" if b.is_winning else "Outbid",
                    b.created_at.strftime("%d %b %Y %H:%M") if b.created_at else "—",
                ]
                for b in bids
            ],
        })

    if kind == "product":
        from .models import Product
        prod = Product.objects.select_related("category", "subcategory", "vendor").prefetch_related("images").filter(id=obj_id).first()
        if not prod:
            return JsonResponse({"success": False, "message": "Product not found."}, status=404)
        curr = prod.currency or "USD"
        imgs = [img.url for img in prod.images.all()[:6] if img.url]
        return JsonResponse({
            "success": True,
            "title": f"{prod.product_code or prod.product_id} — {prod.product_name}",
            "detail_url": f"/admin/products/{prod.id}/",
            "images": imgs,
            "headers": ["Attribute", "Value"],
            "rows": [
                ["Product Code", prod.product_code or prod.product_id],
                ["Listing ID", prod.product_id],
                ["Model No", prod.model_no or "—"],
                ["Brand", prod.brand_name or "—"],
                ["Category", f"{prod.category.name if prod.category else '—'} / {prod.subcategory.name if prod.subcategory else '—'}"],
                ["Quantity", f"{prod.quantity:,}"],
                ["Buyer Price", _fmt_money(prod.current_price, curr)],
                ["Liquidation Price", _fmt_money(prod.liquidating_price, curr)],
                ["MSRP", _fmt_money(prod.msrp, curr) if prod.msrp else "—"],
                ["Inventory Location", f"{prod.inventory_country or '—'} {prod.inventory_location or ''}".strip()],
            ],
        })

    return JsonResponse({"success": False, "message": "Unsupported drilldown type."}, status=400)


def export_report_data(request, report_type: str):
    """
    Exports any report table (honoring active URL filters) to CSV (default) or Excel (.xlsx via ?format=xlsx).
    Maintains backward compatibility with /admin/reports/export/rfq/ alias as well as /rfqs/.
    """
    admin_user = _auth_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    alias_map = {"rfq": "rfqs"}
    normalized_type = alias_map.get(report_type, report_type)
    is_priv = _is_privileged_admin(admin_user)

    if normalized_type == "auctions":
        columns, rows = _build_auctions_report(request, is_privileged=is_priv, for_export=True)
    elif normalized_type in REPORT_BUILDERS:
        columns, rows = REPORT_BUILDERS[normalized_type](request, for_export=True)
    else:
        return redirect("reports_dashboard")

    fmt = (request.GET.get("format") or "csv").strip().lower()
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    headers = [c["label"] for c in columns]
    keys = [c["key"] for c in columns]

    if fmt == "xlsx":
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = normalized_type.title()[:31]
            ws.append(headers)
            hdr_fill = PatternFill(start_color="0A5C48", end_color="0A5C48", fill_type="solid")
            hdr_font = Font(color="FFFFFF", bold=True)
            for cell in ws[1]:
                cell.fill = hdr_fill
                cell.font = hdr_font

            for r in rows:
                ws.append([r["cells"].get(k, "") for k in keys])

            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            resp = HttpResponse(
                buf.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            resp["Content-Disposition"] = f'attachment; filename="{normalized_type}_report_{timestamp}.xlsx"'
            return resp
        except Exception as e:
            logger.warning("XLSX export failed, falling back to CSV: %s", e)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{normalized_type}_report_{timestamp}.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r["cells"].get(k, "") for k in keys])
    return response
