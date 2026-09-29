from django.http import JsonResponse
from django.shortcuts import render
from .models import SystemSettings

class MaintenanceModeMiddleware:
    """
    Middleware that intercepts requests when Maintenance Mode is enabled.
    Admin routes (/admin/*) are bypassed so administrators can manage the portal.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Bypass admin routes, static/media files, and authentication
        if (
            path.startswith('/admin/') or 
            path.startswith('/static/') or 
            path.startswith('/media/') or 
            path == '/favicon.ico' or path.startswith('/send-') or path.startswith('/verify-') or path.startswith('/complete-')
        ):
            return self.get_response(request)

        try:
            sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
            if sys_settings.is_maintenance_mode:
                # Return JSON error for API requests
                if path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        "status": 503,
                        "error": "Maintenance Mode",
                        "message": sys_settings.maintenance_message or "Website is currently under maintenance. Please check back later."
                    }, status=503)

                # Render HTML maintenance page for browser requests
                return render(request, "maintenance.html", {
                    "message": sys_settings.maintenance_message or "Website is currently under maintenance. Please check back later."
                }, status=503)
        except Exception:
            pass

        return self.get_response(request)
