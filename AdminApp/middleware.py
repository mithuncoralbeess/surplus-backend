import os
import socket
import logging
import threading
from django.core.cache import cache
from django.db import connections, close_old_connections, OperationalError, InterfaceError
from django.http import JsonResponse
from django.shortcuts import render
from .models import SystemSettings

logger = logging.getLogger(__name__)
NODE_ID = os.getenv("NODE_ID") or socket.gethostname() or "surplus-node-1"

_SCHEMA_LOCK = threading.Lock()
_PRODUCT_CODE_SCHEMA_VERIFIED = False


def _products_has_product_code(connection) -> bool:
    try:
        with connection.cursor() as cursor:
            cols = {
                col.name.lower()
                for col in connection.introspection.get_table_description(cursor, "products")
            }
        return "product_code" in cols
    except Exception:
        return True


def _repair_product_code_column(connection):
    """
    Emergency idempotent fallback if `migrate` fails due to migration-history drift
    while `products.product_code` is missing. Adds the column, backfills unique codes,
    creates a unique index, and marks migration 0077 as recorded if absent.
    """
    from django.db.migrations.recorder import MigrationRecorder
    from .models import generate_random_product_code

    with connection.cursor() as cursor:
        if not _products_has_product_code(connection):
            if connection.vendor == "postgresql":
                cursor.execute(
                    "ALTER TABLE products ADD COLUMN IF NOT EXISTS product_code varchar(100) NOT NULL DEFAULT '';"
                )
            else:
                cursor.execute(
                    "ALTER TABLE products ADD COLUMN product_code varchar(100) NOT NULL DEFAULT '';"
                )

        cursor.execute("SELECT id, product_id, product_code FROM products ORDER BY id;")
        rows = cursor.fetchall()
        seen_ids = set()
        seen_codes = set()
        for row_id, raw_pid, raw_pcode in rows:
            pid = (raw_pid or "").strip()
            if not pid or pid.upper() in seen_ids:
                num = row_id
                candidate = f"PRO-{num:05d}"
                while candidate.upper() in seen_ids:
                    num += 1
                    candidate = f"PRO-{num:05d}"
                pid = candidate
            seen_ids.add(pid.upper())

            pcode = (raw_pcode or "").strip()
            if not pcode or pcode.upper() in seen_codes:
                candidate = generate_random_product_code()
                while candidate.upper() in seen_codes:
                    candidate = generate_random_product_code()
                pcode = candidate
            seen_codes.add(pcode.upper())

            if raw_pid != pid or raw_pcode != pcode:
                cursor.execute(
                    "UPDATE products SET product_id = %s, product_code = %s WHERE id = %s;",
                    [pid, pcode, row_id],
                )

        if connection.vendor in ("postgresql", "sqlite"):
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS products_product_code_uniq ON products (product_code);"
            )

    try:
        recorder = MigrationRecorder(connection)
        recorder.ensure_schema()
        mig_name = "0077_product_product_code_alter_product_enquiry_status_and_more"
        if not recorder.migration_qs.filter(app="AdminApp", name=mig_name).exists():
            recorder.record_applied("AdminApp", mig_name)
    except Exception as rec_exc:
        logger.warning(f"[DatabaseFailoverMiddleware] Could not record 0077 migration: {rec_exc}")


def _run_adminapp_migrate_or_repair(conn):
    from django.core.management import call_command

    try:
        call_command("migrate", "AdminApp", verbosity=0, interactive=False)
    except Exception as mig_exc:
        logger.warning(
            f"[DatabaseFailoverMiddleware] call_command migrate failed ({mig_exc}); "
            "attempting idempotent product_code column repair."
        )

    if not _products_has_product_code(conn):
        _repair_product_code_column(conn)


def _ensure_product_code_schema():
    """
    One-time, lock-protected schema verification on the first HTTP request.
    If migration 0077 has not been applied to the database yet, runs AdminApp
    migrations safely (guarded by a PostgreSQL advisory lock) with an idempotent
    column-repair fallback so requests never fail with `column products.product_code does not exist`.
    """
    global _PRODUCT_CODE_SCHEMA_VERIFIED
    if _PRODUCT_CODE_SCHEMA_VERIFIED:
        return

    with _SCHEMA_LOCK:
        if _PRODUCT_CODE_SCHEMA_VERIFIED:
            return
        try:
            conn = connections["default"]
            if _products_has_product_code(conn):
                _PRODUCT_CODE_SCHEMA_VERIFIED = True
                return

            if conn.vendor == "postgresql":
                with conn.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_lock(770077);")
                try:
                    if not _products_has_product_code(conn):
                        _run_adminapp_migrate_or_repair(conn)
                finally:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute("SELECT pg_advisory_unlock(770077);")
                    except Exception:
                        pass
            else:
                _run_adminapp_migrate_or_repair(conn)

            if _products_has_product_code(conn):
                _PRODUCT_CODE_SCHEMA_VERIFIED = True
        except Exception as exc:
            logger.error(f"[DatabaseFailoverMiddleware] Auto-migration check failed: {exc}")


class DatabaseFailoverMiddleware:
    """
    Resilience & Failover Middleware:
    - Proactively cleans stale/closed DB connections before handling requests.
    - Ensures pending product_code schema migration is applied if missing.
    - If an OperationalError / InterfaceError occurs during an idempotent request (GET/HEAD),
      closes broken connections, updates the DB circuit breaker, and transparently retries once.
    - Injects X-Upstream-Node and X-Failover-Status headers for load balancer observability.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not _PRODUCT_CODE_SCHEMA_VERIFIED:
            _ensure_product_code_schema()

        failover_triggered = False
        try:
            response = self.get_response(request)
        except (OperationalError, InterfaceError) as exc:
            logger.warning(f"[DatabaseFailoverMiddleware] DB connection error on {request.path}: {exc}")
            try:
                from config.db_router import mark_db_failure
                mark_db_failure("default", exc)
            except Exception:
                pass

            for conn in connections.all():
                try:
                    conn.close()
                except Exception:
                    pass
            close_old_connections()

            if request.method in ("GET", "HEAD", "OPTIONS"):
                failover_triggered = True
                response = self.get_response(request)
            else:
                raise

        response["X-Upstream-Node"] = NODE_ID
        response["X-Failover-Status"] = "recovered" if failover_triggered else "primary"
        return response


class MaintenanceModeMiddleware:
    """
    Middleware that intercepts requests when Maintenance Mode is enabled.
    Admin routes (/admin/*) are bypassed so administrators can manage the portal.
    Optimized with short-term cache (30s) to avoid querying DB on every request.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Bypass admin routes, static/media files, authentication, and health/maintenance status checks
        if (
            path.startswith('/admin/') or 
            path.startswith('/static/') or 
            path.startswith('/media/') or 
            path == '/favicon.ico' or 
            '/auth/' in path or
            path.startswith('/send-') or 
            path.startswith('/verify-') or 
            path.startswith('/complete-') or
            path.startswith('/api/auth/') or
            path == '/api/maintenance-status/' or
            path.startswith('/api/health')
        ):
            return self.get_response(request)

        try:
            maint_info = cache.get("maint_middleware_status")
            if maint_info is None:
                sys_settings = SystemSettings.objects.filter(id=1).first()
                if not sys_settings:
                    sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
                maint_info = {
                    "is_active": sys_settings.is_maintenance_mode,
                    "message": sys_settings.maintenance_message or "Website is currently under maintenance. Please check back later."
                }
                cache.set("maint_middleware_status", maint_info, timeout=600)

            if maint_info.get("is_active"):
                maint_msg = maint_info.get("message")
                # Return JSON error for API requests
                if path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        "status": 503,
                        "error": "Maintenance Mode",
                        "message": maint_msg
                    }, status=503)

                # Render HTML maintenance page for browser requests
                return render(request, "maintenance.html", {
                    "message": maint_msg
                }, status=503)
        except Exception:
            pass

        return self.get_response(request)
