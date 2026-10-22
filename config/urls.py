"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.contrib.staticfiles.storage import staticfiles_storage
from django.views.generic.base import RedirectView
from api import views as api_views

urlpatterns = [
    # Favicon route
    path("favicon.ico", RedirectView.as_view(url=staticfiles_storage.url("images/favicon.ico"))),

    # Django Dashboard for registration & staff management
    path("django-admin/", admin.site.urls),

    # Staff / Admin Portal & Login Screen
    path("admin/", include("AdminApp.urls")),

    # Root redirect & aliases to admin / vendor login
    path("admin_login/", lambda request: redirect("admin_login_page")),
    path("admin-login/", lambda request: redirect("admin_login_page")),
    path("vendor_login/", lambda request: redirect("vendor_login_page")),
    path("vendor-login/", lambda request: redirect("vendor_login_page")),
    path("login/", lambda request: redirect("admin_login_page")),
    path("", lambda request: redirect("admin_login_page")),

    # General APIs
    path("api/", include("api.urls")),
    
    # Frontend Auth Endpoints (Root Level)
    path("send-registration-otp/", api_views.send_registration_otp),
    path("verify-registration-otp/", api_views.verify_registration_otp),
    path("complete-profile/", api_views.complete_profile),
    path("send-login-otp/", api_views.send_login_otp),
    path("verify-login-otp/", api_views.verify_login_otp),
    
    path("submit-product-request/", api_views.submit_product_request),
    path("submit-lot-request/", api_views.submit_lot_request),
    
    # Lots App
    path("", include("lots.urls")),
]

import urllib.parse
from django.views.static import serve
from django.urls import re_path
from django.http import Http404

def robust_media_serve(request, path, document_root=None, show_indexes=False):
    """
    Serves media files while gracefully handling differences in URL encoding
    (e.g., spaces vs %20 vs %2520).
    """
    candidates = [path]
    unquoted = urllib.parse.unquote(path)
    if unquoted not in candidates:
        candidates.append(unquoted)
    double_unquoted = urllib.parse.unquote(unquoted)
    if double_unquoted not in candidates:
        candidates.append(double_unquoted)
    quoted = urllib.parse.quote(unquoted)
    if quoted not in candidates:
        candidates.append(quoted)

    for cand in candidates:
        try:
            return serve(request, cand, document_root=document_root, show_indexes=show_indexes)
        except Http404:
            continue
    raise Http404("Media file not found")

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", robust_media_serve, {"document_root": settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


from django.http import JsonResponse

def custom_handler500(request):
    origin = request.headers.get("Origin", "*")
    response = JsonResponse({
        "success": False,
        "status": 500,
        "message": "Internal Server Error. Please try again later."
    }, status=500)
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Allow-Credentials"] = "true"
    response["Access-Control-Allow-Headers"] = "*"
    return response

handler500 = "config.urls.custom_handler500"
