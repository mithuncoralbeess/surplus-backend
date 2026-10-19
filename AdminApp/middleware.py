from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from .models import SystemSettings

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

        # Bypass admin routes, static/media files, authentication, and maintenance status check
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
            path == '/api/health/'
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
