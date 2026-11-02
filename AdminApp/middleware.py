import os
import socket
import logging
from django.core.cache import cache
from django.db import connections, close_old_connections, OperationalError, InterfaceError
from django.http import JsonResponse
from django.shortcuts import render
from .models import SystemSettings

logger = logging.getLogger(__name__)
NODE_ID = os.getenv("NODE_ID") or socket.gethostname() or "surplus-node-1"


class DatabaseFailoverMiddleware:
    """
    Resilience & Failover Middleware:
    - Proactively cleans stale/closed DB connections before handling requests.
    - If an OperationalError / InterfaceError occurs during an idempotent request (GET/HEAD),
      closes broken connections, updates the DB circuit breaker, and transparently retries once.
    - Injects X-Upstream-Node and X-Failover-Status headers for load balancer observability.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
