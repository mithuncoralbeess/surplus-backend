from django.urls import path
from django.shortcuts import redirect
from .views import (
    vendor_login_page,
    vendor_register,
    vendor_login,
    vendor_logout_view,
    get_current_vendor,
    admin_login_page,
    admin_register,
    admin_login,
    admin_logout_view,
    get_current_admin,
    super_admin_password_reset,
    super_admin_verify_otp,
    adminDashBoard,
    xlsxDashBoard,
    adminIndex,
    excel_test_view,
    content_pages_view,
    content_page_editor_view,
    content_pages_api,
    content_blogs_view,
    content_blog_editor_view,
    content_blogs_api,
    seller_enquiries_view,
    seller_enquiry_detail_view,
    lot_enquiries_view,
    lot_enquiry_detail_view,
    add_lot_view,
    seller_enquiry_status_api,
    seller_enquiry_edit_api,
    lot_enquiry_status_api,
    lot_enquiry_edit_api,
    upload_lot_manifest_api,
    parse_lot_spreadsheet_api,
    save_lot_products_api,
    manage_users_view,
    delete_user_api,
    contact_enquiries_view,
    page_views_analytics_view,
    whatsapp_enquiries_view,
    partnership_enquiries_view,

    main_categories_view,
    all_products_view,
    toggle_product_status_view,
    add_product_view,
    price_control_view,
    update_charge_percentage,
    price_control_apply,
    product_detail_view,
    brands_management_view,
    brands_delete_api,
    brands_batch_delete_api,
    price_control_preview_api,
    price_control_rollback_api,
    toggle_maintenance_mode_api,
    popup_view,
    admin_auctions_view,
    admin_auction_create_view,
    admin_auction_detail_view,
    admin_auction_action_api,
    product_collections_view,
    update_product_collection_api,
    search_products_api,
)

urlpatterns = [
    # Vendor Login Screen (HTML Page & POST handler)
    path('vendor-login/', vendor_login, name='vendor_login_page'),
    path('vendor-register/', vendor_register, name='vendor_register'),
    path('vendor-logout/', vendor_logout_view, name='vendor_logout'),
    path('vendor-me/', get_current_vendor, name='vendor_me'),

    # Admin Login Screen (HTML Page & POST handler)
    path("login/", admin_login, name="admin_login_page"),
    path("register/", admin_register, name="admin_register"),
    path("logout/", admin_logout_view, name="admin_logout"),
    path("me/", get_current_admin, name="admin_me"),

    # Password Reset & OTP Flow
    path("password-reset/", super_admin_password_reset, name="super_admin_password_reset"),
    path("verify-otp/", super_admin_verify_otp, name="super_admin_verify_otp"),

    # Dashboards (HTML View & JSON API)
    path("dashboard/", adminDashBoard, name="adminDashBoard"),
    path("xlsx-dashboard/", xlsxDashBoard, name="xlsxDashBoard"),
    path("vendor-index/", adminIndex, name="adminIndex"),
    path("excel-test/", excel_test_view, name="excel_test_view"),
    path("popup/", popup_view, name="popup_view"),

    # Content Manager: Pages
    path("content/pages/", content_pages_view, name="content_pages_view"),
    path("content/pages/create/", content_page_editor_view, name="content_page_create"),
    path("content/pages/<int:page_id>/edit/", content_page_editor_view, name="content_page_edit"),
    path("api/content/pages/", content_pages_api, name="content_pages_api_list"),
    path("api/content/pages/<int:page_id>/", content_pages_api, name="content_pages_api_detail"),
    path("content/pages/api/", content_pages_api, name="content_pages_api_alt_list"),
    path("content/pages/api/<int:page_id>/", content_pages_api, name="content_pages_api_alt_detail"),

    # Content Manager: Blogs
    path("content/blogs/", content_blogs_view, name="content_blogs_view"),
    path("content/blogs/create/", content_blog_editor_view, name="content_blog_create"),
    path("content/blogs/<int:blog_id>/edit/", content_blog_editor_view, name="content_blog_edit"),
    path("api/content/blogs/", content_blogs_api, name="content_blogs_api_list"),
    path("api/content/blogs/<int:blog_id>/", content_blogs_api, name="content_blogs_api_detail"),

    # Enquiries: Seller Product Enquiries (PRO-XXXXX)
    path("enquiries/seller/", seller_enquiries_view, name="seller_enquiries_list"),
    path("enquiries/seller/", seller_enquiries_view, name="seller_enquiries"),
    path("enquiries/seller/<int:enquiry_id>/detail/", seller_enquiry_detail_view, name="seller_enquiry_detail"),
    path("enquiries/seller/<str:status_filter>/", seller_enquiries_view, name="seller_enquiries_filtered"),
    path("api/enquiries/seller/<int:enquiry_id>/status/", seller_enquiry_status_api, name="seller_enquiry_status_api"),
    path("api/enquiries/seller/<int:enquiry_id>/edit/", seller_enquiry_edit_api, name="seller_enquiry_edit_api"),

    # Enquiries: Lot Batch Enquiries (BLK-XXXXX)
    path("lots/add/", add_lot_view, name="add_lot"),
    path("enquiries/lots/add/", add_lot_view, name="add_lot_alias"),
    path("enquiries/lots/", lot_enquiries_view, name="lot_enquiries_list"),
    path("enquiries/lots/<int:enquiry_id>/detail/", lot_enquiry_detail_view, name="lot_enquiry_detail"),
    path("enquiries/lots/<str:status_filter>/", lot_enquiries_view, name="lot_enquiries_filtered"),
    path("api/enquiries/lots/<int:enquiry_id>/status/", lot_enquiry_status_api, name="lot_enquiry_status_api"),
    path("api/enquiries/lots/<int:enquiry_id>/edit/", lot_enquiry_edit_api, name="lot_enquiry_edit_api"),
    path("api/enquiries/lots/<int:enquiry_id>/upload-manifest/", upload_lot_manifest_api, name="upload_lot_manifest_api"),
    path("api/enquiries/lots/<int:enquiry_id>/parse/", parse_lot_spreadsheet_api, name="parse_lot_spreadsheet_api"),
    path("api/enquiries/lots/<int:enquiry_id>/parse-spreadsheet/", parse_lot_spreadsheet_api, name="parse_lot_spreadsheet_api_alt"),
    path("api/enquiries/lots/<int:enquiry_id>/save-products/", save_lot_products_api, name="save_lot_products_api"),
    # User Management (Registered Users List without RFQs/Products)
    path("users/", manage_users_view, name="manage_users"),
    path("manage-users/", manage_users_view, name="manage_users_alias"),
    path("users/<int:user_id>/delete/", delete_user_api, name="delete_user"),
    path("api/users/<int:user_id>/delete/", delete_user_api, name="delete_user_api"),

    # Redirect legacy sellers-buyers to manage users
    path("sellers-buyers/", lambda request: redirect("manage_users")),

    # Analytics & Traffic Tracking
    path("analytics/page-views/", page_views_analytics_view, name="page_views_analytics"),
    path("analytics/traffic/", page_views_analytics_view, name="page_views_analytics_alt"),

    # Contact Us Enquiries
    path("enquiries/contact-us/", contact_enquiries_view, name="contact_enquiries"),

    path("enquiries/whatsapp/", whatsapp_enquiries_view, name="whatsapp_enquiries"),
    path("enquiries/partnership/", partnership_enquiries_view, name="partnership_enquiries"),

    # Category Management
    path("categories/main/", main_categories_view, name="main_categories"),

    # Product Management
    path("products/all/", all_products_view, name="all_products"),
    path("products/collections/", product_collections_view, name="product_collections"),
    path("api/products/collections/update/", update_product_collection_api, name="update_product_collection_api"),
    path("api/products/search/", search_products_api, name="admin_search_products_api"),
    path("products/<int:product_id>/toggle-status/", toggle_product_status_view, name="toggle_product_status"),
    path("products/add/", add_product_view, name="add_product"),
    path("products/price-control/", price_control_view, name="price_control"),
    path("products/price-control/update-charge/", update_charge_percentage, name="update_charge_percentage"),
    path("products/price-control/apply/", price_control_apply, name="price_control_apply"),
    path("api/products/price-control/preview/", price_control_preview_api, name="price_control_preview_api"),
    path("api/products/price-control/rollback/<int:log_id>/", price_control_rollback_api, name="price_control_rollback_api"),
    path("products/<int:product_id>/", product_detail_view, name="product_detail"),

    # Brand Management (Landing Page Brands)
    path("brands/", brands_management_view, name="brands_management"),
    path("api/brands/<int:brand_id>/delete/", brands_delete_api, name="brands_delete_api"),
    path("api/brands/batch-delete/", brands_batch_delete_api, name="brands_batch_delete_api"),

    # Maintenance Mode Toggle API
    path("api/maintenance/toggle/", toggle_maintenance_mode_api, name="toggle_maintenance_mode_api"),

    # Auctions Management (Model-Agnostic Engine)
    path("auctions/", admin_auctions_view, name="admin_auctions_view"),
    path("auctions/create/", admin_auction_create_view, name="admin_auction_create"),
    path("auctions/<str:auction_id>/", admin_auction_detail_view, name="admin_auction_detail"),
    path("api/auctions/<str:auction_id>/action/", admin_auction_action_api, name="admin_auction_action_api"),
]
