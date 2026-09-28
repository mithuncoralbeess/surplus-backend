"""
URL configuration for config project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from api import views as api_views

urlpatterns = [
    # Django Dashboard for registration & staff management
    path("django-admin/", admin.site.urls),

    # Staff / Admin Portal & Login Screen
    path("admin/", include("AdminApp.urls")),

    # Root redirect to admin login
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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
