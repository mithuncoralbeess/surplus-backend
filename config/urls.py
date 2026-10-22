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
    path("admin", lambda request: redirect("admin_root")),

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

import os
import urllib.parse
from django.views.static import serve
from django.urls import re_path
from django.http import Http404

def robust_media_serve(request, path, document_root=None, show_indexes=False):
    """
    Serves media files while gracefully handling differences in:
    - URL encoding (spaces vs %20 vs %2520)
    - Spaces vs underscores (WhatsApp Image vs WhatsApp_Image)
    - File extension and case differences on Linux servers (e.g. .jpeg vs .jpg, PM vs pm)
    - Prefix matches for generated upload hashes (e.g. 406086f3_*)
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

    for base in [unquoted, double_unquoted]:
        alt_under = base.replace(" ", "_")
        if alt_under not in candidates:
            candidates.append(alt_under)
        alt_space = base.replace("_", " ")
        if alt_space not in candidates:
            candidates.append(alt_space)

    for cand in candidates:
        try:
            return serve(request, cand, document_root=document_root, show_indexes=show_indexes)
        except Http404:
            continue

    # Fallback: scan target directory under document_root for case-insensitive or hash prefix match
    if document_root and os.path.isdir(str(document_root)):
        clean_target = unquoted.replace("\\", "/").strip("/")
        dir_part = os.path.dirname(clean_target)
        file_part = os.path.basename(clean_target)
        target_dir = os.path.join(str(document_root), dir_part)

        if os.path.isdir(target_dir):
            file_lower = file_part.lower()
            prefix = file_part[:9].lower() if len(file_part) > 9 and file_part[8] == "_" else None
            try:
                for entry in os.listdir(target_dir):
                    entry_lower = entry.lower()
                    if entry_lower == file_lower or entry_lower.replace(" ", "_") == file_lower.replace(" ", "_"):
                        rel = os.path.join(dir_part, entry).replace("\\", "/")
                        return serve(request, rel, document_root=document_root, show_indexes=show_indexes)
                    if prefix and entry_lower.startswith(prefix):
                        rel = os.path.join(dir_part, entry).replace("\\", "/")
                        return serve(request, rel, document_root=document_root, show_indexes=show_indexes)
            except Exception:
                pass

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
