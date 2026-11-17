"""
URL Configuration for Reports API.
Routes (with or without trailing slash):
  /api/reports/products
  /api/reports/lots
  /api/reports/lots/<id>/items
  /api/reports/users
  /api/reports/rfqs
  /api/reports/rfqs/<id>/items
  /api/reports/auctions
  /api/reports/enquiries
  /api/reports/summary
"""

from django.urls import re_path
from .views import (
    AuctionsReportView,
    EnquiriesReportView,
    LotItemsDrilldownView,
    LotsReportView,
    ProductsReportView,
    RfqItemsDrilldownView,
    RfqsReportView,
    SummaryReportView,
    UsersReportView,
)

urlpatterns = [
    # 6 Core Report List Endpoints
    re_path(r"^products/?$", ProductsReportView.as_view(), name="report_products"),
    re_path(r"^lots/?$", LotsReportView.as_view(), name="report_lots"),
    re_path(r"^users/?$", UsersReportView.as_view(), name="report_users"),
    re_path(r"^rfqs/?$", RfqsReportView.as_view(), name="report_rfqs"),
    re_path(r"^auctions/?$", AuctionsReportView.as_view(), name="report_auctions"),
    re_path(r"^enquiries/?$", EnquiriesReportView.as_view(), name="report_enquiries"),

    # Drill-down Endpoints
    re_path(r"^lots/(?P<pk>[^/]+)/items/?$", LotItemsDrilldownView.as_view(), name="report_lot_items"),
    re_path(r"^rfqs/(?P<pk>[^/]+)/items/?$", RfqItemsDrilldownView.as_view(), name="report_rfq_items"),

    # Command Center Summary Endpoint
    re_path(r"^summary/?$", SummaryReportView.as_view(), name="report_summary"),
]
