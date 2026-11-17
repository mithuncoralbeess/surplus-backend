"""
Reports Module Views.
Implements:
  - ProductsReportView (/api/reports/products)
  - LotsReportView (/api/reports/lots) + LotItemsDrilldownView (/api/reports/lots/<id>/items)
  - UsersReportView (/api/reports/users)
  - RfqsReportView (/api/reports/rfqs) + RfqItemsDrilldownView (/api/reports/rfqs/<id>/items)
  - AuctionsReportView (/api/reports/auctions)
  - EnquiriesReportView (/api/reports/enquiries) - unified cross-table leads inbox
  - SummaryReportView (/api/reports/summary) - Command Center with 60s cache
"""

import csv
import io
import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List

from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import connection
from django.db.models import Avg, Count, F, Q, Sum
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from AdminApp.models import (
    Auction,
    ContactUsEnquiry,
    Lot,
    LotBatchEnquiry,
    LotProduct,
    PartnershipEnquiry,
    Product,
    RfqEnquiry,
    RfqEnquiryItem,
    SellerProductEnquiry,
    VendorDetails,
)
from .base import IsReportsAdminUser, ReportListView, since
from .serializers import (
    AuctionReportSerializer,
    LotProductDrilldownSerializer,
    LotReportSerializer,
    ProductReportSerializer,
    RfqEnquiryItemSerializer,
    RfqReportSerializer,
    UserReportSerializer,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Products Report
# ==============================================================================
class ProductsReportView(ReportListView):
    """
    Products Report Endpoint: GET /api/reports/products
    Segments: needs_approval, live, declined, all
    """

    model = Product
    serializer_class = ProductReportSerializer
    DATE_FIELDS = ["created_at", "date_approved"]

    SEGMENTS = {
        "needs_approval": {
            "q": Q(enquiry_status__in=["PENDING", "CORRECTION_NEEDED"]),
            "sort": "created_at",
        },
        "live": {
            "q": Q(enquiry_status="APPROVED", is_active=True),
            "sort": "-created_at",
        },
        "declined": {
            "q": Q(enquiry_status="DECLINED"),
            "sort": "-created_at",
        },
        "all": {
            "sort": "-created_at",
        },
    }

    FILTERS = {
        "search": lambda v: (
            Q(product_name__icontains=v)
            | Q(product_id__icontains=v)
            | Q(brand_name__icontains=v)
            | Q(model_no__icontains=v)
            | Q(product_code__icontains=v)
        ),
        "category": lambda v: Q(category_id=v),
        "subcategory": lambda v: Q(subcategory_id=v),
        "brand": lambda v: Q(brand_name__iexact=v),
        "country": lambda v: Q(inventory_country=v) | Q(manufacturing_country=v),
        "price_min": lambda v: Q(current_price__gte=v),
        "price_max": lambda v: Q(current_price__lte=v),
        "qty_min": lambda v: Q(quantity__gte=v),
        "qty_max": lambda v: Q(quantity__lte=v),
        "intake": lambda v: Q(intake_channel=v),
        "flag": lambda v: Q(**{f"is_{v}": True}),
        "msrp_min": lambda v: Q(msrp__gte=v),
        "msrp_max": lambda v: Q(msrp__lte=v),
        "offer_min": lambda v: Q(offer__gte=v),
        "currency": lambda v: Q(currency=v),
        "vendor": lambda v: Q(vendor_id=v),
        "certificate": lambda v: Q(third_party_certificate=(v.lower() in ("yes", "true", "1"))),
    }

    export_fields = [
        ("ID", "id"),
        ("Product ID", "product_id"),
        ("Name", "name"),
        ("Category", "category"),
        ("Subcategory", "subcategory"),
        ("Brand", "brand"),
        ("Quantity", "qty"),
        ("Buyer Price", "buyer_price"),
        ("MSRP", "msrp"),
        ("Offer", "offer"),
        ("Currency", "currency"),
        ("Country", "inventory_country"),
        ("Age (Days)", "age_days"),
        ("Status", "status"),
        ("Vendor", "vendor"),
        ("Created At", "created_at"),
    ]

    def base_qs(self):
        return (
            Product.objects.select_related("vendor", "category", "subcategory")
            .prefetch_related("images")
        )


# ==============================================================================
# 2. Lots Report & Drilldown
# ==============================================================================
class LotsReportView(ReportListView):
    """
    Lots Report Endpoint: GET /api/reports/lots
    Segments: pending, live, declined, all
    """

    model = Lot
    serializer_class = LotReportSerializer
    DATE_FIELDS = ["created_at"]

    SEGMENTS = {
        "pending": {
            "q": Q(enquiry_status="pending"),
            "sort": "created_at",
        },
        "live": {
            "q": Q(enquiry_status="approved", is_active=True),
            "sort": "-created_at",
        },
        "declined": {
            "q": Q(enquiry_status="declined"),
            "sort": "-created_at",
        },
        "all": {
            "sort": "-created_at",
        },
    }

    FILTERS = {
        "search": lambda v: (
            Q(title__icontains=v)
            | Q(lot_number__icontains=v)
            | Q(key_brands_included__icontains=v)
        ),
        "condition": lambda v: Q(condition__icontains=v),
        "source": lambda v: Q(source_type__icontains=v),
        "sale_method": lambda v: Q(sale_method=v),
        "load_type": lambda v: Q(load_type=v),
        "country": lambda v: Q(inventory_country=v),
        "value_min": lambda v: Q(total_est_retail_value_msrp__gte=v),
        "value_max": lambda v: Q(total_est_retail_value_msrp__lte=v),
        "ask_min": lambda v: Q(ask_price_surplus_payout__gte=v),
        "ask_max": lambda v: Q(ask_price_surplus_payout__lte=v),
        "units_min": lambda v: Q(total_units_quantity__gte=v),
        "skus_min": lambda v: Q(number_of_distinct_skus__gte=v),
        "pallet_min": lambda v: Q(pallet_count__gte=v),
        "stock_age": lambda v: Q(inventory_stock_age=v),
        "vendor": lambda v: Q(vendor_id=v),
        "certificate": lambda v: Q(third_party_certificate_available=(v.lower() in ("yes", "true", "1"))),
    }

    export_fields = [
        ("ID", "id"),
        ("Lot Number", "lot_number"),
        ("Title", "title"),
        ("Condition", "condition"),
        ("Source", "source_type"),
        ("Sale Method", "sale_method"),
        ("Load Type", "load_type"),
        ("Country", "inventory_country"),
        ("Est MSRP Value", "total_est_retail_value_msrp"),
        ("Surplus Ask Price", "ask_price_surplus_payout"),
        ("% of Retail", "pct_of_retail"),
        ("Units", "total_units_quantity"),
        ("SKUs", "number_of_distinct_skus"),
        ("Pallets", "pallet_count"),
        ("Vendor", "vendor"),
        ("Status", "enquiry_status"),
        ("Created At", "created_at"),
    ]

    def base_qs(self):
        return Lot.objects.select_related("vendor")


class LotItemsDrilldownView(ListAPIView):
    """
    Manifest Drill-down: GET /api/reports/lots/<id>/items
    Returns all items within a lot.
    """

    permission_classes = [IsReportsAdminUser]
    serializer_class = LotProductDrilldownSerializer

    def get_queryset(self):
        lot_id = self.kwargs.get("pk")
        return LotProduct.objects.filter(Q(lot_id=lot_id) | Q(lot__lot_number=str(lot_id))).order_by("id")


# ==============================================================================
# 3. Users / Vendors Report
# ==============================================================================
class UsersReportView(ReportListView):
    """
    Users & Vendors Report Endpoint: GET /api/reports/users
    Segments: new, buyers, sellers, all
    """

    model = VendorDetails
    serializer_class = UserReportSerializer
    DATE_FIELDS = ["created_at"]

    SEGMENTS = {
        "new": {
            "q": Q(created_at__gte=since(30)),
            "sort": "-created_at",
        },
        "buyers": {
            "q": Q(user_type__in=["BUYER", "BOTH"]),
            "sort": "-created_at",
        },
        "sellers": {
            "q": Q(user_type__in=["SELLER", "BOTH"]),
            "sort": "-created_at",
        },
        "all": {
            "sort": "-created_at",
        },
    }

    FILTERS = {
        "search": lambda v: (
            Q(full_name__icontains=v)
            | Q(email__icontains=v)
            | Q(company_name__icontains=v)
            | Q(username__icontains=v)
            | Q(mobile_number__icontains=v)
        ),
        "user_type": lambda v: Q(user_type=v),
        "entity": lambda v: Q(account_entity_type=v),
        "country": lambda v: Q(country=v),
        "business_type": lambda v: Q(business_type__icontains=v),
        "category": lambda v: Q(category_interested__contains=v),
        "status": lambda v: Q(status=(v.lower() in ("active", "true", "1"))),
        "has_company": lambda v: (
            Q(company_name__isnull=False) & ~Q(company_name="")
            if v.lower() in ("yes", "true", "1")
            else (Q(company_name__isnull=True) | Q(company_name=""))
        ),
    }

    export_fields = [
        ("ID", "id"),
        ("Username", "username"),
        ("Full Name", "full_name"),
        ("Email", "email"),
        ("Mobile", "mobile_number"),
        ("Company", "company_name"),
        ("Role / User Type", "user_type"),
        ("Entity", "entity"),
        ("Country", "country"),
        ("Business Type", "business_type"),
        ("Status", "status"),
        ("Registered At", "created_at"),
    ]


# ==============================================================================
# 4. RFQs Report & Drilldown
# ==============================================================================
class RfqsReportView(ReportListView):
    """
    RFQs Demand Report Endpoint: GET /api/reports/rfqs
    Segments: open, pending, accepted, all
    """

    model = RfqEnquiry
    serializer_class = RfqReportSerializer
    DATE_FIELDS = ["created_at"]

    SEGMENTS = {
        "open": {
            "q": Q(status__in=["PENDING", "QUOTED"]),
            "sort": "created_at",
        },
        "pending": {
            "q": Q(status="PENDING"),
            "sort": "created_at",
        },
        "accepted": {
            "q": Q(status="ACCEPTED"),
            "sort": "-created_at",
        },
        "all": {
            "sort": "-created_at",
        },
    }

    FILTERS = {
        "search": lambda v: (
            Q(reference__icontains=v)
            | Q(company_name__icontains=v)
            | Q(email__icontains=v)
            | Q(contact_person__icontains=v)
            | Q(phone__icontains=v)
        ),
        "country": lambda v: Q(country=v),
        "dest_port": lambda v: Q(destination_port__icontains=v),
        "incoterm": lambda v: Q(incoterm=v),
        "payment": lambda v: Q(payment_method=v),
        "item_type": lambda v: Q(items__item_type=v),
        "category": lambda v: Q(items__category__icontains=v),
        "value_min": lambda v: Q(estimated_value__gte=v),
        "value_max": lambda v: Q(estimated_value__lte=v),
        "units_min": lambda v: Q(total_units__gte=v),
        "buyer": lambda v: Q(buyer_id=v) | Q(company_name__icontains=v),
    }

    export_fields = [
        ("ID", "id"),
        ("RFQ Reference", "reference"),
        ("Buyer", "buyer"),
        ("Company", "company_name"),
        ("Email", "email"),
        ("Phone", "phone"),
        ("Country", "country"),
        ("Destination Port", "destination_port"),
        ("Incoterm", "incoterm"),
        ("Payment Method", "payment_method"),
        ("Est Value", "estimated_value"),
        ("Units", "total_units"),
        ("Items Count", "item_count"),
        ("Status", "status"),
        ("Created At", "created_at"),
    ]

    def base_qs(self):
        return (
            RfqEnquiry.objects.select_related("buyer")
            .annotate(item_count=Count("items", distinct=True))
            .distinct()
        )


class RfqItemsDrilldownView(ListAPIView):
    """
    Items Drill-down: GET /api/reports/rfqs/<id>/items
    Returns all items associated with an RFQ request.
    """

    permission_classes = [IsReportsAdminUser]
    serializer_class = RfqEnquiryItemSerializer

    def get_queryset(self):
        rfq_id = self.kwargs.get("pk")
        return RfqEnquiryItem.objects.filter(Q(rfq_id=rfq_id) | Q(rfq__reference=str(rfq_id))).order_by("id")


# ==============================================================================
# 5. Auctions Report
# ==============================================================================
class AuctionsReportView(ReportListView):
    """
    Auctions Report Endpoint: GET /api/reports/auctions
    Segments: live, scheduled, closed, all
    """

    model = Auction
    serializer_class = AuctionReportSerializer
    DATE_FIELDS = ["created_at", "start_time", "end_time"]

    SEGMENTS = {
        "live": {
            "q": Q(status="live"),
            "sort": "end_time",
        },
        "scheduled": {
            "q": Q(status="scheduled"),
            "sort": "start_time",
        },
        "closed": {
            "q": Q(status__in=["ended", "sold", "reserve_not_met"]),
            "sort": "-end_time",
        },
        "all": {
            "sort": "-created_at",
        },
    }

    FILTERS = {
        "search": lambda v: Q(title__icontains=v) | Q(auction_id__icontains=v),
        "item_type": lambda v: Q(item_type=v),
        "category": lambda v: Q(category_id=v),
        "bid_min": lambda v: Q(current_bid__gte=v),
        "bid_max": lambda v: Q(current_bid__lte=v),
        "reserve_min": lambda v: Q(reserve_price__gte=v),
        "buy_now": lambda v: (
            Q(buy_now_price__isnull=False)
            if v.lower() in ("yes", "true", "1")
            else Q(buy_now_price__isnull=True)
        ),
        "vendor": lambda v: Q(vendor_id=v),
    }

    export_fields = [
        ("ID", "id"),
        ("Auction ID", "auction_id"),
        ("Title", "title"),
        ("Item Type", "item_type"),
        ("Category", "category"),
        ("Vendor", "vendor"),
        ("Currency", "currency"),
        ("Starting Bid", "starting_bid"),
        ("Current Bid", "current_bid"),
        ("Reserve Price", "reserve_price"),
        ("Buy Now Price", "buy_now_price"),
        ("Total Bids", "total_bids"),
        ("Status", "status"),
        ("Start Time", "start_time"),
        ("End Time", "end_time"),
        ("Created At", "created_at"),
    ]

    def base_qs(self):
        return Auction.objects.select_related("category", "vendor")


# ==============================================================================
# 6. Enquiries & Leads Report (Multi-source normalized in-memory)
# ==============================================================================
class EnquiriesReportView(APIView):
    """
    Enquiries & Leads Report Endpoint: GET /api/reports/enquiries
    Normalises four underlying source tables into a unified inbox:
      1. SellerProductEnquiry / Product
      2. LotBatchEnquiry / Lot
      3. PartnershipEnquiry
      4. ContactUsEnquiry
    """

    permission_classes = [IsReportsAdminUser]

    def get(self, request):
        type_filter = (request.query_params.get("type") or "").strip().lower()
        search = (request.query_params.get("search") or "").strip().lower()
        status_filter = (request.query_params.get("status") or "").strip().lower()
        country_filter = (request.query_params.get("country") or "").strip().lower()
        category_filter = (request.query_params.get("category") or "").strip().lower()
        is_blocked_filter = (request.query_params.get("is_blocked") or "").strip().lower()
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        # 1. Gather Seller Product Enquiries (check SellerProductEnquiry + pending Products)
        seller_rows = []
        if type_filter in ("", "all", "seller_product", "product"):
            spe_qs = SellerProductEnquiry.objects.select_related("vendor")
            if date_from:
                spe_qs = spe_qs.filter(created_at__gte=date_from)
            if date_to:
                spe_qs = spe_qs.filter(created_at__lte=f"{date_to} 23:59:59" if len(date_to) == 10 else date_to)
            for o in spe_qs:
                seller_rows.append({
                    "id": f"spe_{o.id}",
                    "raw_id": o.id,
                    "type": "Seller product",
                    "source_key": "seller_product",
                    "name": o.title,
                    "email": o.vendor.email if o.vendor else "",
                    "value": o.price,
                    "status": o.enquiry_status,
                    "country": o.manufacturing_country or "",
                    "category": "",
                    "is_blocked": False,
                    "created": o.created_at,
                })

            # Also check Product table pending/submissions if SellerProductEnquiry is sparse
            prod_qs = Product.objects.select_related("vendor", "category").filter(
                enquiry_status__in=["PENDING", "CORRECTION_NEEDED"]
            )
            if date_from:
                prod_qs = prod_qs.filter(created_at__gte=date_from)
            if date_to:
                prod_qs = prod_qs.filter(created_at__lte=f"{date_to} 23:59:59" if len(date_to) == 10 else date_to)
            for p in prod_qs:
                seller_rows.append({
                    "id": f"prod_{p.id}",
                    "raw_id": p.id,
                    "type": "Seller product",
                    "source_key": "seller_product",
                    "name": p.product_name,
                    "email": p.vendor.email if p.vendor else "",
                    "value": p.current_price or p.liquidating_price,
                    "status": p.enquiry_status,
                    "country": p.inventory_country or p.manufacturing_country or "",
                    "category": p.category.name if p.category else "",
                    "is_blocked": False,
                    "created": p.created_at,
                })

        # 2. Gather Lot Batch Enquiries (check LotBatchEnquiry + pending Lots)
        lot_rows = []
        if type_filter in ("", "all", "lot_batch", "lot"):
            lbe_qs = LotBatchEnquiry.objects.select_related("uploaded_by")
            if date_from:
                lbe_qs = lbe_qs.filter(created_at__gte=date_from)
            if date_to:
                lbe_qs = lbe_qs.filter(created_at__lte=f"{date_to} 23:59:59" if len(date_to) == 10 else date_to)
            for o in lbe_qs:
                lot_rows.append({
                    "id": f"lbe_{o.id}",
                    "raw_id": o.id,
                    "type": "Lot batch",
                    "source_key": "lot_batch",
                    "name": o.title,
                    "email": o.uploaded_by.email if o.uploaded_by else "",
                    "value": o.total_price or o.ask_price_surplus_payout,
                    "status": o.enquiry_status,
                    "country": o.inventory_location or "",
                    "category": "",
                    "is_blocked": False,
                    "created": o.created_at,
                })

            lot_qs = Lot.objects.select_related("vendor").filter(enquiry_status="pending")
            if date_from:
                lot_qs = lot_qs.filter(created_at__gte=date_from)
            if date_to:
                lot_qs = lot_qs.filter(created_at__lte=f"{date_to} 23:59:59" if len(date_to) == 10 else date_to)
            for l in lot_qs:
                lot_rows.append({
                    "id": f"lot_{l.id}",
                    "raw_id": l.id,
                    "type": "Lot batch",
                    "source_key": "lot_batch",
                    "name": l.title,
                    "email": l.vendor.email if l.vendor else "",
                    "value": l.ask_price_surplus_payout or l.total_est_retail_value_msrp,
                    "status": l.enquiry_status,
                    "country": l.inventory_country or "",
                    "category": "",
                    "is_blocked": False,
                    "created": l.created_at,
                })

        # 3. Gather Partnership Enquiries
        part_rows = []
        if type_filter in ("", "all", "partnership"):
            part_qs = PartnershipEnquiry.objects.all()
            if date_from:
                part_qs = part_qs.filter(created_at__gte=date_from)
            if date_to:
                part_qs = part_qs.filter(created_at__lte=f"{date_to} 23:59:59" if len(date_to) == 10 else date_to)
            for o in part_qs:
                part_rows.append({
                    "id": f"part_{o.id}",
                    "raw_id": o.id,
                    "type": "Partnership",
                    "source_key": "partnership",
                    "name": o.name,
                    "email": o.email,
                    "value": None,
                    "status": o.status,
                    "country": o.business_location or "",
                    "category": o.partnership_interest or "",
                    "is_blocked": False,
                    "created": o.created_at,
                })

        # 4. Gather Contact Us Enquiries
        contact_rows = []
        if type_filter in ("", "all", "contact"):
            cont_qs = ContactUsEnquiry.objects.all()
            if date_from:
                cont_qs = cont_qs.filter(created_at__gte=date_from)
            if date_to:
                cont_qs = cont_qs.filter(created_at__lte=f"{date_to} 23:59:59" if len(date_to) == 10 else date_to)
            for o in cont_qs:
                contact_rows.append({
                    "id": f"cont_{o.id}",
                    "raw_id": o.id,
                    "type": "Contact us",
                    "source_key": "contact",
                    "name": o.full_name,
                    "email": o.email,
                    "value": None,
                    "status": o.status,
                    "country": "",
                    "category": o.enquiry_type or "",
                    "is_blocked": bool(o.is_blocked),
                    "created": o.created_at,
                })

        segment_counts = {
            "all": len(seller_rows) + len(lot_rows) + len(part_rows) + len(contact_rows),
            "seller_product": len(seller_rows),
            "lot_batch": len(lot_rows),
            "partnership": len(part_rows),
            "contact": len(contact_rows),
        }

        # Merge all active collections
        all_rows = seller_rows + lot_rows + part_rows + contact_rows

        # Apply in-memory filters
        filtered_rows = []
        for r in all_rows:
            if search:
                haystack = f"{r['name']} {r['email']} {r['country']} {r['category']}".lower()
                if search not in haystack:
                    continue
            if status_filter and status_filter != "all":
                if str(r["status"]).lower() != status_filter:
                    continue
            if country_filter and country_filter != "all":
                if country_filter not in str(r["country"]).lower():
                    continue
            if category_filter and category_filter != "all":
                if category_filter not in str(r["category"]).lower():
                    continue
            if is_blocked_filter:
                is_bl = is_blocked_filter in ("yes", "true", "1")
                if r["is_blocked"] != is_bl:
                    continue
            filtered_rows.append(r)

        # Sort descending by creation timestamp
        filtered_rows.sort(key=lambda x: x["created"] or timezone.now(), reverse=True)

        # Handle export
        export_type = (request.query_params.get("export") or "").lower().strip()
        if export_type in ("csv", "xlsx", "excel"):
            headers = ["ID", "Type", "Name / Company", "Email", "Value", "Status", "Country", "Category", "Created"]
            export_data = [
                [
                    row["id"],
                    row["type"],
                    row["name"],
                    row["email"],
                    str(row["value"]) if row["value"] is not None else "",
                    row["status"],
                    row["country"],
                    row["category"],
                    row["created"].strftime("%Y-%m-%d %H:%M") if row["created"] else "",
                ]
                for row in filtered_rows[:50000]
            ]
            timestamp = timezone.now().strftime("%Y%m%d_%H%M")
            if export_type == "csv":
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(headers)
                writer.writerows(export_data)
                resp = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
                resp["Content-Disposition"] = f'attachment; filename="enquiries_report_{timestamp}.csv"'
                return resp
            else:
                try:
                    import openpyxl
                    wb = openpyxl.Workbook(write_only=True)
                    ws = wb.create_sheet(title="Enquiries")
                    ws.append(headers)
                    for r in export_data:
                        ws.append(r)
                    buf = io.BytesIO()
                    wb.save(buf)
                    buf.seek(0)
                    resp = HttpResponse(
                        buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    resp["Content-Disposition"] = f'attachment; filename="enquiries_report_{timestamp}.xlsx"'
                    return resp
                except ImportError:
                    pass

        # Pagination
        page = request.query_params.get("page", 1)
        page_size = int(request.query_params.get("page_size", 50))
        paginator = Paginator(filtered_rows, page_size)
        try:
            paged_obj = paginator.page(page)
        except PageNotAnInteger:
            paged_obj = paginator.page(1)
        except EmptyPage:
            paged_obj = paginator.page(paginator.num_pages)

        # Format rows for JSON response
        formatted_rows = [
            {
                "id": r["id"],
                "type": r["type"],
                "name": r["name"],
                "email": r["email"],
                "value": float(r["value"]) if isinstance(r["value"], (Decimal, int, float)) else r["value"],
                "status": r["status"],
                "country": r["country"],
                "category": r["category"],
                "is_blocked": r["is_blocked"],
                "created": r["created"].isoformat() if r["created"] else None,
            }
            for r in paged_obj.object_list
        ]

        return Response({
            "rows": formatted_rows,
            "total": paginator.count,
            "segment_counts": segment_counts,
        })


# ==============================================================================
# 7. Summary / Command Center Endpoint
# ==============================================================================
class SummaryReportView(APIView):
    """
    Command Center Summary Endpoint: GET /api/reports/summary?range=30d
    Cached ~60 seconds keyed by range window.
    Returns:
      - alerts: []
      - actions: {approvals: {count, oldest_days, products, lots}, rfqs_unquoted, outliers, stale_lots}
      - kpis: [{key, label, value, delta, trend}]
      - supply_demand: [{category, supply, demand, signal}]
      - activity: [{tone, type, title, sub, ts}]
    """

    permission_classes = [IsReportsAdminUser]

    def get(self, request):
        range_param = (request.query_params.get("range") or "30d").strip().lower()
        if range_param == "7d":
            days = 7
        elif range_param == "90d":
            days = 90
        else:
            days = 30
            range_param = "30d"

        cache_key = f"reports_command_center_summary_{range_param}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        data = self.build_summary_data(days, range_param)
        cache.set(cache_key, data, timeout=60)
        return Response(data)

    def build_summary_data(self, days: int, range_label: str) -> dict:
        now = timezone.now()
        cur_start = now - timedelta(days=days)
        prev_start = now - timedelta(days=days * 2)

        # ----------------------------------------------------------------------
        # 1. Action Counts
        # ----------------------------------------------------------------------
        # Approvals: Product (PENDING/CORRECTION_NEEDED) + Lot (pending)
        p_pending = Product.objects.filter(enquiry_status__in=["PENDING", "CORRECTION_NEEDED"])
        l_pending = Lot.objects.filter(enquiry_status="pending")
        p_count = p_pending.count()
        l_count = l_pending.count()

        p_min = p_pending.aggregate(m=models_Min("created_at"))["m"] if p_count > 0 else None
        l_min = l_pending.aggregate(m=models_Min("created_at"))["m"] if l_count > 0 else None
        oldest_dates = [x for x in [p_min, l_min] if x is not None]
        oldest_ts = min(oldest_dates) if oldest_dates else None
        oldest_days = max(0, (now - oldest_ts).days) if oldest_ts else 0

        # RFQs unquoted (status='PENDING')
        rfqs_unquoted = RfqEnquiry.objects.filter(status="PENDING").count()

        # Stale lots: declined or pending > 14 days
        stale_lots = Lot.objects.filter(
            Q(enquiry_status="declined") | Q(enquiry_status="pending", created_at__lt=since(14))
        ).count()

        # Valuation Outliers (top 80% cumulative share of MSRP)
        outlier_count = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    WITH ranked AS (
                        SELECT id, product_name, msrp,
                        SUM(msrp) OVER (ORDER BY msrp DESC) AS cum,
                        SUM(msrp) OVER () AS total
                        FROM products WHERE is_active = true AND msrp IS NOT NULL
                    )
                    SELECT COUNT(*) FROM ranked WHERE cum <= 0.80 * total;
                """)
                outlier_row = cursor.fetchone()
                if outlier_row:
                    outlier_count = outlier_row[0]
        except Exception as e:
            logger.warning("Error computing valuation outliers: %s", e)
            outlier_count = 0

        actions = {
            "approvals": {
                "count": p_count + l_count,
                "oldest_days": oldest_days,
                "products": p_count,
                "lots": l_count,
            },
            "rfqs_unquoted": rfqs_unquoted,
            "outliers": outlier_count,
            "stale_lots": stale_lots,
        }

        # ----------------------------------------------------------------------
        # 2. KPIs with period-over-period delta
        # ----------------------------------------------------------------------
        # Current window vs Previous window
        cur_live = Product.objects.filter(is_active=True).count() + Lot.objects.filter(is_active=True).count()
        prev_live = (
            Product.objects.filter(is_active=True, created_at__lt=cur_start).count()
            + Lot.objects.filter(is_active=True, created_at__lt=cur_start).count()
        )

        cur_buyers = VendorDetails.objects.filter(user_type__in=["BUYER", "BOTH"]).count()
        prev_buyers = VendorDetails.objects.filter(
            user_type__in=["BUYER", "BOTH"], created_at__lt=cur_start
        ).count()

        cur_sellers = VendorDetails.objects.filter(user_type__in=["SELLER", "BOTH"]).count()
        prev_sellers = VendorDetails.objects.filter(
            user_type__in=["SELLER", "BOTH"], created_at__lt=cur_start
        ).count()

        cur_rfqs = RfqEnquiry.objects.filter(created_at__gte=cur_start).count()
        prev_rfqs = RfqEnquiry.objects.filter(created_at__gte=prev_start, created_at__lt=cur_start).count()

        cur_avg_px = Product.objects.filter(is_active=True).aggregate(a=Avg("current_price"))["a"] or 0
        prev_avg_px = (
            Product.objects.filter(is_active=True, created_at__lt=cur_start).aggregate(a=Avg("current_price"))["a"]
            or cur_avg_px
        )

        # SLA: average days from created_at to date_approved
        cur_approved = Product.objects.filter(
            enquiry_status="APPROVED", date_approved__isnull=False, date_approved__gte=cur_start
        )
        prev_approved = Product.objects.filter(
            enquiry_status="APPROVED",
            date_approved__isnull=False,
            date_approved__gte=prev_start,
            date_approved__lt=cur_start,
        )

        def calc_sla_days(qs):
            cnt = qs.count()
            if not cnt:
                return 0.0
            total_sec = sum(
                max(0, (o.date_approved - o.created_at).total_seconds())
                for o in qs[:200]
                if o.date_approved and o.created_at
            )
            return round(total_sec / (cnt * 86400.0), 1)

        cur_sla = calc_sla_days(cur_approved)
        prev_sla = calc_sla_days(prev_approved) or cur_sla

        def compute_delta(cur_v, prev_v, unit=""):
            diff = cur_v - prev_v
            if prev_v > 0:
                pct = round((diff / float(prev_v)) * 100.0, 1)
            else:
                pct = 0.0
            trend = "up" if diff > 0 else ("down" if diff < 0 else "neutral")
            return f"{'+' if diff > 0 else ''}{pct}%" if unit == "%" else f"{'+' if diff > 0 else ''}{round(diff, 1)}", trend

        delta_live, trend_live = compute_delta(cur_live, prev_live, "%")
        delta_buyers, trend_buyers = compute_delta(cur_buyers, prev_buyers, "%")
        delta_sellers, trend_sellers = compute_delta(cur_sellers, prev_sellers, "%")
        delta_rfqs, trend_rfqs = compute_delta(cur_rfqs, prev_rfqs, "%")
        delta_px, trend_px = compute_delta(float(cur_avg_px), float(prev_avg_px), "%")
        delta_sla, trend_sla = compute_delta(cur_sla, prev_sla)

        kpis = [
            {
                "key": "live_listings",
                "label": "Live Listings",
                "value": cur_live,
                "delta": delta_live,
                "trend": trend_live,
            },
            {
                "key": "active_buyers",
                "label": "Active Buyers",
                "value": cur_buyers,
                "delta": delta_buyers,
                "trend": trend_buyers,
            },
            {
                "key": "verified_sellers",
                "label": "Verified Sellers",
                "value": cur_sellers,
                "delta": delta_sellers,
                "trend": trend_sellers,
            },
            {
                "key": "rfq_demand",
                "label": f"RFQ Inquiries ({range_label})",
                "value": cur_rfqs,
                "delta": delta_rfqs,
                "trend": trend_rfqs,
            },
            {
                "key": "avg_product_price",
                "label": "Avg Product Price",
                "value": f"${float(cur_avg_px):,.2f}",
                "delta": delta_px,
                "trend": trend_px,
            },
            {
                "key": "approval_sla",
                "label": "Approval SLA",
                "value": f"{cur_sla} days",
                "delta": delta_sla,
                "trend": "down" if cur_sla < prev_sla else "up",
            },
        ]

        # ----------------------------------------------------------------------
        # 3. Supply vs Demand (Per Category)
        # ----------------------------------------------------------------------
        supply_map: Dict[str, int] = {}
        demand_map: Dict[str, int] = {}

        # Supply from active products
        prod_cats = (
            Product.objects.filter(is_active=True, category__isnull=False)
            .values("category__name")
            .annotate(n=Count("id"))
        )
        for row in prod_cats:
            cat_name = row["category__name"] or "General"
            supply_map[cat_name] = supply_map.get(cat_name, 0) + row["n"]

        # Demand from RFQ enquiry items
        rfq_cats = (
            RfqEnquiryItem.objects.exclude(category__isnull=True)
            .exclude(category="")
            .values("category")
            .annotate(n=Count("rfq", distinct=True))
        )
        for row in rfq_cats:
            cat_name = row["category"].strip()
            demand_map[cat_name] = demand_map.get(cat_name, 0) + row["n"]

        all_categories = sorted(list(set(list(supply_map.keys()) + list(demand_map.keys()))))
        supply_demand = []
        for cat in all_categories[:12]:
            s = supply_map.get(cat, 0)
            d = demand_map.get(cat, 0)
            if d > 0 and s <= d * 2:
                signal = "under_supplied"
            elif s >= 20 and (d / float(s)) < 0.1:
                signal = "over_supplied"
            else:
                signal = "balanced"
            supply_demand.append({
                "category": cat,
                "supply": s,
                "demand": d,
                "signal": signal,
            })

        # ----------------------------------------------------------------------
        # 4. Merged Activity Feed
        # ----------------------------------------------------------------------
        feed = []
        # Newest 5 pending lots
        for lot in Lot.objects.filter(enquiry_status="pending").order_by("-created_at")[:5]:
            feed.append({
                "tone": "amber",
                "type": "lot_pending",
                "title": f"New Lot Submitted: {lot.title or lot.lot_number}",
                "sub": f"Lot #{lot.lot_number} submitted by {lot.vendor.company_name if lot.vendor else 'Seller'}",
                "ts": lot.created_at.isoformat() if lot.created_at else now.isoformat(),
                "_dt": lot.created_at or now,
            })

        # Newest 5 RFQs
        for rfq in RfqEnquiry.objects.order_by("-created_at")[:5]:
            feed.append({
                "tone": "red",
                "type": "rfq",
                "title": f"RFQ Received: {rfq.reference}",
                "sub": f"{rfq.total_units or 0} units requested by {rfq.company_name or 'Buyer'}",
                "ts": rfq.created_at.isoformat() if rfq.created_at else now.isoformat(),
                "_dt": rfq.created_at or now,
            })

        # Newest 5 Sellers
        for v in VendorDetails.objects.filter(user_type__in=["SELLER", "BOTH"]).order_by("-created_at")[:5]:
            feed.append({
                "tone": "brand",
                "type": "seller",
                "title": f"New Seller Registered: {v.company_name or v.full_name or v.username}",
                "sub": f"{v.country or 'Global'} • {v.account_entity_type or 'Entity'}",
                "ts": v.created_at.isoformat() if v.created_at else now.isoformat(),
                "_dt": v.created_at or now,
            })

        feed.sort(key=lambda x: x["_dt"], reverse=True)
        for item in feed:
            item.pop("_dt", None)
        feed = feed[:10]

        # ----------------------------------------------------------------------
        # 5. Alerts
        # ----------------------------------------------------------------------
        alerts = []
        if actions["approvals"]["count"] > 0:
            alerts.append({
                "tone": "amber",
                "title": f"{actions['approvals']['count']} Pending Submissions Require Review",
                "body": (
                    f"{actions['approvals']['products']} products and {actions['approvals']['lots']} lots "
                    f"are awaiting admin approval. Oldest submission is {actions['approvals']['oldest_days']} days old."
                ),
            })
        if rfqs_unquoted > 0:
            alerts.append({
                "tone": "red",
                "title": f"{rfqs_unquoted} RFQ Inquiries Awaiting Proforma Quotation",
                "body": "Unquoted commercial demand inquiries require proforma preparation or allocation.",
            })
        if outlier_count > 0:
            alerts.append({
                "tone": "blue",
                "title": f"Valuation Concentration: {outlier_count} Items Represent Top 80% MSRP",
                "body": f"{outlier_count} active catalog items make up 80% of aggregate inventory retail valuation.",
            })

        return {
            "alerts": alerts,
            "actions": actions,
            "kpis": kpis,
            "supply_demand": supply_demand,
            "activity": feed,
        }


def models_Min(field_name):
    from django.db.models import Min
    return Min(field_name)
