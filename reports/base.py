"""
Base generic ListAPIView and helpers for Surplus Market Reports API.
Implements:
  - ReportListView with config-driven SEGMENTS and FILTERS
  - Unified server-side pagination (default 50/page)
  - Segments aggregation (Count with filter)
  - Date filtering (date_field, date_from, date_to)
  - Response contract: {"rows": [...], "total": int, "segment_counts": {...}}
  - Streaming exports for CSV and Excel (.xlsx) capped at 50k rows
  - Admin authentication gating via AdminDetails session or Django staff
"""

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.core.cache import cache
from django.db.models import Count, Q
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

logger = logging.getLogger(__name__)


def since(days: int):
    """Returns a timezone-aware datetime `days` in the past."""
    return timezone.now() - timedelta(days=days)


class IsReportsAdminUser(permissions.BasePermission):
    """
    Permission check for Reports APIs.
    Accepts:
      1. Active AdminDetails session (request.session['adminid'])
      2. Django authenticated staff / superuser
    """

    def has_permission(self, request, view):
        from AdminApp.views import _get_authenticated_admin

        admin = _get_authenticated_admin(request)
        if admin:
            request.admin_user = admin
            return True

        user = getattr(request, "user", None)
        if user and user.is_authenticated and (user.is_staff or user.is_superuser):
            request.admin_user = user
            return True

        return False


class ReportsPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        return Response({
            "rows": data,
            "total": self.page.paginator.count,
        })


class EchoCSV:
    """An object that implements just the write method of the file-like interface for CSV streaming."""
    def write(self, value):
        return value


class ReportListView(ListAPIView):
    """
    Base generic view for all config-driven reports.
    Subclasses define:
      - model: Django Model class
      - serializer_class: DRF Serializer
      - SEGMENTS: dict of segment_key -> {"q": Q(...), "sort": "field"}
      - FILTERS: dict of query_param -> lambda value: Q(...)
      - DATE_FIELDS: list of allowed date fields, e.g. ["created_at"]
      - export_fields: list of tuple(label, attr_or_callable) for CSV/XLSX
    """

    permission_classes = [IsReportsAdminUser]
    pagination_class = ReportsPagination
    model = None
    serializer_class = None
    SEGMENTS: Dict[str, Dict[str, Any]] = {}
    FILTERS: Dict[str, Any] = {}
    DATE_FIELDS: List[str] = ["created_at"]
    export_fields: List[tuple] = []
    MAX_EXPORT_ROWS = 50000

    def base_qs(self):
        """Override per report (select_related, prefetch_related, annotate)."""
        if self.model is not None:
            return self.model.objects.all()
        return super().get_queryset()

    def soft_delete_filter(self, qs):
        """Soft-delete hook: override per report if model uses soft-delete or archive flags."""
        return qs

    def get_queryset(self):
        qs = self.base_qs()
        if not self.request.query_params.get("include_archived"):
            qs = self.soft_delete_filter(qs)

        # Segment filter
        segment_key = self.request.query_params.get("segment", "all")
        seg = self.SEGMENTS.get(segment_key, {})
        if seg.get("q"):
            qs = qs.filter(seg["q"])

        # Per-report parameter filters
        for param, make_q in self.FILTERS.items():
            val = self.request.query_params.get(param)
            if val in (None, "", "all"):
                continue
            qs = qs.filter(make_q(val))

        # Shared date range filter
        qs = self.apply_date(qs)

        # Server-side sorting: request param > segment default > "-created_at"
        sort = self.request.query_params.get("sort") or seg.get("sort", "-created_at")
        try:
            qs = qs.order_by(sort)
        except Exception:
            qs = qs.order_by("-id")

        return qs

    def apply_date(self, qs):
        field = self.request.query_params.get("date_field", self.DATE_FIELDS[0])
        if field not in self.DATE_FIELDS:
            field = self.DATE_FIELDS[0]

        frm = self.request.query_params.get("date_from")
        to = self.request.query_params.get("date_to")

        if frm:
            qs = qs.filter(**{f"{field}__gte": frm})
        if to:
            to_val = to.strip()
            if len(to_val) == 10:
                qs = qs.filter(**{f"{field}__lte": f"{to_val} 23:59:59"})
            else:
                qs = qs.filter(**{f"{field}__lte": to_val})
        return qs

    def segment_counts(self):
        """
        Calculates counts for each segment in one single SQL query using Count('id', filter=Q(...)).
        """
        qs = self.base_qs()
        if not self.request.query_params.get("include_archived"):
            qs = self.soft_delete_filter(qs)

        # Apply per-report filters (except segment) so tab badges reflect current search & facet context
        for param, make_q in self.FILTERS.items():
            val = self.request.query_params.get(param)
            if val in (None, "", "all"):
                continue
            try:
                qs = qs.filter(make_q(val))
            except Exception:
                pass

        aggregations = {}
        for key, seg in self.SEGMENTS.items():
            if seg.get("q"):
                aggregations[key] = Count("id", filter=seg["q"])
            else:
                aggregations[key] = Count("id")

        try:
            return qs.aggregate(**aggregations)
        except Exception as e:
            logger.warning("Error computing segment_counts: %s", e)
            return {k: 0 for k in self.SEGMENTS.keys()}

    def list(self, request, *args, **kwargs):
        export_type = (request.query_params.get("export") or "").lower().strip()
        if export_type in ("csv", "xlsx", "excel"):
            return self.export_response(request, export_type)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response({
                "rows": serializer.data,
                "total": self.paginator.page.paginator.count,
                "segment_counts": self.segment_counts(),
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "rows": serializer.data,
            "total": queryset.count(),
            "segment_counts": self.segment_counts(),
        })

    def export_response(self, request, export_type: str):
        """
        Streams full filtered queryset without pagination up to MAX_EXPORT_ROWS.
        """
        queryset = self.get_queryset()[:self.MAX_EXPORT_ROWS]
        serializer = self.get_serializer(queryset, many=True)
        rows_data = serializer.data

        report_name = (self.__class__.__name__.lower().replace("reportview", "").replace("report", "")) or "report"
        timestamp = timezone.now().strftime("%Y%m%d_%H%M")

        if export_type == "csv":
            return self._stream_csv(rows_data, f"{report_name}_report_{timestamp}.csv")
        else:
            return self._export_xlsx(rows_data, f"{report_name}_report_{timestamp}.xlsx")

    def _stream_csv(self, rows_data: List[dict], filename: str):
        if not rows_data:
            response = HttpResponse("No data available for export\n", content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        # Determine columns
        if self.export_fields:
            headers = [col[0] for col in self.export_fields]
            keys = [col[1] for col in self.export_fields]
        else:
            first_row = rows_data[0]
            headers = list(first_row.keys())
            keys = headers

        def row_generator():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(headers)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

            for row in rows_data:
                row_vals = []
                for k in keys:
                    if callable(k):
                        val = k(row)
                    elif isinstance(k, str):
                        val = row.get(k, "")
                    else:
                        val = ""
                    row_vals.append(str(val) if val is not None else "")
                writer.writerow(row_vals)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        response = StreamingHttpResponse(row_generator(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _export_xlsx(self, rows_data: List[dict], filename: str):
        try:
            import openpyxl
        except ImportError:
            # Fallback to CSV if openpyxl is not installed
            return self._stream_csv(rows_data, filename.replace(".xlsx", ".csv"))

        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(title="Report")

        if self.export_fields:
            headers = [col[0] for col in self.export_fields]
            keys = [col[1] for col in self.export_fields]
        elif rows_data:
            headers = list(rows_data[0].keys())
            keys = headers
        else:
            headers = ["No data"]
            keys = []

        ws.append(headers)

        for row in rows_data:
            row_vals = []
            for k in keys:
                if callable(k):
                    val = k(row)
                elif isinstance(k, str):
                    val = row.get(k, "")
                else:
                    val = ""
                # Ensure complex objects (dict/list) convert to string for openpyxl
                if isinstance(val, (dict, list)):
                    val = str(val)
                row_vals.append(val)
            ws.append(row_vals)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

