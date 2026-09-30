from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    api_root,
    health_check,
    ItemViewSet,
    get_public_pages_list,
    get_public_page_detail,
    get_public_navigation_menu,
    get_public_blogs_list,
    get_public_blog_detail,
    submit_seller_enquiry,
    submit_lot_enquiry,
    submit_partnership_enquiry,
    submit_contact_us_enquiry,
    send_registration_otp,
    verify_registration_otp,
    complete_profile,
    send_login_otp,
    verify_login_otp,
    submit_product_request,
    submit_lot_request,
    track_view_api,
)

router = DefaultRouter()
router.register(r"items", ItemViewSet, basename="item")

urlpatterns = [
    path("", api_root, name="api-root"),
    path("health/", health_check, name="health-check"),
    
    # Analytics View Tracking
    path("analytics/track-view/", track_view_api, name="track_view_api"),
    path("track-view/", track_view_api, name="track_view_api_alt"),

    
    # Headless CMS Public REST APIs for Frontend Server
    path("pages/", get_public_pages_list, name="public_pages_list"),
    path("pages/navigation/", get_public_navigation_menu, name="public_pages_navigation"),
    path("pages/<slug:slug>/", get_public_page_detail, name="public_page_detail"),

    # Public Blog REST APIs
    path("blogs/", get_public_blogs_list, name="public_blogs_list"),
    path("blogs/<slug:slug>/", get_public_blog_detail, name="public_blog_detail"),

    # Public Enquiry Submissions
    path("enquiries/seller/", submit_seller_enquiry, name="public_seller_enquiry_submit"),
    path("enquiries/lots/", submit_lot_enquiry, name="public_lot_enquiry_submit"),
    path("enquiries/contact-us/", submit_contact_us_enquiry, name="public_contact_us_enquiry_submit"),
    path("enquiries/partnership/", submit_partnership_enquiry, name="public_partnership_enquiry_submit"),
    path("enquiries/partnership-enquiry/", submit_partnership_enquiry, name="public_partnership_enquiry_submit_alias"),
    path("partnership-enquiry/", submit_partnership_enquiry, name="public_partnership_enquiry_submit_legacy"),
    path("contact-us/", submit_contact_us_enquiry, name="public_contact_us_enquiry_submit_alt"),



    # Vendor Registration and Login OTP flows
    path("auth/register/send-otp/", send_registration_otp, name="send_registration_otp"),
    path("auth/register/verify-otp/", verify_registration_otp, name="verify_registration_otp"),
    path("auth/register/complete-profile/", complete_profile, name="complete_profile"),
    path("auth/login/send-otp/", send_login_otp, name="send_login_otp"),
    path("auth/login/verify-otp/", verify_login_otp, name="verify_login_otp"),

    # Submissions
    path("submit-product-request/", submit_product_request, name="submit_product_request"),
    path("submit-lot-request/", submit_lot_request, name="submit_lot_request"),

    # Additional user endpoints (Wishlist, RFQ) will be added here
    path("", include(router.urls)),
]
