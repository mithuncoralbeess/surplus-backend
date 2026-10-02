import uuid
import hashlib
import random
import secrets
from decimal import Decimal
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db.models import Q, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
# 11

from .models import (
    AdminDetails,
    VendorDetails,
    AdminPasswordResetOTP,
    ContentPage,
    BlogPost,
    SellerProductEnquiry,
    LotBatchEnquiry,
    PartnershipEnquiry,
    ContactUsEnquiry,
    PageViewLog,
    MainCategory,
    SubCategory,
    Lot,
    LotProduct,
    Product,
    ProductImage,
    SystemSettings,
)
from .services import EmailService
from .serializers import (
    AdminRegisterSerializer,
    AdminLoginSerializer,
    AdminDetailsSerializer,
    VendorRegisterSerializer,
    VendorDetailsSerializer,
    SuperAdminPasswordResetSerializer,
    SuperAdminVerifyOTPSerializer,
    ContentPageSerializer,
)


def _get_authenticated_admin(request):
    """
    Helper to check session version validity against database & cache.
    Optimized with short-term cache lookup to avoid redundant DB queries per request.
    """
    admin_id = request.session.get("adminid")
    session_version = request.session.get("session_version")

    if not admin_id or session_version is None:
        return None

    cache_key = f"admin_obj_{admin_id}"
    admin_user = cache.get(cache_key)

    if not admin_user:
        try:
            admin_user = AdminDetails.objects.get(id=admin_id, status=True)
            cache.set(cache_key, admin_user, 60)
        except AdminDetails.DoesNotExist:
            return None

    cached_version = cache.get(f"admin_version_{admin_user.id}")
    current_version = (
        cached_version
        if cached_version is not None
        else admin_user.session_version
    )
    if session_version != current_version:
        cache.delete(cache_key)
        return None
    return admin_user


def admin_login_page(request):
    """
    Renders the rich Admin Login Screen template.
    If already logged in, redirects to the user's role dashboard.
    """
    admin_user = _get_authenticated_admin(request)
    if admin_user:
        if admin_user.email == "super@gmail.com" or admin_user.account_type == "SuperAdmin":
            return redirect("adminDashBoard")
        elif admin_user.email == "xlsxsurplusadmin@gmail.com" or admin_user.account_type == "XLSXAdmin":
            return redirect("xlsxDashBoard")
        elif admin_user.account_type == "Vendor":
            return redirect("adminIndex")
        return redirect("adminDashBoard")

    return render(request, "login.html")


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def admin_register(request):
    """
    Admin Registration Flow (API & form handler):
    - Checks for existing username and email
    - Salted SHA-256 password hashing
    - Role assignment (SuperAdmin for super@gmail.com, XLSXAdmin for xlsxsurplusadmin@gmail.com, Admin otherwise)
    """
    if request.method == "GET":
        return Response(
            {"message": "Submit POST with username, email, firstname, lastname, confirm_password to register."},
            status=status.HTTP_200_OK,
        )

    serializer = AdminRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    username = data["username"]
    email = data["email"].strip().lower()
    confirm_pass = data["resolved_password"]

    # Salted SHA-256 Password Hashing: <hash>:<salt>
    salt = uuid.uuid4().hex
    enc_pass = (
        hashlib.sha256(salt.encode() + confirm_pass.encode()).hexdigest()
        + ":"
        + salt
    )

    # Role Assignment:
    if email == "super@gmail.com":
        account_type = "SuperAdmin"
        web_is_active = "live"
    elif email == "xlsxsurplusadmin@gmail.com":
        account_type = "XLSXAdmin"
        web_is_active = "live"
    else:
        account_type = "Admin"
        web_is_active = "live"

    admin_user = AdminDetails.objects.create(
        username=username,
        email=email,
        pass_word=enc_pass,
        account_type=account_type,
        status=True,
        session_version=1,
        web_is_active=web_is_active,
    )

    return Response(
        {
            "success": True,
            "message": "Admin registration successful. Please proceed to login.",
            "redirect_url": "/admin/login/",
            "data": AdminDetailsSerializer(admin_user).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def admin_login(request):
    """
    Admin Login Flow:
    - Supports JSON API, HTML Form POST, and GET query string logins
    - Hash verification with salted SHA-256
    - Fallback auth to standard Django superusers
    - Session setup: adminid and session_version
    - Role-based routing: SuperAdmin, XLSX Admin, Admin, Vendor
    """
    req_data = dict(request.data or {})
    if request.method == "GET":
        # If no credentials passed in GET parameters, render the HTML login page
        if "user_email" not in request.GET and "email" not in request.GET and "username" not in request.GET:
            if request.headers.get("Accept", "").find("text/html") != -1:
                return admin_login_page(request)
            return Response(
                {"message": "Submit POST with user_email and user_pass to login."},
                status=status.HTTP_200_OK,
            )
        req_data = {
            "user_email": request.GET.get("user_email") or request.GET.get("email") or request.GET.get("username"),
            "user_pass": request.GET.get("user_pass") or request.GET.get("password"),
        }

    serializer = AdminLoginSerializer(data=req_data)
    if not serializer.is_valid():
        if request.headers.get("Accept", "").find("text/html") != -1 and request.content_type != "application/json":
            return admin_login_page(request)
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    identifier = serializer.validated_data["resolved_identifier"].strip()
    user_pass = serializer.validated_data["resolved_password"]

    admin_user = None
    admin_qs = AdminDetails.objects.filter(
        email__iexact=identifier
    ) | AdminDetails.objects.filter(username__iexact=identifier)

    if not admin_qs.exists() and identifier.upper().startswith("ADM-"):
        adm_id_clean = identifier[4:].strip()
        if adm_id_clean.isdigit():
            admin_qs = AdminDetails.objects.filter(id=int(adm_id_clean))

    if admin_qs.exists():
        candidate = admin_qs.first()
        if not candidate.status:
            return Response(
                {"success": False, "message": "Account is inactive. Contact SuperAdmin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            stored_hash, salt = candidate.pass_word.split(":")
            computed_hash = hashlib.sha256(
                salt.encode() + user_pass.encode()
            ).hexdigest()
            if computed_hash == stored_hash:
                admin_user = candidate
        except (ValueError, AttributeError):
            pass

    # Fallback Auth: Standard Django authenticate for superusers
    if not admin_user:
        django_user = authenticate(request, username=identifier, password=user_pass)
        if django_user and (django_user.is_superuser or django_user.is_staff):
            admin_user, _ = AdminDetails.objects.get_or_create(
                username=django_user.username,
                defaults={
                    "email": django_user.email or f"{django_user.username}@surplus.local",
                    "first_name": django_user.first_name,
                    "last_name": django_user.last_name,
                    "pass_word": AdminDetails.hash_password(user_pass),
                    "account_type": "SuperAdmin" if django_user.is_superuser else "Admin",
                    "status": True,
                    "session_version": 1,
                    "web_is_active": "live",
                },
            )

    if not admin_user:
        if request.headers.get("Accept", "").find("text/html") != -1 and request.content_type != "application/json":
            return render(request, "login.html", {"error": "Invalid email/username or password."})
        return Response(
            {"success": False, "message": "Invalid email/username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # Session Setup:
    request.session["adminid"] = admin_user.id
    request.session["session_version"] = admin_user.session_version

    # Role-Based Routing:
    if admin_user.email == "super@gmail.com" or admin_user.account_type == "SuperAdmin":
        redirect_route = "adminDashBoard"
        redirect_url = "/admin/dashboard/"
    elif (
        admin_user.email == "xlsxsurplusadmin@gmail.com"
        or admin_user.account_type == "XLSXAdmin"
    ):
        redirect_route = "xlsxDashBoard"
        redirect_url = "/admin/xlsx-dashboard/"
    elif admin_user.account_type == "Vendor":
        redirect_route = "adminIndex"
        redirect_url = "/admin/vendor-index/"
    else:
        redirect_route = "adminDashBoard"
        redirect_url = "/admin/dashboard/"

    if request.headers.get("Accept", "").find("text/html") != -1 and request.content_type != "application/json":
        return redirect(redirect_url)

    return Response(
        {
            "success": True,
            "message": "Login successful.",
            "redirect_route": redirect_route,
            "redirect_url": redirect_url,
            "admin": AdminDetailsSerializer(admin_user).data,
        },
        status=status.HTTP_200_OK,
    )


def admin_logout_view(request):
    """
    Flushes admin session and redirects to login screen.
    """
    request.session.flush()
    if request.headers.get("Accept", "").find("application/json") != -1:
        return Response(
            {"success": True, "message": "Logged out successfully.", "redirect_url": "/admin/login/"},
            status=status.HTTP_200_OK,
        )
    return redirect("admin_login_page")


@api_view(["POST"])
@permission_classes([AllowAny])
def super_admin_password_reset(request):
    """
    Generates 6-digit random OTP and dispatches via EmailService.
    """
    serializer = SuperAdminPasswordResetSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = serializer.validated_data["email"].strip().lower()
    try:
        admin_user = AdminDetails.objects.get(email=email)
    except AdminDetails.DoesNotExist:
        return Response(
            {
                "success": True,
                "message": "If an account exists with this email, a 6-digit reset OTP has been sent.",
            },
            status=status.HTTP_200_OK,
        )

    otp = f"{secrets.SystemRandom().randint(100000, 999999)}"
    AdminPasswordResetOTP.objects.filter(admin=admin_user, is_used=False).update(is_used=True)
    AdminPasswordResetOTP.objects.create(admin=admin_user, email=email, otp=otp)
    EmailService.send_admin_password_reset_otp(email=email, otp=otp)

    return Response(
        {
            "success": True,
            "message": "6-digit OTP dispatched to your registered email (valid for 10 minutes).",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def super_admin_verify_otp(request):
    """
    Validates OTP, updates password salt/hash, increments session_version,
    invalidates cache (admin_version_<id>), and flushes active session.
    """
    serializer = SuperAdminVerifyOTPSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email = serializer.validated_data["email"].strip().lower()
    otp_code = serializer.validated_data["otp"].strip()
    new_password = serializer.validated_data["new_password"]

    try:
        admin_user = AdminDetails.objects.get(email=email)
    except AdminDetails.DoesNotExist:
        return Response(
            {"success": False, "message": "Invalid request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp_record = (
        AdminPasswordResetOTP.objects.filter(
            admin=admin_user,
            otp=otp_code,
            is_used=False,
        )
        .order_by("-created_at")
        .first()
    )

    if not otp_record or not otp_record.is_valid():
        return Response(
            {"success": False, "message": "Invalid or expired OTP."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp_record.is_used = True
    otp_record.save()

    salt = uuid.uuid4().hex
    enc_pass = (
        hashlib.sha256(salt.encode() + new_password.encode()).hexdigest()
        + ":"
        + salt
    )
    admin_user.pass_word = enc_pass
    admin_user.session_version += 1
    admin_user.save()

    cache_key = f"admin_version_{admin_user.id}"
    cache.set(cache_key, admin_user.session_version, timeout=86400)

    if request.session.get("adminid") == admin_user.id:
        request.session.flush()

    return Response(
        {
            "success": True,
            "message": "Password reset successfully. Please login with your new password.",
            "redirect_url": "/admin/login/",
        },
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------
# Dashboard Views (HTML & JSON Dual Support)
# ---------------------------------------------------------

def adminDashBoard(request):
    """
    Main Admin Dashboard view for SuperAdmin and Standard Admins.
    Computes real dynamic stats from database models.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    is_super = admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com"
    staff_list = AdminDetails.objects.all().order_by("-created_at") if is_super else []

    # Real DB computations
    pending_prod_sales = Product.objects.filter(enquiry_status__iexact="pending").aggregate(s=Sum("current_price"))["s"] or 0
    pending_lot_sales = Lot.objects.filter(enquiry_status__iexact="pending").aggregate(s=Sum("total_price"))["s"] or 0
    total_sales_due = float(pending_prod_sales + pending_lot_sales)

    appr_prod_sales = Product.objects.filter(enquiry_status__iexact="approved").aggregate(s=Sum("current_price"))["s"] or 0
    appr_lot_sales = Lot.objects.filter(enquiry_status__iexact="approved").aggregate(s=Sum("total_price"))["s"] or 0
    total_sales_amount = float(appr_prod_sales + appr_lot_sales)

    active_products_stock = Product.objects.filter(is_active=True).aggregate(s=Sum("quantity"))["s"] or 0
    if not active_products_stock:
        active_products_stock = Product.objects.filter(is_active=True).count()

    companies_count = VendorDetails.objects.filter(account_entity_type="COMPANY").count()
    if companies_count == 0:
        companies_count = VendorDetails.objects.exclude(company_name="").count()

    context = {
        "admin": admin_user,
        "is_super_admin": is_super,
        "staff_list": staff_list,
        "stats": {
            "currency": "USD",
            "total_admins": AdminDetails.objects.count(),
            "active_admins": AdminDetails.objects.filter(status=True).count(),
            "total_sales_due": f"{total_sales_due:.2f}",
            "total_sales_amount": f"{total_sales_amount:.2f}",
            "active_products_qty": active_products_stock,
            "custom_landing_users": ContentPage.objects.filter(category="Custom").count(),
            "companies": companies_count,
            "purchase_invoices": Lot.objects.count(),
            "sales_invoices": Product.objects.count(),
            "products": Product.objects.count(),
            "categories": SubCategory.objects.count(),
            "total_page_views": PageViewLog.objects.count(),
            "registered_users": VendorDetails.objects.count(),
        },
    }


    if request.headers.get("Accept", "").find("application/json") != -1:
        return Response({
            "view": "SuperAdmin Dashboard" if is_super else "Admin Dashboard",
            "current_admin": AdminDetailsSerializer(admin_user).data,
            "is_super_admin": is_super,
            "stats": context["stats"],
            "staff_list": AdminDetailsSerializer(staff_list, many=True).data if is_super else [],
        })

    return render(request, "dashboard.html", context)




def xlsxDashBoard(request):
    """
    XLSX Admin Dashboard for Bulk Data Management.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    if admin_user.account_type not in ["XLSXAdmin", "SuperAdmin"]:
        return redirect("adminDashBoard")

    context = {
        "admin": admin_user,
        "features": ["Bulk Item Import (Excel/CSV)", "Bulk Export Reports", "Batch Inventory Sync"],
    }
    return render(request, "xlsx_dashboard.html", context)


def adminIndex(request):
    """
    Vendor Dashboard / Index View.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    context = {
        "admin": admin_user,
    }
    return render(request, "vendor_index.html", context)


@api_view(["GET"])
def get_current_admin(request):
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response(
            {"authenticated": False, "message": "No active admin session found."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return Response(
        {"authenticated": True, "admin": AdminDetailsSerializer(admin_user).data},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------
# Content Manager: Pages Views & REST APIs
# ---------------------------------------------------------

def _seed_default_pages_if_empty(admin_user):
    if ContentPage.objects.count() == 0:
        default_pages = [
            {
                "title": "About Us",
                "slug": "about-us",
                "category": "Information",
                "status": "published",
                "meta_title": "About Us - Surplus B2B Marketplace",
                "meta_description": "Learn more about Surplus B2B procurement hub and excess inventory liquidation platform.",
                "show_in_header": True,
                "show_in_footer": True,
                "sort_order": 1,
                "content": "<h2>About Surplus Market</h2><p>Surplus connects manufacturers, distributors, and wholesale buyers across global markets.</p>",
            },
            {
                "title": "Calculator",
                "slug": "calculator",
                "category": "Custom",
                "status": "published",
                "meta_title": "Surplus ROI & Cost Calculator",
                "meta_description": "Calculate estimated liquidation returns and margin savings for surplus inventory.",
                "show_in_header": False,
                "show_in_footer": False,
                "sort_order": 2,
                "content": "<h2>Surplus Savings & Liquidation Calculator</h2><p>Estimate your returns and savings on bulk lot transactions.</p>",
            },
            {
                "title": "Checklist Comparison",
                "slug": "checklist-comparison",
                "category": "Information",
                "status": "published",
                "meta_title": "Checklist Comparison - Surplus Platform",
                "meta_description": "Compare features, verification checks, and seller requirements across Surplus trading tiers.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 3,
                "content": "<h2>Platform Feature & Inspection Checklist</h2><p>Compare verification criteria and buyer guarantees.</p>",
            },
            {
                "title": "Compare",
                "slug": "compare",
                "category": "Information",
                "status": "published",
                "meta_title": "Compare B2B Wholesale Options",
                "meta_description": "Compare lots, pricing models, and bulk procurement options on Surplus.",
                "show_in_header": False,
                "show_in_footer": False,
                "sort_order": 4,
                "content": "<h2>Compare Options</h2><p>Side-by-side comparison tool for excess stock lots and categories.</p>",
            },
            {
                "title": "Contact Us",
                "slug": "contact",
                "category": "Help",
                "status": "published",
                "meta_title": "Contact Us - Surplus Support",
                "meta_description": "Get in touch with our B2B procurement team and customer support specialists.",
                "show_in_header": True,
                "show_in_footer": True,
                "sort_order": 5,
                "content": "<h2>Get In Touch</h2><p>Contact our support team for bulk lot enquiries, seller onboarding, and corporate accounts.</p>",
            },
            {
                "title": "Frequently Asked Questions",
                "slug": "faq",
                "category": "Help",
                "status": "published",
                "meta_title": "FAQ - Surplus B2B Help Center",
                "meta_description": "Find answers to frequently asked questions about bidding, logistics, seller verification, and payments.",
                "show_in_header": True,
                "show_in_footer": True,
                "sort_order": 6,
                "content": "<h2>Frequently Asked Questions</h2><p>Find quick answers to common questions about buying and selling on Surplus.</p>",
            },
            {
                "title": "India Region",
                "slug": "india",
                "category": "Custom",
                "status": "published",
                "meta_title": "Surplus India - Regional B2B Inventory Hub",
                "meta_description": "B2B surplus liquidation and wholesale procurement marketplace serving India.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 7,
                "content": "<h2>Surplus India Regional Hub</h2><p>Connecting bulk buyers and verified sellers across India.</p>",
            },
            {
                "title": "Inventory Calculator",
                "slug": "inventory-calculator",
                "category": "Custom",
                "status": "published",
                "meta_title": "Inventory Valuation Calculator",
                "meta_description": "Calculate residual value, holding cost, and liquidation pricing for stock clearance.",
                "show_in_header": False,
                "show_in_footer": False,
                "sort_order": 8,
                "content": "<h2>Inventory Valuation & Holding Cost Calculator</h2><p>Tools to analyze overstock and aging inventory value.</p>",
            },
            {
                "title": "Privacy Policy",
                "slug": "privacy",
                "category": "Policy",
                "status": "published",
                "meta_title": "Privacy Policy - Surplus",
                "meta_description": "Learn how Surplus collects, manages, and protects customer and transactional data.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 9,
                "content": "<h2>Privacy Policy</h2><p>We implement enterprise-grade encryption and data protection policies.</p>",
            },
            {
                "title": "Qatar Region",
                "slug": "qatar",
                "category": "Custom",
                "status": "published",
                "meta_title": "Surplus Qatar - B2B Clearance Marketplace",
                "meta_description": "Excess inventory and clearance lot distribution hub in Qatar.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 10,
                "content": "<h2>Surplus Qatar Regional Hub</h2><p>Regional procurement and liquidation network for Qatar.</p>",
            },
            {
                "title": "Returns & Refund Policy",
                "slug": "returns",
                "category": "Policy",
                "status": "published",
                "meta_title": "Returns & Refund Policy - Surplus",
                "meta_description": "Details regarding return eligibility, lot inspection windows, and dispute resolution.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 11,
                "content": "<h2>Returns & Dispute Policy</h2><p>Guidelines on inspection periods, claims, and return procedures for wholesale lots.</p>",
            },
            {
                "title": "Saudi Arabia Region",
                "slug": "saudi",
                "category": "Custom",
                "status": "published",
                "meta_title": "Surplus Saudi Arabia - KSA B2B Wholesale Hub",
                "meta_description": "Wholesale surplus liquidation and excess stock marketplace across Saudi Arabia.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 12,
                "content": "<h2>Surplus KSA Regional Hub</h2><p>Wholesale trading and inventory clearance across Saudi Arabia.</p>",
            },
            {
                "title": "Terms and Conditions",
                "slug": "terms",
                "category": "Policy",
                "status": "published",
                "meta_title": "Terms & Conditions - Surplus Marketplace",
                "meta_description": "Official terms and legal conditions for surplus trading and wholesale procurement.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 13,
                "content": "<h2>Terms & Conditions</h2><p>Official terms governing platform usage, transactions, and corporate compliance.</p>",
            },
            {
                "title": "Warranty & Guarantees",
                "slug": "warranty",
                "category": "Help",
                "status": "published",
                "meta_title": "Warranty & Guarantee Coverage - Surplus",
                "meta_description": "Information on factory warranty verification, stock condition grading, and buyer protection.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 14,
                "content": "<h2>Warranty & Verification Guarantees</h2><p>Every listed batch specifies condition grading, remaining shelf life, or warranty details.</p>",
            },
            {
                "title": "UAE Region",
                "slug": "uae",
                "category": "Custom",
                "status": "published",
                "meta_title": "Surplus UAE - Emirates B2B Inventory Hub",
                "meta_description": "Excess inventory and wholesale surplus marketplace in the United Arab Emirates.",
                "show_in_header": False,
                "show_in_footer": True,
                "sort_order": 15,
                "content": "<h2>Surplus UAE Regional Hub</h2><p>B2B inventory clearance and bulk lot trade hub for the UAE.</p>",
            },
            {
                "title": "Sell With Us",
                "slug": "sell",
                "category": "Information",
                "status": "published",
                "meta_title": "Sell Excess Inventory - Surplus Seller Onboarding",
                "meta_description": "Liquidate overstock, bulk lots, and clearance inventory quickly on Surplus.",
                "show_in_header": True,
                "show_in_footer": True,
                "sort_order": 16,
                "content": "<h2>Sell Your Surplus Stock</h2><p>Reach corporate buyers globally and liquidate excess inventory fast.</p>",
            },
        ]
        for p in default_pages:
            ContentPage.objects.create(created_by=admin_user, **p)


def content_pages_view(request):
    """
    Renders the Pages management view in the Content Manager section.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    _seed_default_pages_if_empty(admin_user)

    pages = ContentPage.objects.all().order_by("sort_order", "-updated_at")
    
    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "pages": pages,
        "stats": {
            "total_pages": pages.count(),
            "published_pages": pages.filter(status="published").count(),
            "draft_pages": pages.filter(status="draft").count(),
            "header_pages": pages.filter(show_in_header=True).count(),
        },
    }

    if request.headers.get("Accept", "").find("application/json") != -1:
        return Response({
            "pages": ContentPageSerializer(pages, many=True).data,
            "stats": context["stats"],
        })

    return render(request, "content_pages.html", context)


def content_page_editor_view(request, page_id=None):
    """
    Renders the dedicated Create / Edit Page screen.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    page = None
    components_json = "[]"
    if page_id:
        try:
            page = ContentPage.objects.get(id=page_id)
            import json
            components_json = json.dumps(page.components or [])
        except ContentPage.DoesNotExist:
            return redirect("content_pages_view")

    import json

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "page": page,
        "components_json": components_json,
        "available_components_json": "[]",
        "is_edit": page is not None,
    }
    return render(request, "content_page_form.html", context)


@api_view(["GET", "POST", "PUT", "DELETE"])
def content_pages_api(request, page_id=None):
    """
    REST API for Content Page CRUD operations.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response(
            {"success": False, "message": "Unauthorized admin session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    # 1. GET (List all or single page)
    if request.method == "GET":
        if page_id:
            try:
                page = ContentPage.objects.get(id=page_id)
                return Response({"success": True, "page": ContentPageSerializer(page).data})
            except ContentPage.DoesNotExist:
                return Response({"success": False, "message": "Page not found."}, status=status.HTTP_404_NOT_FOUND)
        
        category = request.GET.get("category")
        status_filter = request.GET.get("status")
        search = request.GET.get("search", "").strip()

        qs = ContentPage.objects.all()
        if category:
            qs = qs.filter(category=category)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(title__icontains=search) | qs.filter(slug__icontains=search)

        return Response({"success": True, "pages": ContentPageSerializer(qs, many=True).data})

    # 2. POST (Create new page)
    elif request.method == "POST":
        data = request.data.copy()
        title = data.get("title", "").strip()
        slug = data.get("slug", "").strip()

        if not title:
            return Response({"success": False, "message": "Page title is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not slug:
            import re
            slug = re.sub(r"[^\w\s-]", "", title.lower())
            slug = re.sub(r"[-\s]+", "-", slug).strip("-")
            data["slug"] = slug

        # Ensure slug uniqueness
        original_slug = data["slug"]
        counter = 1
        while ContentPage.objects.filter(slug=data["slug"]).exists():
            data["slug"] = f"{original_slug}-{counter}"
            counter += 1

        serializer = ContentPageSerializer(data=data)
        if serializer.is_valid():
            page = serializer.save(created_by=admin_user)
            return Response(
                {"success": True, "message": "Page created successfully.", "page": ContentPageSerializer(page).data},
                status=status.HTTP_201_CREATED,
            )
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    # 3. PUT (Update page)
    elif request.method == "PUT":
        if not page_id:
            return Response({"success": False, "message": "Page ID is required for update."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            page = ContentPage.objects.get(id=page_id)
        except ContentPage.DoesNotExist:
            return Response({"success": False, "message": "Page not found."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data.copy()
        serializer = ContentPageSerializer(page, data=data, partial=True)
        if serializer.is_valid():
            updated_page = serializer.save()
            return Response(
                {"success": True, "message": "Page updated successfully.", "page": ContentPageSerializer(updated_page).data},
                status=status.HTTP_200_OK,
            )
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    # 4. DELETE (Remove page)
    elif request.method == "DELETE":
        if not page_id:
            return Response({"success": False, "message": "Page ID is required for deletion."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            page = ContentPage.objects.get(id=page_id)
            page.delete()
            return Response({"success": True, "message": "Page deleted successfully."}, status=status.HTTP_200_OK)
        except ContentPage.DoesNotExist:
            return Response({"success": False, "message": "Page not found."}, status=status.HTTP_404_NOT_FOUND)


def _seed_sample_blogs_if_empty():
    from .models import BlogPost
    import json
    from pathlib import Path
    from django.conf import settings

    sample_dir = settings.BASE_DIR / "sample-blog"
    json_file = sample_dir / "blogs.json"
    if not json_file.exists():
        json_file = sample_dir / "all_blogs.json"

    if json_file.exists():
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                blogs_data = json.load(f)
                if isinstance(blogs_data, list) and len(blogs_data) > BlogPost.objects.count():
                    objs = []
                    for item in blogs_data:
                        title = item.get("title", "Untitled Blog")
                        raw_slug = item.get("slug") or f"blog-{item.get('id', 1)}"
                        slug = raw_slug.strip().lower()
                        blog_code = item.get("blog_code") or f"BLOG-{item.get('id', 1):06d}"
                        content = item.get("content") or ""
                        excerpt = item.get("excerpt") or ""
                        author = item.get("author") or "Admin"
                        category_name = item.get("category_name") or item.get("category") or "General"
                        img_raw = item.get("image") or item.get("featured_image_url") or ""
                        if img_raw:
                            if img_raw.startswith("http://") or img_raw.startswith("https://") or img_raw.startswith("/"):
                                img = img_raw
                            else:
                                img = f"/media/{img_raw}"
                        else:
                            img = ""

                        meta_t = item.get("meta_tags") or item.get("meta_title") or title
                        meta_d = item.get("meta_description") or ""
                        read_t = int(item.get("read_time") or 3)
                        total_r = int(item.get("total_reads") or 0)
                        is_pub = item.get("is_published", True)
                        is_active = not item.get("is_del", False)

                        objs.append(BlogPost(
                            title=title,
                            slug=slug,
                            blog_code=blog_code,
                            author=author,
                            category_name=category_name,
                            excerpt=excerpt,
                            content=content,
                            featured_image_url=img,
                            meta_title=meta_t[:255],
                            meta_description=meta_d,
                            read_time=read_t,
                            total_reads=total_r,
                            status="published" if is_pub else "draft",
                            is_active=is_active
                        ))
                    BlogPost.objects.bulk_create(objs, ignore_conflicts=True)
        except Exception as e:
            print(f"Error seeding blogs: {e}")


def content_blogs_view(request):
    """
    Renders the Blogs management list view in Content Manager section.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    _seed_sample_blogs_if_empty()

    from .models import BlogPost
    from django.db.models import Q, Sum
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all").lower()
    category_filter = request.GET.get("category", "all")
    page_num = request.GET.get("page", 1)

    blogs_qs = BlogPost.objects.all().order_by("-created_at")

    total_count = blogs_qs.count()
    published_count = blogs_qs.filter(status="published").count()
    draft_count = blogs_qs.filter(status="draft").count()
    total_reads_count = blogs_qs.aggregate(s=Sum("total_reads"))["s"] or 0

    if status_filter in ("published", "draft"):
        blogs_qs = blogs_qs.filter(status=status_filter)

    if category_filter != "all" and category_filter.strip():
        blogs_qs = blogs_qs.filter(category_name__iexact=category_filter.strip())

    if search_query:
        blogs_qs = blogs_qs.filter(
            Q(title__icontains=search_query) | Q(slug__icontains=search_query) | Q(blog_code__icontains=search_query) | Q(author__icontains=search_query)
        )

    categories_list = BlogPost.objects.exclude(category_name="").values_list("category_name", flat=True).distinct()

    paginator = Paginator(blogs_qs, 10)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "blogs": page_obj,
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "category_filter": category_filter,
        "categories_list": categories_list,
        "stats": {
            "total_blogs": total_count,
            "published_blogs": published_count,
            "draft_blogs": draft_count,
            "total_reads": total_reads_count,
        },
    }
    return render(request, "content_blogs.html", context)


def content_blog_editor_view(request, blog_id=None):
    """
    Renders the Create / Edit Blog Post form.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import BlogPost
    blog = None
    if blog_id:
        blog = BlogPost.objects.filter(id=blog_id).first()
        if not blog:
            return redirect("content_blogs_view")

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "blog": blog,
        "is_edit": blog is not None,
    }
    return render(request, "content_blog_form.html", context)


@api_view(["GET", "POST", "PUT", "DELETE"])
@permission_classes([AllowAny])
def content_blogs_api(request, blog_id=None):
    """
    REST API for Blog Post CRUD operations.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response(
            {"success": False, "message": "Unauthorized admin session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    from .models import BlogPost
    from django.utils.text import slugify

    if request.method == "DELETE":
        target_id = blog_id or request.data.get("id")
        if not target_id:
            return Response({"success": False, "message": "Blog ID is required."}, status=status.HTTP_400_BAD_REQUEST)
        blog = BlogPost.objects.filter(id=target_id).first()
        if not blog:
            return Response({"success": False, "message": "Blog post not found."}, status=status.HTTP_404_NOT_FOUND)
        blog.delete()
        return Response({"success": True, "message": "Blog post deleted successfully."})

    if request.method in ("POST", "PUT"):
        payload = request.data
        title = payload.get("title", "").strip()
        if not title:
            return Response({"success": False, "message": "Title is required."}, status=status.HTTP_400_BAD_REQUEST)

        slug = payload.get("slug", "").strip() or slugify(title)
        blog_code = payload.get("blog_code", "").strip() or f"BLOG-{secrets.SystemRandom().randint(100000, 999999)}"

        if blog_id:
            blog = BlogPost.objects.filter(id=blog_id).first()
        else:
            blog = BlogPost.objects.filter(slug=slug).first() or BlogPost()

        blog.title = title
        blog.slug = slug
        blog.blog_code = blog_code
        blog.author = payload.get("author", "Admin").strip()
        blog.category_name = payload.get("category_name", "General").strip()
        blog.excerpt = payload.get("excerpt", "").strip()
        blog.content = payload.get("content", "").strip()
        blog.featured_image_url = payload.get("featured_image_url", "").strip()
        blog.meta_title = payload.get("meta_title", "").strip()
        blog.meta_description = payload.get("meta_description", "").strip()
        blog.meta_keywords = payload.get("meta_keywords", "").strip()
        blog.read_time = int(payload.get("read_time", 3))
        blog.status = payload.get("status", "published").strip().lower()

        if "image" in request.FILES:
            blog.image = request.FILES["image"]

        blog.save()

        return Response({
            "success": True,
            "message": "Blog post saved successfully.",
            "blog_id": blog.id,
            "slug": blog.slug,
            "redirect_url": "/admin/content/blogs/"
        }, status=status.HTTP_200_OK)

    return Response({"success": True, "message": "Blog API online."})


# =============================================================
# ENQUIRIES: SELLER & LOT INQUIRIES MANAGEMENT VIEWS
# =============================================================

def seller_enquiries_view(request, status_filter=None):
    """
    Renders the Seller Product Enquiries dashboard table.
    Filters: all, pending, approved, declined.
    Includes pagination (50 products per page) for optimal performance.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Product
    from django.db.models import Q
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    current_status = status_filter or request.GET.get("status", "all").lower()
    search = request.GET.get("search", "").strip()
    date_filter = request.GET.get("date_filter", "all")
    page_num = request.GET.get("page", 1)

    qs = Product.objects.all().select_related("vendor", "category", "subcategory").order_by("-created_at")

    if date_filter == "today":
        qs = qs.filter(created_at__date=timezone.now().date())
    elif date_filter == "7days":
        qs = qs.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7))
    elif date_filter == "30days":
        qs = qs.filter(created_at__gte=timezone.now() - timezone.timedelta(days=30))
    
    # Status Counts
    total_count = Product.objects.count()
    pending_count = Product.objects.filter(enquiry_status__iexact="pending").count()
    approved_count = Product.objects.filter(enquiry_status__iexact="approved").count()
    declined_count = Product.objects.filter(enquiry_status__iexact="declined").count()

    if current_status in ("pending", "approved", "declined"):
        qs = qs.filter(enquiry_status__iexact=current_status)

    if search:
        qs = qs.filter(Q(product_id__icontains=search) | Q(model_no__icontains=search) | Q(product_name__icontains=search))

    paginator = Paginator(qs, 50)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "enquiries": page_obj,
        "page_obj": page_obj,
        "current_status": current_status,
        "search": search,
        "date_filter": date_filter,
        "counts": {
            "total": total_count,
            "pending": pending_count,
            "approved": approved_count,
            "declined": declined_count,
        }
    }
    return render(request, "seller_enquiries.html", context)


def lot_enquiries_view(request, status_filter=None):
    """
    Renders the Lot Batch Enquiries (.xlsx / .csv) dashboard table.
    Filters: all, pending, approved, declined.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Lot
    from django.db.models import Q
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    current_status = status_filter or request.GET.get("status", "all").lower()
    search = request.GET.get("search", "").strip()
    date_filter = request.GET.get("date_filter", "all")
    page_num = request.GET.get("page", 1)

    qs = Lot.objects.all().select_related("vendor", "category").order_by("-created_at")

    if date_filter == "today":
        qs = qs.filter(created_at__date=timezone.now().date())
    elif date_filter == "7days":
        qs = qs.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7))
    elif date_filter == "30days":
        qs = qs.filter(created_at__gte=timezone.now() - timezone.timedelta(days=30))
    
    # Status Counts
    total_count = Lot.objects.count()
    pending_count = Lot.objects.filter(enquiry_status="pending").count()
    approved_count = Lot.objects.filter(enquiry_status="approved").count()
    declined_count = Lot.objects.filter(enquiry_status="declined").count()

    if current_status in ("pending", "approved", "declined"):
        qs = qs.filter(enquiry_status=current_status)

    if search:
        qs = qs.filter(Q(lot_number__icontains=search) | Q(title__icontains=search))

    paginator = Paginator(qs, 50)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "enquiries": page_obj,
        "page_obj": page_obj,
        "current_status": current_status,
        "search": search,
        "date_filter": date_filter,
        "counts": {
            "total": total_count,
            "pending": pending_count,
            "approved": approved_count,
            "declined": declined_count,
        }
    }
    return render(request, "lot_enquiries.html", context)


@api_view(["POST", "PUT", "DELETE"])
def seller_enquiry_status_api(request, enquiry_id):
    """
    Admin API to update status (pending, approved, declined) or delete a SellerProductEnquiry.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response({"success": False, "message": "Unauthorized admin session."}, status=status.HTTP_401_UNAUTHORIZED)

    from .models import Product
    try:
        enquiry = Product.objects.get(id=enquiry_id)
    except Product.DoesNotExist:
        return Response({"success": False, "message": "Product enquiry not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        enquiry.delete()
        return Response({"success": True, "message": "Product deleted successfully."})

    has_explicit_active = ("active_status" in request.data or "is_active" in request.data)

    if "active_status" in request.data:
        act_val = str(request.data.get("active_status")).lower()
        if act_val in ("active", "true", "1"):
            enquiry.is_active = True
        elif act_val in ("inactive", "false", "0"):
            enquiry.is_active = False

    if "is_active" in request.data:
        enquiry.is_active = bool(request.data.get("is_active"))

    if "status" in request.data:
        new_status = request.data.get("status", "").upper()
        if new_status.lower() in ("pending", "approved", "declined"):
            enquiry.enquiry_status = new_status
            if not has_explicit_active:
                enquiry.is_active = (new_status.lower() == "approved")

    enquiry.save()

    return Response({
        "success": True,
        "message": f"Product status updated.",
        "product_id": enquiry.product_id or enquiry.sku,
        "status": enquiry.enquiry_status,
        "is_active": enquiry.is_active,
        "active_status": enquiry.active_status
    })


@api_view(["POST", "PUT"])
def seller_enquiry_edit_api(request, enquiry_id):
    """
    Admin API to update product enquiry / product details from detail views.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response({"success": False, "message": "Unauthorized admin session."}, status=status.HTTP_401_UNAUTHORIZED)

    from .models import Product, SubCategory
    try:
        product = Product.objects.get(id=enquiry_id)
    except Product.DoesNotExist:
        return Response({"success": False, "message": "Product enquiry not found."}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    
    title = data.get("product_name") or data.get("title")
    if title and str(title).strip():
        product.product_name = str(title).strip()

    if "liquidating_price" in data and data["liquidating_price"] not in (None, ""):
        try:
            product.liquidating_price = float(data["liquidating_price"])
        except (ValueError, TypeError):
            pass
    elif "price" in data and data["price"] not in (None, ""):
        try:
            product.liquidating_price = float(data["price"])
        except (ValueError, TypeError):
            pass

    if "previous_price" in data and data["previous_price"] not in (None, ""):
        try:
            product.previous_price = float(data["previous_price"])
        except (ValueError, TypeError):
            pass
    elif "original_price" in data and data["original_price"] not in (None, ""):
        try:
            product.previous_price = float(data["original_price"])
        except (ValueError, TypeError):
            pass
    elif "discount_price" in data and data["discount_price"] not in (None, ""):
        try:
            product.previous_price = float(data["discount_price"])
        except (ValueError, TypeError):
            pass

    if "stock_quantity" in data and data["stock_quantity"] not in (None, ""):
        try:
            product.stock_quantity = int(data["stock_quantity"])
        except (ValueError, TypeError):
            pass

    if "brand" in data:
        product.brand = str(data["brand"]).strip()

    if "main_category_id" in data and data["main_category_id"]:
        try:
            main_cat = MainCategory.objects.get(id=int(data["main_category_id"]))
            product.category = main_cat
        except (MainCategory.DoesNotExist, ValueError):
            pass

    if "subcategory_id" in data and data["subcategory_id"]:
        try:
            sub_cat = SubCategory.objects.get(id=int(data["subcategory_id"]))
            product.subcategory = sub_cat
            if sub_cat.main_category and not product.category:
                product.category = sub_cat.main_category
        except (SubCategory.DoesNotExist, ValueError):
            pass
    elif "category_name" in data and str(data["category_name"]).strip():
        cat_str = str(data["category_name"]).strip()
        sub_cat = SubCategory.objects.filter(name__iexact=cat_str).first()
        if sub_cat:
            product.subcategory = sub_cat
            if sub_cat.main_category and not product.category:
                product.category = sub_cat.main_category

    if "is_available_for_offers" in data:
        product.is_available_for_offers = bool(data["is_available_for_offers"])

    cond_val = data.get("condition") or data.get("product_condition") or data.get("stock_condition")
    if cond_val is not None:
        product.condition = str(cond_val).strip()

    if "inventory_location" in data:
        product.inventory_location = str(data["inventory_location"]).strip()
    if "manufacturing_country" in data:
        product.manufacturing_country = str(data["manufacturing_country"]).strip()
    if "manufacturing_year" in data and data["manufacturing_year"] not in (None, ""):
        try:
            product.manufacturing_year = int(data["manufacturing_year"])
        except (ValueError, TypeError):
            pass
    if "dimensions" in data:
        product.dimensions = str(data["dimensions"]).strip()
    if "warranty" in data:
        product.warranty = str(data["warranty"]).strip()
    if "reason_to_sell" in data:
        product.reason_to_sell = str(data["reason_to_sell"]).strip()
    if "description" in data:
        product.description = str(data["description"]).strip()
    if "enquiry_status" in data:
        status_val = str(data["enquiry_status"]).upper()
        if status_val in ("PENDING", "APPROVED", "DECLINED"):
            product.enquiry_status = status_val
    if "active_status" in data:
        act_val = str(data["active_status"]).lower()
        if act_val in ("active", "true", "1"):
            product.is_active = True
        elif act_val in ("inactive", "false", "0"):
            product.is_active = False
    elif "is_active" in data:
        product.is_active = bool(data["is_active"])
    if "warranty_attachment" in data:
        product.warranty_attachment = str(data["warranty_attachment"]).strip()
    if "third_party_certificate" in data:
        cert_val = data["third_party_certificate"]
        product.third_party_certificate = cert_val in (True, "true", "1", 1, "yes")
    if "third_party_documents" in data:
        product.third_party_documents = str(data["third_party_documents"]).strip()

    product.save()

    return Response({
        "success": True,
        "message": "Product details updated successfully.",
        "product_id": product.product_id or product.sku
    })


def seller_enquiry_detail_view(request, enquiry_id):
    """
    Admin HTML view to show the details of a single Product enquiry.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from django.db.models import Q
    from .models import Product
    lookup = Q(id=enquiry_id) | Q(product_id=str(enquiry_id))
    enquiry = Product.objects.select_related("vendor", "category", "subcategory__main_category").filter(lookup).first()
    if not enquiry:
        enquiry = Product.objects.select_related("vendor", "category", "subcategory__main_category").first()
    if not enquiry:
        return redirect("seller_enquiries")

    vendor = enquiry.vendor
    if not vendor and enquiry.vendor_id:
        from .models import VendorDetails
        vendor = VendorDetails.objects.filter(id=enquiry.vendor_id).first()
    if not vendor:
        from .models import VendorDetails, VendorOTP
        latest_otp = VendorOTP.objects.filter(is_used=True).order_by("-created_at").first()
        if latest_otp:
            vendor = latest_otp.vendor or VendorDetails.objects.filter(email__iexact=latest_otp.email).first()
        if not vendor:
            vendor = VendorDetails.objects.order_by("-id").first()
        if vendor:
            enquiry.vendor = vendor
            enquiry.save(update_fields=["vendor"])

    company_val = "N/A"
    full_name_val = "N/A"
    phone_val = "N/A"
    email_val = "N/A"
    business_location_val = "N/A"
    industry_val = "N/A"

    if vendor:
        full_name_val = vendor.full_name or vendor.username or "N/A"
        phone_val = vendor.mobile_number or "N/A"
        email_val = vendor.email or "N/A"
        company_val = vendor.company_name or vendor.username or "Individual Seller"
        business_location_val = vendor.business_location or "N/A"
        if vendor.category_interested:
            if isinstance(vendor.category_interested, list):
                industry_val = ", ".join(vendor.category_interested)
            else:
                industry_val = str(vendor.category_interested)
        elif vendor.business_type:
            industry_val = vendor.business_type
        elif vendor.user_type:
            industry_val = vendor.user_type

    user_data = {
        "vendor_id": vendor.vendor_id if vendor else "N/A",
        "user_id": vendor.vendor_id if vendor else "N/A",
        "raw_vendor_id": vendor.id if vendor else None,
        "raw_user_id": vendor.id if vendor else None,
        "full_name": full_name_val,
        "phone_no": phone_val,
        "email": email_val,
        "company": company_val,
        "business_location": business_location_val,
        "industry": industry_val,
    }

    product_data = {}
    processed_raw_keys = set()

    product_keys_schema = [
        ("product_name", "Product Name", True, ["product_name", "product name"]),
        ("product_category", "Product Category", True, ["select product category", "product category", "category"]),
        ("brand_name", "Brand Name", False, ["brand_name", "brand name", "brand"]),
        ("model_no", "Model No. / Part Number", False, ["model no. / part number", "model no", "part number", "model number"]),
        ("manufacturing_country", "Manufacturing Country", True, ["select manufacturing country", "manufacturing country", "country"]),
        ("inventory_location", "Inventory Location", False, ["inventory_location", "inventory location", "location", "warehouse location"]),
        ("manufacturing_year", "Manufacturing Year", False, ["manufacturing year", "year"]),
        ("dimensions", "Dimensions", False, ["dimensions", "dimension"]),
        ("expiry_date", "Expiry Date", False, ["expiry date", "expiry"]),
        ("excluded_countries", "Excluded Countries", False, ["excluded countries", "excluded countries (optional)"]),
        ("quantity", "Quantity", True, ["quantity", "qty"]),
        ("currency", "Currency", True, ["currency"]),
        ("liquidating_price", "Liquidating Price", True, ["liquidating price", "price"]),
        ("previous_price", "Previous Price", True, ["previous price", "original price"]),
        ("description", "Description", False, ["description", "desc"]),
        ("reason_to_sell", "Reason to Sell", True, ["reason to sell", "reason"]),
        ("warranty", "Warranty", False, ["warranty"]),
        ("certificate", "3rd Party Certificate", False, ["3rd party certificate", "certificate"]),
    ]

    required_product_keys = []
    
    # Extract known keys in specific order
    for dict_key, display_name, is_req, lookups in product_keys_schema:
        if is_req:
            required_product_keys.append(dict_key)
            
        found_val = None
        for r_key, r_val in enquiry.raw_data.items():
            if r_key in processed_raw_keys:
                continue
            k_norm_str = str(r_key).lower().replace("_", " ")
            if k_norm_str in lookups:
                found_val = r_val
                processed_raw_keys.add(r_key)
                break
                
        product_data[dict_key] = found_val

    # Fill product_data from model fields if available
    cat_str = ""
    if enquiry.subcategory:
        if enquiry.subcategory.main_category:
            cat_str = f"{enquiry.subcategory.main_category.name} » {enquiry.subcategory.name}"
        else:
            cat_str = enquiry.subcategory.name
    elif enquiry.category:
        cat_str = enquiry.category.name

    model_fields_dict = {
        "product_name": enquiry.product_name,
        "product_category": cat_str,
        "brand_name": enquiry.brand,
        "model_no": enquiry.model_no,
        "manufacturing_country": enquiry.manufacturing_country,
        "inventory_location": enquiry.inventory_location,
        "manufacturing_year": enquiry.manufacturing_year,
        "dimensions": enquiry.dimensions,
        "expiry_date": enquiry.expiry_date.strftime("%Y-%m-%d") if enquiry.expiry_date else None,
        "excluded_countries": (", ".join(enquiry.excluded_countries) if isinstance(enquiry.excluded_countries, list) and enquiry.excluded_countries else None),
        "quantity": enquiry.stock_quantity,
        "currency": enquiry.currency,
        "liquidating_price": str(enquiry.liquidating_price) if enquiry.liquidating_price else None,
        "current_price": str(enquiry.current_price) if enquiry.current_price else None,
        "previous_price": str(enquiry.previous_price) if enquiry.previous_price is not None else None,
        "condition": enquiry.condition,
        "is_available_for_offers": enquiry.is_available_for_offers,
        "date_approved": enquiry.date_approved.strftime("%Y-%m-%d %H:%M") if enquiry.date_approved else None,
        "description": enquiry.description,
        "reason_to_sell": enquiry.reason_to_sell,
        "warranty": enquiry.warranty,
        "warranty_document": enquiry.warranty_attachment,
        "certificate": enquiry.third_party_documents if enquiry.third_party_documents else ("Yes" if enquiry.third_party_certificate else None),
        "offer": str(enquiry.offer) if enquiry.offer else None,
    }

    for k, v in model_fields_dict.items():
        if v is not None and v != "":
            product_data[k] = v

    # Append any remaining unknown keys (excluding image, certificate, documents, and user fields)
    excluded_raw_keys = {
        "featured_image_url", "third_party_certificate", "documents",
        "image", "product_image", "certificate", "3rd_party_certificate",
        "seller_email", "email", "full_name", "name", "phone", "phone_no",
        "company", "company_name", "business_location", "location", "industry"
    }
    for r_key, r_val in enquiry.raw_data.items():
        k_norm = str(r_key).lower().replace(" ", "_").replace("-", "_")
        if k_norm not in excluded_raw_keys and r_key not in processed_raw_keys and r_key not in product_data:
            product_data[r_key] = r_val

    from .models import MainCategory
    categories = MainCategory.objects.prefetch_related("subcategories").all()

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "enquiry": enquiry,
        "user_data": user_data,
        "product_data": product_data,
        "required_product_keys": required_product_keys,
        "categories": categories,
    }
    return render(request, "seller_enquiry_detail.html", context)


@api_view(["POST", "PUT"])
def lot_enquiry_edit_api(request, enquiry_id):
    """
    Admin API to update Lot batch details from detail view.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response({"success": False, "message": "Unauthorized admin session."}, status=status.HTTP_401_UNAUTHORIZED)

    from .models import Lot, SubCategory
    try:
        lot = Lot.objects.get(id=enquiry_id)
    except Lot.DoesNotExist:
        return Response({"success": False, "message": "Lot not found."}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    if "title" in data and str(data["title"]).strip():
        lot.title = str(data["title"]).strip()
    if "total_price" in data and data["total_price"] not in (None, ""):
        try:
            lot.total_price = float(data["total_price"])
        except (ValueError, TypeError):
            pass
    if "currency" in data:
        lot.currency = str(data["currency"]).strip()
    if "inventory_location" in data:
        lot.inventory_location = str(data["inventory_location"]).strip()
    if "subcategory_id" in data and data["subcategory_id"]:
        try:
            sub_cat = SubCategory.objects.get(id=int(data["subcategory_id"]))
            lot.category = sub_cat
            lot.category_name = sub_cat.name
        except (SubCategory.DoesNotExist, ValueError):
            pass
    elif "category_name" in data and str(data["category_name"]).strip():
        lot.category_name = str(data["category_name"]).strip()

    if "reason_to_sell" in data:
        lot.reason_to_sell = str(data["reason_to_sell"]).strip()
    if "description" in data:
        lot.description = str(data["description"]).strip()
    if "enquiry_status" in data:
        status_val = str(data["enquiry_status"]).lower()
        if status_val in ("pending", "approved", "declined"):
            lot.enquiry_status = status_val
    if "active_status" in data:
        act_val = str(data["active_status"]).lower()
        if act_val in ("active", "true", "1"):
            lot.active_status = "active"
            lot.is_active = True
        elif act_val in ("inactive", "false", "0"):
            lot.active_status = "inactive"
            lot.is_active = False
    elif "is_active" in data:
        lot.is_active = bool(data["is_active"])
        lot.active_status = "active" if lot.is_active else "inactive"

    if not isinstance(lot.raw_data, dict):
        lot.raw_data = {}

    if "title" in data:
        lot.raw_data["title"] = lot.title
    if "total_price" in data:
        lot.raw_data["liquidation_price"] = lot.total_price
    if "reason_to_sell" in data:
        lot.raw_data["notes"] = lot.reason_to_sell
    if "description" in data:
        lot.raw_data["description"] = lot.description

    lot.save()

    return Response({
        "success": True,
        "message": "Lot batch details updated successfully.",
        "batch_id": lot.lot_number
    })


@api_view(["POST", "PUT", "DELETE"])
def lot_enquiry_status_api(request, enquiry_id):
    """
    Admin API to update status (pending, approved, declined) or active status (active, inactive) or delete a LotBatchEnquiry.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response({"success": False, "message": "Unauthorized admin session."}, status=status.HTTP_401_UNAUTHORIZED)

    from .models import Lot
    try:
        enquiry = Lot.objects.get(id=enquiry_id)
    except Lot.DoesNotExist:
        return Response({"success": False, "message": "Lot not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        enquiry.delete()
        return Response({"success": True, "message": "Lot deleted successfully."})

    has_explicit_active = ("active_status" in request.data or "is_active" in request.data)

    if "active_status" in request.data:
        act_val = str(request.data.get("active_status")).lower()
        if act_val in ("active", "true", "1"):
            enquiry.active_status = "active"
            enquiry.is_active = True
        elif act_val in ("inactive", "false", "0"):
            enquiry.active_status = "inactive"
            enquiry.is_active = False

    if "is_active" in request.data:
        enquiry.is_active = bool(request.data.get("is_active"))
        enquiry.active_status = "active" if enquiry.is_active else "inactive"

    if "status" in request.data:
        new_status = str(request.data.get("status")).lower()
        if new_status in ("pending", "approved", "declined"):
            enquiry.enquiry_status = new_status
            if not has_explicit_active:
                enquiry.active_status = "active" if new_status == "approved" else "inactive"
                enquiry.is_active = (new_status == "approved")

    enquiry.save()

    return Response({
        "success": True,
        "message": f"Lot status updated to {new_status}.",
        "batch_id": enquiry.lot_number,
        "status": enquiry.enquiry_status
    })


def lot_enquiry_detail_view(request, enquiry_id):
    """
    Admin HTML view to show the details of a single Lot, including its extracted products.
    """
    from django.shortcuts import get_object_or_404
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Lot
    enquiry = get_object_or_404(Lot, id=enquiry_id)

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "enquiry": enquiry,
    }
    
    user_data = {
        "full_name": None,
        "phone_no": None,
        "email": None,
        "company": None,
        "business_location": None,
        "industry": None
    }
    batch_data = {
        "category_breakdown": None,
        "shipping_size": None,
        "stock_condition": None,
        "inventory_age": None,
        "distinct_skus": None,
        "total_units": None,
        "key_brands": None,
        "notes": None,
        "msrp": None,
        "currency": "AED",
        "liquidation_price": None,
        "open_to_offer": None,
        "media": None
    }

    processed_raw_keys = set()
    for k, v in enquiry.raw_data.items():
        k_norm = str(k).lower().replace(" ", "_").replace("-", "_")
        
        # User Data
        if k_norm in ("full_name", "name", "contact_person"):
            user_data["full_name"] = v
            processed_raw_keys.add(k)
        elif k_norm in ("phone_no", "phone", "phone_number", "contact_number"):
            user_data["phone_no"] = v
            processed_raw_keys.add(k)
        elif k_norm in ("email", "e_mail", "email_address"):
            user_data["email"] = v
            processed_raw_keys.add(k)
        elif k_norm in ("company", "company_name"):
            user_data["company"] = v
            processed_raw_keys.add(k)
        elif k_norm in ("business_location", "location", "inventory_location"):
            user_data["business_location"] = v
            processed_raw_keys.add(k)
        elif k_norm == "industry":
            user_data["industry"] = v
            processed_raw_keys.add(k)
            
        # Batch Data
        elif "category" in k_norm or "breakdown" in k_norm:
            batch_data["category_breakdown"] = v
            processed_raw_keys.add(k)
        elif "shipping" in k_norm or "size" in k_norm:
            batch_data["shipping_size"] = v
            processed_raw_keys.add(k)
        elif "condition" in k_norm:
            batch_data["stock_condition"] = v
            processed_raw_keys.add(k)
        elif "age" in k_norm:
            batch_data["inventory_age"] = v
            processed_raw_keys.add(k)
        elif "sku" in k_norm or "distinct" in k_norm:
            batch_data["distinct_skus"] = v
            processed_raw_keys.add(k)
        elif "unit" in k_norm or "quantity" in k_norm or "total" in k_norm:
            batch_data["total_units"] = v
            processed_raw_keys.add(k)
        elif "brand" in k_norm:
            batch_data["key_brands"] = v
            processed_raw_keys.add(k)
        elif "note" in k_norm or "packaging" in k_norm:
            batch_data["notes"] = v
            processed_raw_keys.add(k)
        elif k_norm in ("msrp", "retail_price"):
            batch_data["msrp"] = v
            processed_raw_keys.add(k)
        elif k_norm == "currency":
            batch_data["currency"] = v
            processed_raw_keys.add(k)
        elif "liquidation" in k_norm or "target_price" in k_norm:
            batch_data["liquidation_price"] = v
            processed_raw_keys.add(k)
        elif "offer" in k_norm or "open_to" in k_norm:
            batch_data["open_to_offer"] = v
            processed_raw_keys.add(k)
        elif k_norm in ("media", "image", "images", "video", "videos", "product_image", "warehouse_image"):
            batch_data["media"] = v
            processed_raw_keys.add(k)
            
    vendor = enquiry.vendor
    if not vendor:
        raw_vid = enquiry.raw_data.get("vendor_id") or enquiry.raw_data.get("user_id")
        if raw_vid:
            v_clean = str(raw_vid).strip()
            if v_clean.upper().startswith("USR-"):
                v_clean = v_clean[4:].strip()
            if v_clean.isdigit():
                vendor = VendorDetails.objects.filter(id=int(v_clean)).first()
            if not vendor:
                vendor = VendorDetails.objects.filter(email__iexact=str(raw_vid).strip()).first()

    if not vendor:
        from .models import VendorOTP
        latest_otp = VendorOTP.objects.filter(is_used=True).order_by("-created_at").first()
        if latest_otp:
            vendor = latest_otp.vendor or VendorDetails.objects.filter(email__iexact=latest_otp.email).first()
        if not vendor:
            vendor = VendorDetails.objects.order_by("-id").first()
        if vendor and hasattr(enquiry, 'vendor'):
            enquiry.vendor = vendor
            enquiry.save(update_fields=["vendor"])

    if vendor:
        user_data["vendor_id"] = vendor.vendor_id
        user_data["raw_vendor_id"] = vendor.id
        user_data["user_id"] = vendor.vendor_id
        user_data["raw_user_id"] = vendor.id
        user_data["full_name"] = vendor.full_name or vendor.username or "N/A"
        user_data["phone_no"] = vendor.mobile_number or "N/A"
        user_data["email"] = vendor.email or "N/A"
        user_data["company"] = vendor.company_name or vendor.username or "Individual Seller"
        user_data["business_location"] = vendor.business_location or "N/A"
        if vendor.category_interested:
            user_data["industry"] = ", ".join(vendor.category_interested) if isinstance(vendor.category_interested, list) else str(vendor.category_interested)
        elif vendor.business_type:
            user_data["industry"] = vendor.business_type
    else:
        user_data["vendor_id"] = "N/A"
        user_data["user_id"] = "N/A"
        user_data["business_location"] = "N/A"
        user_data["industry"] = "N/A"

    context["user_data"] = user_data
    context["batch_data"] = batch_data
    
    from .models import LotProduct
    db_products = list(LotProduct.objects.filter(lot=enquiry).order_by("id"))
    is_saved_to_db = len(db_products) > 0 or bool(enquiry.raw_data.get("is_saved_to_db"))

    products_list = []
    if db_products:
        for p in db_products:
            p_dict = dict(p.raw_data or {})
            p_dict["product_id"] = p.product_id
            p_dict["product_name"] = p.product_name or p_dict.get("product_name") or p_dict.get("title") or "-"
            p_dict["quantity"] = p.quantity or p_dict.get("available_quantity") or p_dict.get("quantity") or 0
            p_dict["condition"] = p.condition or p_dict.get("product_condition") or "Surplus"
            products_list.append(p_dict)
    elif enquiry.raw_data.get("is_saved_to_db") and enquiry.raw_data.get("products"):
        products_list = enquiry.raw_data.get("products", [])
    elif enquiry.file:
        try:
            from lots.importer import parse_spreadsheet
            enquiry.file.open('rb')
            parse_res = parse_spreadsheet(enquiry.file)
            parsed_items = parse_res.get("all_items", [])
            if parsed_items:
                products_list = parsed_items
        except Exception as e:
            print(f"Error parsing attached excel file: {e}")

    if not isinstance(products_list, list):
        products_list = []

    context["products"] = products_list
    context["is_saved_to_db"] = is_saved_to_db
    context["extra_data"] = {k: v for k, v in enquiry.raw_data.items() if k not in processed_raw_keys and k not in ("products", "manifest_items")}

    return render(request, "lot_enquiry_detail.html", context)


@api_view(["POST"])
def save_lot_products_api(request, enquiry_id):
    """
    Saves extracted Excel products into the database (LotProduct records & raw_data).
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response(
            {"success": False, "message": "Unauthorized admin session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    from .models import Lot, LotProduct
    try:
        enquiry = Lot.objects.get(id=enquiry_id)
    except Lot.DoesNotExist:
        return Response(
            {"success": False, "message": "Lot enquiry not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    products_data = request.data.get("products", [])

    # If products data not provided in body, parse attached file on server
    if not products_data and enquiry.file:
        try:
            from lots.importer import parse_spreadsheet
            enquiry.file.open('rb')
            parse_res = parse_spreadsheet(enquiry.file)
            products_data = parse_res.get("all_items", [])
        except Exception as e:
            return Response(
                {"success": False, "message": f"Error parsing Excel file: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if not products_data and enquiry.raw_data.get("products"):
        products_data = enquiry.raw_data.get("products")

    if not products_data:
        return Response(
            {"success": False, "message": "No product data found to save to database."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Save to database
    LotProduct.objects.filter(lot=enquiry).delete()
    saved_count = 0

    for item in products_data:
        p_name = item.get("product_name") or item.get("title") or item.get("name") or f"Product #{saved_count + 1}"
        p_qty = item.get("available_quantity") or item.get("quantity") or 1
        try:
            p_qty = int(p_qty)
        except (ValueError, TypeError):
            p_qty = 1

        p_cond = item.get("product_condition") or item.get("condition") or "New / Surplus"

        LotProduct.objects.create(
            lot=enquiry,
            product_name=str(p_name)[:255],
            quantity=p_qty,
            condition=str(p_cond)[:255],
            raw_data=item,
        )
        saved_count += 1

    if not isinstance(enquiry.raw_data, dict):
        enquiry.raw_data = {}

    enquiry.raw_data["products"] = products_data
    enquiry.raw_data["is_saved_to_db"] = True
    enquiry.save()

    return Response({
        "success": True,
        "message": f"Successfully saved {saved_count} products to database.",
        "saved_count": saved_count
    })


def manage_users_view(request):
    """
    Dedicated view for listing registered users (VendorDetails).
    Does NOT include RFQ or product metrics.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from AdminApp.models import VendorDetails
    vendor_queryset = VendorDetails.objects.all().order_by("-created_at")

    search_query = request.GET.get("q", "").strip()
    type_filter = request.GET.get("type", "").strip()
    status_filter = request.GET.get("status", "").strip()

    users_list = []
    registered_count = 0
    sellers_count = 0
    buyers_count = 0
    both_count = 0
    active_count = 0
    inactive_count = 0

    for vendor in vendor_queryset:
        registered_count += 1

        u_type = "Buyer"
        if vendor.user_type == "SELLER":
            u_type = "Seller"
            sellers_count += 1
        elif vendor.user_type == "BOTH":
            u_type = "Both"
            both_count += 1
        else:
            buyers_count += 1

        is_active = vendor.status
        if is_active:
            active_count += 1
        else:
            inactive_count += 1

        name = vendor.username
        email = vendor.email or ""
        company = vendor.company_name or "-"
        phone = vendor.mobile_number or "-"
        country = vendor.business_location or "-"
        entity_type = vendor.get_account_entity_type_display() if hasattr(vendor, "get_account_entity_type_display") else vendor.account_entity_type

        # Filter logic
        if search_query:
            sq = search_query.lower()
            if not (sq in name.lower() or sq in email.lower() or sq in company.lower() or sq in phone.lower() or sq in vendor.user_id.lower()):
                continue

        if type_filter and type_filter.lower() != "all":
            if type_filter.lower() != u_type.lower():
                continue

        if status_filter and status_filter.lower() != "any":
            if status_filter.lower() == "active" and not is_active:
                continue
            if status_filter.lower() == "inactive" and is_active:
                continue

        users_list.append({
            "id": vendor.id,
            "vendor_id": vendor.vendor_id,
            "user_id": vendor.vendor_id,
            "formatted_id": vendor.vendor_id,
            "username": vendor.username,
            "name": name,
            "email": email,
            "type": u_type,
            "company": company,
            "country": country,
            "phone": phone,
            "entity_type": entity_type,
            "business_type": vendor.business_type or "-",
            "business_address": vendor.business_address or "-",
            "tax_registration_number": vendor.tax_registration_number or "-",
            "category_interested": vendor.category_interested or "-",
            "status": "Active" if is_active else "Inactive",
            "joined": vendor.created_at,
        })

    context = {
        "admin": admin_user,
        "users": users_list,
        "search_query": search_query,
        "type_filter": type_filter,
        "status_filter": status_filter,
        "stats": {
            "total_users": registered_count,
            "sellers_only": sellers_count,
            "buyers_only": buyers_count,
            "both": both_count,
            "active": active_count,
            "inactive": inactive_count,
        }
    }
    return render(request, "users_list.html", context)


@api_view(["POST", "DELETE"])
def delete_user_api(request, user_id):
    """
    Deletes a registered user (VendorDetails) by user_id.
    Requires authenticated admin session.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return Response(
            {"success": False, "message": "Unauthorized admin session."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    from AdminApp.models import VendorDetails
    try:
        vendor = VendorDetails.objects.get(id=user_id)
        user_name = vendor.username
        vendor.delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type == "application/json" or request.method == "DELETE":
            return Response(
                {"success": True, "message": f"User '{user_name}' deleted successfully."},
                status=status.HTTP_200_OK,
            )
        return redirect("manage_users")
    except VendorDetails.DoesNotExist:
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type == "application/json" or request.method == "DELETE":
            return Response(
                {"success": False, "message": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return redirect("manage_users")
    except Exception as e:
        if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.content_type == "application/json" or request.method == "DELETE":
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return redirect("manage_users")


def contact_enquiries_view(request):
    """
    View for the Contact Us (General Enquiries) page in Admin Portal.
    Fetches real submissions from ContactUsEnquiry database table.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    # Handle POST Actions (Delete / Block / Bulk)
    if request.method == "POST":
        action = request.POST.get("action")
        selected_ids = request.POST.getlist("selected_ids") or request.POST.getlist("contact_id")
        
        if action == "delete" and selected_ids:
            ContactUsEnquiry.objects.filter(id__in=selected_ids).delete()
        elif action == "block" and selected_ids:
            ContactUsEnquiry.objects.filter(id__in=selected_ids).update(is_blocked=True, status="BLOCKED")
        elif action == "unblock" and selected_ids:
            ContactUsEnquiry.objects.filter(id__in=selected_ids).update(is_blocked=False, status="PENDING")

    search_query = request.GET.get("search", "").strip() or request.GET.get("q", "").strip()
    
    db_contacts = ContactUsEnquiry.objects.all().order_by("-created_at")
    
    if search_query:
        db_contacts = db_contacts.filter(
            Q(full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(enquiry_type__icontains=search_query) |
            Q(message__icontains=search_query)
        )

    contacts_list = []
    for item in db_contacts:
        contacts_list.append({
            "id": item.id,
            "name": item.full_name,
            "full_name": item.full_name,
            "phone": item.phone,
            "email": item.email,
            "date": timezone.localtime(item.created_at).strftime("%b. %d, %Y") if item.created_at else "",
            "time": timezone.localtime(item.created_at).strftime("%I:%M %p").lower() if item.created_at else "",
            "type": item.enquiry_type or "General Inquiry",
            "enquiry_type": item.enquiry_type or "General Inquiry",
            "message": item.message,
            "status": item.status,
            "is_blocked": item.is_blocked,
            "created_at": item.created_at,
        })

    context = {
        "admin": admin_user,
        "contacts": contacts_list,
        "search_query": search_query,
        "page_title": "Contact Us",
        "page_subtitle": "All Contact Enquiries"
    }
    return render(request, "contact_us.html", context)


def page_views_analytics_view(request):
    """
    Dedicated view for Page Visits, Traffic Analytics, and Dwell-Time / Stuck User Intelligence in the Admin Portal.
    Displays page-by-page view counts, average dwell time, where users spend the most time,
    stuck-user analysis, KPI cards, and detailed view logs.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from django.db.models import Avg, Count, Max, Sum, Q

    entity_type_filter = request.GET.get("entity_type", "").strip().lower()
    search_query = request.GET.get("search", "").strip() or request.GET.get("q", "").strip()
    active_tab = request.GET.get("tab", "pages").strip().lower()

    logs = PageViewLog.objects.all().order_by("-created_at")

    if entity_type_filter:
        logs = logs.filter(entity_type=entity_type_filter)

    if search_query:
        logs = logs.filter(
            Q(path__icontains=search_query) |
            Q(entity_slug__icontains=search_query) |
            Q(ip_address__icontains=search_query) |
            Q(user_agent__icontains=search_query) |
            Q(referrer__icontains=search_query)
        )

    # Core Counts
    total_views = PageViewLog.objects.count()
    today_views = PageViewLog.objects.filter(created_at__date=timezone.now().date()).count()
    unique_visitors = PageViewLog.objects.exclude(ip_address__isnull=True).values("ip_address").distinct().count()
    total_stuck_sessions = PageViewLog.objects.filter(is_stuck=True).count()

    # Average Platform Dwell Time
    avg_dwell_res = PageViewLog.objects.filter(duration_seconds__gt=0).aggregate(avg_sec=Avg("duration_seconds"))
    platform_avg_seconds = round(avg_dwell_res.get("avg_sec") or 0)

    # 1. Page-by-Page Aggregation (Number of views for each page + dwell time)
    page_stats_qs = (
        PageViewLog.objects.exclude(path="")
        .values("path", "entity_type")
        .annotate(
            view_count=Count("id"),
            unique_count=Count("ip_address", distinct=True),
            avg_duration=Avg("duration_seconds"),
            max_duration=Max("duration_seconds"),
            stuck_count=Count("id", filter=Q(is_stuck=True))
        )
    )

    if search_query:
        page_stats_qs = page_stats_qs.filter(path__icontains=search_query)
    if entity_type_filter:
        page_stats_qs = page_stats_qs.filter(entity_type=entity_type_filter)

    def _fmt(sec):
        if not sec or sec <= 0:
            return "< 5s"
        if sec < 60:
            return f"{sec}s"
        m = sec // 60
        s = sec % 60
        return f"{m}m {s}s" if s > 0 else f"{m}m"

    page_stats_list = []
    for item in page_stats_qs.order_by("-view_count")[:150]:
        avg_sec = round(item.get("avg_duration") or 0)
        max_sec = item.get("max_duration") or 0
        v_count = item.get("view_count") or 1
        s_count = item.get("stuck_count") or 0
        stuck_pct = round((s_count / v_count) * 100, 1)

        page_stats_list.append({
            "path": item["path"],
            "entity_type": item["entity_type"],
            "view_count": v_count,
            "unique_count": item.get("unique_count") or 0,
            "avg_seconds": avg_sec,
            "avg_duration_fmt": _fmt(avg_sec),
            "max_duration_fmt": _fmt(max_sec),
            "stuck_count": s_count,
            "stuck_pct": stuck_pct,
            "is_high_dwell": avg_sec >= 120,
        })

    # 2. "Where Users Stayed More" Leaderboard (Ranked by highest dwell time)
    most_stayed_pages = sorted(
        [p for p in page_stats_list if p["avg_seconds"] > 0],
        key=lambda x: x["avg_seconds"],
        reverse=True
    )[:8]

    # 3. Stuck Pages Analysis (Pages with highest stuck rate / friction)
    stuck_pages_analysis = sorted(
        [p for p in page_stats_list if p["stuck_count"] > 0],
        key=lambda x: (x["stuck_count"], x["stuck_pct"]),
        reverse=True
    )[:8]

    # Top entity breakdown
    top_blogs = BlogPost.objects.all().order_by("-views_count")[:5]
    top_products = Product.objects.all().order_by("-views_count")[:5]
    top_lots = Lot.objects.all().order_by("-views_count")[:5]

    # Format logs for live table with human readable duration
    formatted_logs = []
    for log in logs[:100]:
        sec = log.duration_seconds or 0
        formatted_logs.append({
            "log": log,
            "duration_fmt": _fmt(sec),
            "is_stuck": log.is_stuck or (sec >= 180)
        })

    context = {
        "admin": admin_user,
        "logs": logs[:100],
        "formatted_logs": formatted_logs,
        "total_views": total_views,
        "today_views": today_views,
        "unique_visitors": unique_visitors,
        "total_stuck_sessions": total_stuck_sessions,
        "platform_avg_duration": _fmt(platform_avg_seconds),
        "page_stats_list": page_stats_list,
        "most_stayed_pages": most_stayed_pages,
        "stuck_pages_analysis": stuck_pages_analysis,
        "top_blogs": top_blogs,
        "top_products": top_products,
        "top_lots": top_lots,
        "search_query": search_query,
        "selected_entity_type": entity_type_filter,
        "active_tab": active_tab,
        "page_title": "Page Visits & User Dwell-Time Analytics",
        "page_subtitle": "Real-time Traffic Tracking, Per-Page Views, Dwell Time & Stuck User Friction Analysis"
    }
    return render(request, "page_views_analytics.html", context)



def whatsapp_enquiries_view(request):
    """
    View for the WhatsApp Enquiries page using real database records.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import ContactUsEnquiry
    from django.db.models import Q

    search_query = request.GET.get("search", "").strip() or request.GET.get("q", "").strip()

    qs = ContactUsEnquiry.objects.filter(
        Q(enquiry_type__icontains="whatsapp") | Q(message__icontains="whatsapp")
    ).order_by("-created_at")

    if search_query:
        qs = qs.filter(
            Q(full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(message__icontains=search_query)
        )

    contacts = []
    for item in qs:
        contacts.append({
            "id": item.id,
            "name": item.full_name,
            "full_name": item.full_name,
            "phone": item.phone,
            "email": item.email,
            "date": item.created_at.strftime("%b. %d, %Y"),
            "time": item.created_at.strftime("%I:%M %p").lower(),
            "type": item.enquiry_type or "WhatsApp",
            "enquiry_type": item.enquiry_type or "WhatsApp",
            "message": item.message,
            "status": item.status,
            "is_blocked": item.is_blocked,
            "created_at": item.created_at,
        })

    context = {
        "admin": admin_user,
        "contacts": contacts,
        "search_query": search_query,
        "page_title": "WhatsApp Enquiries",
        "page_subtitle": "All WhatsApp Enquiries"
    }
    return render(request, "contact_us.html", context)


def partnership_enquiries_view(request):
    """
    View for the Partnership Enquiries page with AJAX status updates & bulk actions.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    # Handle POST Actions (Status Update / Delete / Bulk)
    if request.method == "POST":
        action = request.POST.get("action")
        enquiry_id = request.POST.get("enquiry_id")
        new_status = request.POST.get("status")
        selected_ids = request.POST.getlist("selected_ids") or ( [enquiry_id] if enquiry_id else [] )

        if action == "update_status" and enquiry_id and new_status:
            PartnershipEnquiry.objects.filter(id=enquiry_id).update(status=new_status.upper())
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": f"Status updated to {new_status.upper()}"})
            return redirect("partnership_enquiries")

        elif action == "delete" and selected_ids:
            PartnershipEnquiry.objects.filter(id__in=selected_ids).delete()
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": "Selected enquiry deleted successfully"})
            return redirect("partnership_enquiries")

    db_enquiries = PartnershipEnquiry.objects.all().order_by("-created_at")
    
    counts = {
        "total": db_enquiries.count(),
        "pending": db_enquiries.filter(status="PENDING").count(),
        "contacted": db_enquiries.filter(status="CONTACTED").count(),
        "referral": db_enquiries.filter(
            Q(partnership_interest__icontains="referral") | Q(business_location__icontains="gcc") | Q(business_location__icontains="uae")
        ).count() or db_enquiries.count()
    }

    enquiries_list = []
    for item in db_enquiries:
        enquiries_list.append({
            "id": item.id,
            "name": item.name,
            "email": item.email,
            "location": item.business_location or "N/A",
            "interest": item.partnership_interest or "Partnership",
            "subject": item.subject or "Strategic Proposal",
            "collaboration_details": item.collaboration_details.strip() if item.collaboration_details else "",

            "date": timezone.localtime(item.created_at).strftime("%b. %d, %Y") if item.created_at else "",
            "time": timezone.localtime(item.created_at).strftime("%I:%M %p").lower() if item.created_at else "",
            "status": item.status,
        })

    context = {
        "admin": admin_user,
        "enquiries": enquiries_list,
        "counts": counts,
        "page_title": "Partnership Enquiries",
        "page_subtitle": "Manage Partnership Proposals & GCC Vendor Networks"
    }
    return render(request, "partnership_enquiries.html", context)




def main_categories_view(request):
    """
    Unified view for Categories Management.
    Handles listing, creating, editing, and deleting Main Categories and Subcategories.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_main_category":
            name = request.POST.get("name")
            slug = request.POST.get("slug")
            description = request.POST.get("description", "")
            is_active = request.POST.get("is_active") == "on"
            image = request.FILES.get("image")
            MainCategory.objects.create(
                name=name, slug=slug, description=description, is_active=is_active, image=image
            )
            return redirect("main_categories")

        elif action == "edit_main_category":
            cat_id = request.POST.get("main_category_id")
            cat = MainCategory.objects.filter(id=cat_id).first()
            if cat:
                cat.name = request.POST.get("name", cat.name)
                cat.slug = request.POST.get("slug", cat.slug)
                cat.description = request.POST.get("description", "")
                cat.is_active = request.POST.get("is_active") == "on"
                if request.FILES.get("image"):
                    cat.image = request.FILES.get("image")
                cat.save()
            return redirect("main_categories")

        elif action == "delete_main_category":
            cat_id = request.POST.get("main_category_id")
            MainCategory.objects.filter(id=cat_id).delete()
            return redirect("main_categories")
        
        elif action == "add_sub_category":
            parent_id = request.POST.get("main_category_id")
            name = request.POST.get("name")
            slug = request.POST.get("slug")
            description = request.POST.get("description", "")
            is_active = request.POST.get("is_active") == "on"
            parent = MainCategory.objects.get(id=parent_id)
            SubCategory.objects.create(
                main_category=parent, name=name, slug=slug, description=description, is_active=is_active
            )
            return redirect("main_categories")

        elif action == "edit_sub_category":
            sub_id = request.POST.get("sub_category_id")
            sub = SubCategory.objects.filter(id=sub_id).first()
            if sub:
                sub.name = request.POST.get("name", sub.name)
                sub.slug = request.POST.get("slug", sub.slug)
                sub.description = request.POST.get("description", "")
                sub.is_active = request.POST.get("is_active") == "on"
                sub.save()
            return redirect("main_categories")

        elif action == "delete_sub_category":
            sub_id = request.POST.get("sub_category_id")
            SubCategory.objects.filter(id=sub_id).delete()
            return redirect("main_categories")

    # Prefetch related subcategories to avoid N+1 queries in the template accordion
    main_categories = MainCategory.objects.prefetch_related("subcategories").all()

    context = {
        "admin": admin_user,
        "categories": main_categories,
        "page_title": "Categories Management",
    }
    return render(request, "main_categories.html", context)


# ==========================================
# PRODUCT MANAGEMENT VIEWS
# ==========================================

def all_products_view(request):
    """
    List approved products with standard dashboard table layout.
    Supports bulk actions for changing active/inactive status.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from django.db.models import Q
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

    if request.method == "POST":
        action = request.POST.get("bulk_action")
        selected_ids = request.POST.getlist("selected_products")
        if selected_ids and action:
            if action == "Mark Active":
                Product.objects.filter(id__in=selected_ids).update(is_active=True)
            elif action == "Mark Inactive":
                Product.objects.filter(id__in=selected_ids).update(is_active=False)
            elif action == "Delete Selected":
                Product.objects.filter(id__in=selected_ids).delete()
        return redirect("/admin/products/all/")

    search_query = request.GET.get("q", "").strip()
    page_num = request.GET.get("page", 1)

    # Filter to show approved products (both active and inactive)
    products_qs = Product.objects.select_related("category", "subcategory", "vendor").filter(
        Q(enquiry_status__iexact="APPROVED") | Q(enquiry_status__iexact="approved")
    ).order_by("-created_at")
    approved_enquiries = SellerProductEnquiry.objects.filter(enquiry_status="approved")

    if search_query:
        products_qs = products_qs.filter(
            Q(product_name__icontains=search_query) | Q(product_id__icontains=search_query) | Q(model_no__icontains=search_query) | Q(brand__icontains=search_query)
        )

    paginator = Paginator(products_qs, 50)
    try:
        page_obj = paginator.page(page_num)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        "admin": admin_user,
        "products": page_obj,
        "page_obj": page_obj,
        "approved_enquiries": approved_enquiries,
        "search_query": search_query,
        "page_title": "All Products",
    }
    return render(request, "all_products.html", context)


def toggle_product_status_view(request, product_id):
    """
    Toggles the is_active status (Active / Inactive) of a product.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from django.shortcuts import get_object_or_404
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save()

    next_url = request.META.get("HTTP_REFERER") or f"/admin/products/{product_id}/"
    return redirect(next_url)



def add_product_view(request):
    """
    Form view for adding a new product listing.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    categories = SubCategory.objects.select_related("main_category").all()
    vendors = VendorDetails.objects.all()

    if request.method == "POST":
        title = request.POST.get("title")
        sku = request.POST.get("sku")
        description = request.POST.get("description", "")
        price = request.POST.get("price", "0.00")
        discount_price = request.POST.get("discount_price") or None
        stock_quantity = request.POST.get("stock_quantity", 0)
        brand = request.POST.get("brand", "")
        category_id = request.POST.get("category")
        vendor_id = request.POST.get("vendor")
        inventory_location = request.POST.get("inventory_location", "")
        manufacturing_country = request.POST.get("manufacturing_country", "")
        manufacturing_year = request.POST.get("manufacturing_year") or None
        dimensions = request.POST.get("dimensions", "")
        expiry_date = request.POST.get("expiry_date") or None
        currency = request.POST.get("currency", "USD")
        reason_to_sell = request.POST.get("reason_to_sell", "")
        warranty = request.POST.get("warranty", "")
        third_party_certificate = request.FILES.get("third_party_certificate")
        image = request.FILES.get("image")
        is_active = request.POST.get("is_active") == "on"
        enquiry_status = request.POST.get("enquiry_status", "APPROVED")

        category = None
        if category_id:
            category = SubCategory.objects.filter(id=category_id).first()

        vendor = None
        if vendor_id:
            vendor = VendorDetails.objects.filter(id=vendor_id).first()

        product = Product.objects.create(
            product_name=title or request.POST.get("product_name", ""),
            model_no=sku or request.POST.get("model_no", ""),
            description=description,
            liquidating_price=request.POST.get("liquidating_price") or price or 0,
            msrp=request.POST.get("msrp") or discount_price,
            quantity=stock_quantity,
            brand_name=brand or request.POST.get("brand_name", ""),
            category=category.main_category if (category and hasattr(category, 'main_category')) else None,
            subcategory=category,
            vendor=vendor,
            manufacturing_country=manufacturing_country,
            inventory_location=request.POST.get("inventory_location", ""),
            manufacturing_year=manufacturing_year if manufacturing_year else None,
            dimensions=dimensions,
            expiry_date=expiry_date if expiry_date else None,
            currency=currency,
            reason_to_sell=reason_to_sell,
            warranty=warranty,
            warranty_attachment=request.POST.get("warranty_attachment", ""),
            third_party_certificate=request.POST.get("third_party_certificate") in ("true", "1", "on", True),
            third_party_documents=request.POST.get("third_party_documents", ""),
            enquiry_status=enquiry_status,
            is_active=is_active,
        )

        gallery_urls = request.POST.getlist("gallery_image_urls") or request.POST.getlist("gallery_urls")
        is_real = request.POST.get("is_real_photo", "false").lower() in ("true", "1", "t", "yes")
        for g_url in gallery_urls:
            if g_url.strip():
                ProductImage.objects.create(
                    product=product,
                    image_url=g_url.strip(),
                    is_real_photo=is_real
                )

        gallery_files = request.FILES.getlist("gallery_images")
        for g_file in gallery_files:
            ProductImage.objects.create(
                product=product,
                image=g_file,
                is_real_photo=is_real
            )

        return redirect("all_products")

    context = {
        "admin": admin_user,
        "categories": categories,
        "vendors": vendors,
        "page_title": "Add New Product",
    }
    return render(request, "add_product.html", context)


def add_lot_view(request):
    """
    Form view for creating a new Lot batch package with full specs.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    categories = SubCategory.objects.select_related("main_category").all()
    vendors = VendorDetails.objects.all()

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description", "")
        category_id = request.POST.get("category")
        vendor_id = request.POST.get("vendor")
        user_full_name = request.POST.get("user_full_name", "")
        user_email = request.POST.get("user_email", "")
        user_mobile = request.POST.get("user_mobile", "")
        user_company = request.POST.get("user_company", "")
        user_industry = request.POST.get("user_industry", "")
        business_location = request.POST.get("business_location", "")
        inventory_location = request.POST.get("inventory_location", "") or business_location

        total_price = request.POST.get("total_price", "0.00")
        total_retail_value = request.POST.get("total_retail_value", "0.00")
        currency = request.POST.get("currency", "USD")
        allocation = request.POST.get("allocation", "100")
        sale_method = request.POST.get("sale_method", "offer")
        allow_counter_offers = request.POST.get("allow_counter_offers") == "on"

        condition = request.POST.get("condition", "")
        source_type = request.POST.get("source_type", "")
        load_type = request.POST.get("load_type", "")
        unit_type = request.POST.get("unit_type", "Pieces / Units")
        lot_size = request.POST.get("lot_size", "")
        pallet_count = request.POST.get("pallet_count", 1)
        weight = request.POST.get("weight", "")
        shipping_terms = request.POST.get("shipping_terms", "Buyer Arranges Freight")

        reason_to_sell = request.POST.get("reason_to_sell", "")
        is_active = request.POST.get("is_active") == "on"

        category = None
        if category_id:
            category = SubCategory.objects.filter(id=category_id).first()

        vendor = None
        if user_email:
            vendor = VendorDetails.objects.filter(email__iexact=user_email).first()
            if not vendor:
                # Auto-register new Seller user for this email
                uname = user_email.split("@")[0]
                base_uname = uname
                counter = 1
                while VendorDetails.objects.filter(username=uname).exists():
                    uname = f"{base_uname}{counter}"
                    counter += 1

                name_parts = user_full_name.strip().split(" ", 1)
                f_name = name_parts[0] if name_parts else uname
                l_name = name_parts[1] if len(name_parts) > 1 else ""

                vendor = VendorDetails.objects.create(
                    username=uname,
                    email=user_email,
                    first_name=f_name,
                    last_name=l_name,
                    mobile_number=user_mobile,
                    company_name=user_company,
                    business_location=business_location,
                    category_interested=user_industry,
                    user_type="SELLER",
                    status=True
                )
            else:
                # Update missing seller profile fields if provided
                updated = False
                if user_company and not vendor.company_name:
                    vendor.company_name = user_company
                    updated = True
                if user_mobile and not vendor.mobile_number:
                    vendor.mobile_number = user_mobile
                    updated = True
                if business_location and not vendor.business_location:
                    vendor.business_location = business_location
                    updated = True
                if user_industry and not vendor.category_interested:
                    vendor.category_interested = user_industry
                    updated = True
                if updated:
                    vendor.save()

        if not vendor and vendor_id:
            vendor = VendorDetails.objects.filter(id=vendor_id).first()

        raw_data = {
            "full_name": user_full_name or (vendor.username if vendor else ""),
            "user_full_name": user_full_name or (vendor.username if vendor else ""),
            "email": user_email or (vendor.email if vendor else ""),
            "user_email": user_email or (vendor.email if vendor else ""),
            "phone_no": user_mobile or (vendor.mobile_number if vendor else ""),
            "user_mobile": user_mobile or (vendor.mobile_number if vendor else ""),
            "company": user_company or (vendor.company_name if vendor else ""),
            "industry": user_industry or (vendor.category_interested if vendor else ""),
            "business_location": business_location or (vendor.business_location if vendor else ""),
            "vendor_id": vendor.id if vendor else None,
            "condition": condition,
            "stock_condition": condition,
            "source_type": source_type,
            "load_type": load_type,
            "unit_type": unit_type,
            "lot_size": lot_size,
            "pallet_count": pallet_count,
            "weight": weight,
            "shipping_terms": shipping_terms,
            "msrp": total_retail_value,
            "total_retail_value": total_retail_value,
            "allocation": allocation,
            "sale_method": sale_method,
            "open_to_offer": "Yes" if allow_counter_offers else "No",
            "allow_counter_offers": allow_counter_offers,
        }

        # Handle lot products if submitted via dynamic rows
        products_list = []
        item_skus = request.POST.getlist("item_sku[]")
        item_names = request.POST.getlist("item_name[]")
        item_categories = request.POST.getlist("item_category[]")
        item_conditions = request.POST.getlist("item_condition[]")
        item_quantities = request.POST.getlist("item_quantity[]")
        item_msrps = request.POST.getlist("item_msrp[]")

        for i in range(len(item_names)):
            name = item_names[i].strip()
            if name:
                sku = item_skus[i].strip() if i < len(item_skus) else ""
                cat = item_categories[i].strip() if i < len(item_categories) else ""
                cond = item_conditions[i].strip() if i < len(item_conditions) else (condition or "New / Surplus")
                qty = int(item_quantities[i]) if i < len(item_quantities) and item_quantities[i].isdigit() else 1
                msrp = float(item_msrps[i]) if i < len(item_msrps) and item_msrps[i] else 0.0

                products_list.append({
                    "sku": sku,
                    "product_name": name,
                    "category": cat,
                    "condition": cond,
                    "quantity": qty,
                    "msrp": msrp,
                    "ext_msrp": qty * msrp
                })

        # Handle Excel file import if provided
        excel_file = request.FILES.get("excel_file")
        if excel_file:
            try:
                from lots.importer import parse_spreadsheet
                excel_file.seek(0)
                parse_res = parse_spreadsheet(excel_file)
                parsed_prods = parse_res.get("all_items", [])
                if parsed_prods:
                    products_list.extend(parsed_prods)
                raw_data["parse_summary"] = parse_res.get("summary")
                raw_data["is_valid"] = parse_res.get("is_valid")
                raw_data["row_errors"] = parse_res.get("row_errors")
                raw_data["missing_mandatory_columns"] = parse_res.get("missing_mandatory_columns")
            except Exception as e:
                print(f"Error parsing admin excel file: {e}")

        raw_data["products"] = products_list

        # Create single unified Lot model
        lot = Lot.objects.create(
            title=title,
            description=description,
            category=category,
            category_name=category.name if category else "",
            vendor=vendor,
            inventory_location=inventory_location,
            total_price=total_price,
            currency=currency,
            reason_to_sell=reason_to_sell,
            file=excel_file,
            enquiry_status="pending",
            active_status="active" if is_active else "inactive",
            is_active=is_active,
            raw_data=raw_data,
        )

        return redirect("/admin/enquiries/lots/pending/")

    context = {
        "admin": admin_user,
        "categories": categories,
        "vendors": vendors,
        "page_title": "Create New Lot Package",
    }
    return render(request, "add_lot.html", context)


def price_control_view(request):
    """
    Dashboard for bulk price adjustments and global operational charges.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import PriceAdjustmentLog, Brand
    sys_settings, _ = SystemSettings.objects.get_or_create(id=1)

    categories = SubCategory.objects.all()
    
    # Get distinct brands from Brand model and Product table
    product_brands = list(Product.objects.exclude(brand_name="").values_list("brand_name", flat=True).distinct())
    brand_model_names = list(Brand.objects.values_list("name", flat=True).distinct())
    all_brands = sorted(list(set(product_brands + brand_model_names)))

    logs = PriceAdjustmentLog.objects.all().order_by("-created_at")[:50]

    context = {
        "admin": admin_user,
        "sys_settings": sys_settings,
        "categories": categories,
        "brands": all_brands,
        "logs": logs,
        "page_title": "System Price Controls",
        "charge_percent": sys_settings.operational_charge_percentage,
    }
    return render(request, "price_control.html", context)


def update_charge_percentage(request):
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    if request.method == "POST":
        from .models import PriceAdjustmentLog
        from django.contrib import messages

        sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
        charge_val = request.POST.get("operational_charge_percentage") or request.POST.get("charge_percentage", "0")
        try:
            charge_num = float(charge_val)
        except ValueError:
            charge_num = 0.0

        sys_settings.operational_charge_percentage = charge_num
        sys_settings.save()

        # Log entry
        PriceAdjustmentLog.objects.create(
            admin_name=admin_user.username or admin_user.email or "Admin",
            action_type="Global Charge Update",
            adjustment_method="Percentage (%)",
            value=charge_num,
            note=f"Operational charge updated to {charge_num:.2f}%",
            affected_products_count=Product.objects.count(),
            status="Applied"
        )
        messages.success(request, f"Global operational charge updated to {charge_num:.2f}%!")

    return redirect("price_control")


def price_control_apply(request):
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    if request.method == "POST":
        from .models import PriceAdjustmentLog
        from django.contrib import messages
        from decimal import Decimal, ROUND_HALF_UP

        action = (request.POST.get("adjustment_action") or request.POST.get("action") or "increase").upper()
        adj_method = (request.POST.get("adjustment_method") or request.POST.get("adjustment_type") or "percentage").upper()
        adj_value_raw = request.POST.get("adjustment_value") or request.POST.get("value", "0")

        try:
            adj_value = float(adj_value_raw)
        except ValueError:
            adj_value = 0.0

        filter_category = request.POST.get("filter_category") or request.POST.get("category_id")
        filter_brand = request.POST.get("filter_brand") or request.POST.get("brand")
        target_skus_raw = request.POST.get("target_skus", "")
        note = request.POST.get("adjustment_note", "").strip()

        products = Product.objects.all()

        if target_skus_raw.strip():
            import re
            sku_list = [s.strip() for s in re.split(r'[,\n]+', target_skus_raw) if s.strip()]
            id_list = [int(s) for s in sku_list if s.isdigit()]
            products = products.filter(Q(product_id__in=sku_list) | Q(model_no__in=sku_list) | Q(id__in=id_list))
        else:
            if filter_category and filter_category != "all":
                products = products.filter(subcategory_id=filter_category)
            if filter_brand and filter_brand != "all":
                products = products.filter(brand__iexact=filter_brand)

        backup_snapshot = {}
        affected_count = 0

        for product in products:
            curr_val = float(product.current_price or 0.0)
            backup_snapshot[str(product.id)] = curr_val

            if action == "INCREASE" or action == "INCREASE PRICES":
                if "PERCENT" in adj_method:
                    new_val = curr_val * (1.0 + (adj_value / 100.0))
                else:
                    new_val = curr_val + adj_value
            else:
                if "PERCENT" in adj_method:
                    new_val = curr_val * (1.0 - (adj_value / 100.0))
                else:
                    new_val = curr_val - adj_value

            new_val = max(0.0, new_val)
            product.current_price = Decimal(str(new_val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            product.save()
            affected_count += 1

        action_desc = "Increase Prices" if ("INCREASE" in action) else "Decrease Prices"
        method_desc = "Percentage (%)" if ("PERCENT" in adj_method) else "Fixed Amount"

        PriceAdjustmentLog.objects.create(
            admin_name=admin_user.username or admin_user.email or "Admin",
            action_type=action_desc,
            adjustment_method=method_desc,
            value=adj_value,
            note=note or f"Bulk {action_desc} of {adj_value} ({method_desc})",
            affected_products_count=affected_count,
            status="Applied",
            backup_snapshot=backup_snapshot
        )

        messages.success(request, f"Bulk price adjustment applied to {affected_count} product(s) successfully!")

    return redirect("price_control")


@csrf_exempt
def price_control_preview_api(request):
    """
    JSON Simulation API for Live Change Preview panel.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    import json
    import re

    if request.method == "POST":
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                data = request.POST
        except Exception:
            data = request.POST

        action = str(data.get("action", "increase")).upper()
        adj_method = str(data.get("method", "percentage")).upper()
        try:
            adj_value = float(data.get("value", 0))
        except ValueError:
            adj_value = 0.0

        filter_category = data.get("category", "all")
        filter_brand = data.get("brand", "all")
        target_skus_raw = data.get("target_skus", "")

        products = Product.objects.all()

        if target_skus_raw and target_skus_raw.strip():
            sku_list = [s.strip() for s in re.split(r'[,\n]+', target_skus_raw) if s.strip()]
            id_list = [int(s) for s in sku_list if s.isdigit()]
            products = products.filter(Q(product_id__in=sku_list) | Q(model_no__in=sku_list) | Q(id__in=id_list))
        else:
            if filter_category and filter_category != "all":
                products = products.filter(subcategory_id=filter_category)
            if filter_brand and filter_brand != "all":
                products = products.filter(brand__iexact=filter_brand)

        total_affected = products.count()
        sample_products = []

        for p in products[:10]:
            curr = float(p.current_price or 0.0)
            if "INCREASE" in action:
                if "PERCENT" in adj_method:
                    sim = curr * (1.0 + (adj_value / 100.0))
                else:
                    sim = curr + adj_value
            else:
                if "PERCENT" in adj_method:
                    sim = curr * (1.0 - (adj_value / 100.0))
                else:
                    sim = curr - adj_value
            sim = max(0.0, sim)
            diff = sim - curr

            sample_products.append({
                "id": p.id,
                "name": p.product_name,
                "code": p.product_id or p.model_no,
                "old_price": f"${curr:,.2f}",
                "new_price": f"${sim:,.2f}",
                "diff": f"{'+' if diff >= 0 else ''}${diff:,.2f}",
            })

        return JsonResponse({
            "success": True,
            "total_affected": total_affected,
            "sample_products": sample_products
        })

    return JsonResponse({"success": False, "message": "Invalid request method"}, status=405)


@csrf_exempt
def price_control_rollback_api(request, log_id):
    """
    Rolls back a recorded bulk price adjustment log.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    from .models import PriceAdjustmentLog
    from decimal import Decimal

    try:
        log = PriceAdjustmentLog.objects.get(id=log_id)
        if log.status == "Rolled Back":
            return JsonResponse({"success": False, "message": "Adjustment has already been rolled back."})

        snapshot = log.backup_snapshot or {}
        reverted_count = 0
        for p_id, old_price in snapshot.items():
            try:
                prod = Product.objects.get(id=int(p_id))
                prod.current_price = Decimal(str(old_price))
                prod.save()
                reverted_count += 1
            except Product.DoesNotExist:
                continue

        log.status = "Rolled Back"
        log.save()
        return JsonResponse({"success": True, "message": f"Successfully rolled back price adjustment for {reverted_count} product(s)."})
    except PriceAdjustmentLog.DoesNotExist:
        return JsonResponse({"success": False, "message": "Log entry not found."}, status=404)



def product_detail_view(request, product_id):
    """
    Detailed view for a specific product containing all database fields.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from django.db.models import Q
    from .models import Product
    lookup = Q(id=product_id) | Q(product_id=str(product_id))
    product = Product.objects.select_related("category", "subcategory", "vendor").prefetch_related("images").filter(lookup).first()
    if not product:
        product = Product.objects.select_related("category", "subcategory", "vendor").prefetch_related("images").first()
    if not product:
        return redirect("all_products")

    vendor = product.vendor
    if not vendor and product.vendor_id:
        from .models import VendorDetails
        vendor = VendorDetails.objects.filter(id=product.vendor_id).first()
    if not vendor:
        from .models import VendorDetails, VendorOTP
        latest_otp = VendorOTP.objects.filter(is_used=True).order_by("-created_at").first()
        if latest_otp:
            vendor = latest_otp.vendor or VendorDetails.objects.filter(email__iexact=latest_otp.email).first()
        if not vendor:
            vendor = VendorDetails.objects.order_by("-id").first()
        if vendor:
            product.vendor = vendor
            product.save(update_fields=["vendor"])

    company_val = "N/A"
    full_name_val = "N/A"
    phone_val = "N/A"
    email_val = "N/A"
    business_location_val = "N/A"
    industry_val = "N/A"

    if vendor:
        full_name_val = vendor.full_name or vendor.username or "N/A"
        phone_val = vendor.mobile_number or "N/A"
        email_val = vendor.email or "N/A"
        company_val = vendor.company_name or vendor.username or "Individual Seller"
        business_location_val = vendor.business_location or "N/A"
        if vendor.category_interested:
            if isinstance(vendor.category_interested, list):
                industry_val = ", ".join(vendor.category_interested)
            else:
                industry_val = str(vendor.category_interested)
        elif vendor.business_type:
            industry_val = vendor.business_type
        elif vendor.user_type:
            industry_val = vendor.user_type

    user_data = {
        "vendor_id": vendor.vendor_id if vendor else "N/A",
        "user_id": vendor.vendor_id if vendor else "N/A",
        "raw_vendor_id": vendor.id if vendor else None,
        "raw_user_id": vendor.id if vendor else None,
        "full_name": full_name_val,
        "phone_no": phone_val,
        "email": email_val,
        "company": company_val,
        "business_location": business_location_val,
        "industry": industry_val,
    }

    from .models import MainCategory
    categories = MainCategory.objects.prefetch_related("subcategories").all()

    context = {
        "admin": admin_user,
        "product": product,
        "user_data": user_data,
        "categories": categories,
        "page_title": f"Product Details - {product.product_name}",
    }
    return render(request, "product_detail.html", context)



def excel_test_view(request):
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")
    context = {"admin": admin_user, "page_title": "Excel Parser Test"}
    return render(request, 'excel_test.html', context)


# ==========================================
# VENDOR VIEWS
# ==========================================

def _get_authenticated_vendor(request):
    vendor_id = request.session.get("vendorid")
    session_version = request.session.get("vendor_session_version")

    if not vendor_id or session_version is None:
        return None

    try:
        vendor_user = VendorDetails.objects.get(id=vendor_id, status=True)
        # Note: could add caching here similarly to admin
        if session_version != vendor_user.session_version:
            return None
        return vendor_user
    except VendorDetails.DoesNotExist:
        return None

def vendor_login_page(request):
    vendor_user = _get_authenticated_vendor(request)
    if vendor_user:
        return redirect("adminIndex")
    return render(request, "login.html")  # Might need a separate vendor_login.html later

@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def vendor_register(request):
    if request.method == "GET":
        return Response(
            {"message": "Submit POST with username, email, firstname, lastname, confirm_password to register."},
            status=status.HTTP_200_OK,
        )

    serializer = VendorRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    username = data["username"]
    email = data["email"].strip().lower()
    mobile_number = data.get("resolved_mobile_number", "")
    confirm_pass = data["resolved_password"]

    salt = uuid.uuid4().hex
    enc_pass = hashlib.sha256(salt.encode() + confirm_pass.encode()).hexdigest() + ":" + salt

    vendor_user = VendorDetails.objects.create(
        username=username,
        email=email,
        mobile_number=mobile_number,
        pass_word=enc_pass,
        status=True,
        session_version=1,
    )

    return Response(
        {
            "success": True,
            "message": "Vendor registration successful. Please proceed to login.",
            "redirect_url": "/admin/vendor-login/",
            "data": VendorDetailsSerializer(vendor_user).data,
        },
        status=status.HTTP_201_CREATED,
    )

@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def vendor_login(request):
    if request.method == "GET":
        if request.headers.get("Accept", "").find("text/html") != -1:
            return vendor_login_page(request)
        return Response(
            {"message": "Submit POST with user_email and user_pass to login."},
            status=status.HTTP_200_OK,
        )

    # Reusing AdminLoginSerializer as it only takes email/username and password
    serializer = AdminLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    identifier = serializer.validated_data["resolved_identifier"].strip()
    user_pass = serializer.validated_data["resolved_password"]

    vendor_user = None
    vendor_qs = VendorDetails.objects.filter(
        email__iexact=identifier
    ) | VendorDetails.objects.filter(username__iexact=identifier)

    if vendor_qs.exists():
        candidate = vendor_qs.first()
        if not candidate.status:
            return Response(
                {"success": False, "message": "Account is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            stored_hash, salt = candidate.pass_word.split(":")
            computed_hash = hashlib.sha256(salt.encode() + user_pass.encode()).hexdigest()
            if computed_hash == stored_hash:
                vendor_user = candidate
        except (ValueError, AttributeError):
            pass

    if not vendor_user:
        return Response(
            {"success": False, "message": "Invalid email/username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["vendorid"] = vendor_user.id
    request.session["vendor_session_version"] = vendor_user.session_version

    return Response(
        {
            "success": True,
            "message": "Vendor login successful.",
            "redirect_url": "/admin/vendor-index/",
            "data": VendorDetailsSerializer(vendor_user).data,
        },
        status=status.HTTP_200_OK,
    )

def vendor_logout_view(request):
    if "vendorid" in request.session:
        del request.session["vendorid"]
    if "vendor_session_version" in request.session:
        del request.session["vendor_session_version"]
    return redirect("vendor_login_page")

@api_view(["GET"])
@permission_classes([AllowAny])
def get_current_vendor(request):
    vendor_user = _get_authenticated_vendor(request)
    if not vendor_user:
        return Response({"authenticated": False}, status=status.HTTP_401_UNAUTHORIZED)
    return Response({
        "authenticated": True,
        "vendor": VendorDetailsSerializer(vendor_user).data
    }, status=status.HTTP_200_OK)


def brands_management_view(request):
    """
    Renders and processes Brand Management In Landing Page using real database records.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Brand
    from django.db.models import Q
    from django.contrib import messages

    editing_brand = None
    edit_id = request.GET.get("edit") or request.POST.get("edit_brand_id")
    if edit_id:
        try:
            editing_brand = Brand.objects.get(id=edit_id)
        except Brand.DoesNotExist:
            editing_brand = None

    if request.method == "POST":
        brand_name = request.POST.get("name", "").strip()
        alt_text = request.POST.get("alt_text", "").strip()
        redirect_link = request.POST.get("redirect_link", "").strip()
        description = request.POST.get("description", "").strip()
        image_file = request.FILES.get("image")

        if not brand_name:
            messages.error(request, "Brand Name is required.")
        else:
            if editing_brand:
                editing_brand.name = brand_name
                editing_brand.alt_text = alt_text
                editing_brand.redirect_link = redirect_link
                editing_brand.description = description
                if image_file:
                    editing_brand.image = image_file
                editing_brand.save()
                messages.success(request, f"Brand '{brand_name}' updated successfully!")
                return redirect("brands_management")
            else:
                new_brand = Brand.objects.create(
                    name=brand_name,
                    alt_text=alt_text,
                    redirect_link=redirect_link,
                    description=description,
                    image=image_file if image_file else None
                )
                messages.success(request, f"Brand '{brand_name}' added successfully!")
                return redirect("brands_management")

    search_query = request.GET.get("q", "").strip()
    brands_qs = Brand.objects.all().order_by("-created_at")

    if search_query:
        brands_qs = brands_qs.filter(
            Q(name__icontains=search_query) | Q(alt_text__icontains=search_query) | Q(redirect_link__icontains=search_query)
        )

    total_brands_count = Brand.objects.count()

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "brands": brands_qs,
        "editing_brand": editing_brand,
        "search_query": search_query,
        "total_brands_count": total_brands_count,
    }
    return render(request, "brand_management.html", context)


@csrf_exempt
def brands_delete_api(request, brand_id):
    """
    Deletes a single brand by ID.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    from .models import Brand
    try:
        brand = Brand.objects.get(id=brand_id)
        brand_name = brand.name
        brand.delete()
        return JsonResponse({"success": True, "message": f"Brand '{brand_name}' deleted successfully."})
    except Brand.DoesNotExist:
        return JsonResponse({"success": False, "message": "Brand not found."}, status=404)


@csrf_exempt
def brands_batch_delete_api(request):
    """
    Deletes multiple selected brands by IDs.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid method"}, status=405)

    import json
    from .models import Brand

    try:
        data = json.loads(request.body)
        ids = data.get("ids", [])
        if not ids or not isinstance(ids, list):
            return JsonResponse({"success": False, "message": "No brand IDs provided."}, status=400)

        deleted_count, _ = Brand.objects.filter(id__in=ids).delete()
        return JsonResponse({"success": True, "message": f"Successfully deleted {deleted_count} brand(s)."})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@csrf_exempt
def toggle_maintenance_mode_api(request):
    """
    Toggles global Maintenance Mode on/off.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
    
    if request.method == "POST":
        import json
        if request.content_type == "application/json" and request.body:
            try:
                data = json.loads(request.body)
                if "is_maintenance_mode" in data:
                    sys_settings.is_maintenance_mode = bool(data["is_maintenance_mode"])
                else:
                    sys_settings.is_maintenance_mode = not sys_settings.is_maintenance_mode
            except Exception:
                sys_settings.is_maintenance_mode = not sys_settings.is_maintenance_mode
        else:
            sys_settings.is_maintenance_mode = not sys_settings.is_maintenance_mode

        sys_settings.save()

        # Log entry
        from .models import PriceAdjustmentLog
        PriceAdjustmentLog.objects.create(
            admin_name=admin_user.username or admin_user.email or "Admin",
            action_type="Maintenance Mode Toggle",
            value=0,
            note=f"Maintenance Mode set to {'ON' if sys_settings.is_maintenance_mode else 'OFF'}",
            status="Applied"
        )

        return JsonResponse({
            "success": True,
            "is_maintenance_mode": sys_settings.is_maintenance_mode,
            "status_text": "Maintenance" if sys_settings.is_maintenance_mode else "Live",
            "message": f"Website set to {'Maintenance' if sys_settings.is_maintenance_mode else 'Live'} mode."
        })

    return JsonResponse({
        "success": True,
        "is_maintenance_mode": sys_settings.is_maintenance_mode,
        "status_text": "Maintenance" if sys_settings.is_maintenance_mode else "Live"
    })


def popup_view(request):
    """
    Renders and manages Popup Notification settings for the Admin Portal.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import PopupSetting
    from django.contrib import messages

    popup_setting, _ = PopupSetting.objects.get_or_create(id=1)

    if request.method == "POST":
        popup_setting.title = request.POST.get("title", "").strip() or "Important Admin Notification"
        popup_setting.message = request.POST.get("message", "").strip()
        popup_setting.popup_type = request.POST.get("popup_type", "info")
        popup_setting.is_active = request.POST.get("is_active") in ["on", "true", "1", "True"]
        
        try:
            delay_val = int(request.POST.get("delay_minutes", 1))
            popup_setting.delay_minutes = max(1, delay_val)
        except ValueError:
            popup_setting.delay_minutes = 1

        popup_setting.button_label = request.POST.get("button_label", "Got It").strip()
        popup_setting.button_link = request.POST.get("button_link", "").strip()

        banner_file = request.FILES.get("banner_image")
        if banner_file:
            popup_setting.banner_image = banner_file

        popup_setting.save()
        messages.success(request, f"Pop Up configuration saved successfully! Re-trigger delay set to {popup_setting.delay_minutes} minute(s).")
        return redirect("popup_view")

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "popup": popup_setting,
    }
    return render(request, "popup_settings.html", context)


# ==============================================================================
# AUCTION MANAGEMENT ADMIN VIEWS (MODEL-AGNOSTIC ENGINE)
# ==============================================================================

def admin_auctions_view(request):
    """
    Renders Admin Auctions Management dashboard with live KPI counters, filters, and list.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Auction, AuctionBid, MainCategory
    from django.core.paginator import Paginator

    status_filter = request.GET.get("status", "all").lower()
    search_query = request.GET.get("q", "").strip()

    qs = Auction.objects.select_related("category", "vendor", "winner").prefetch_related("images").all()

    if status_filter != "all":
        qs = qs.filter(status=status_filter)

    if search_query:
        qs = qs.filter(
            Q(title__icontains=search_query) |
            Q(auction_id__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(item_reference_id__icontains=search_query)
        )

    # Sync temporal statuses for list display
    for auc in qs[:50]:
        auc.sync_status()

    # KPI Statistics
    now = timezone.now()
    stats = {
        "total_auctions": Auction.objects.count(),
        "live_auctions": Auction.objects.filter(status="live").count(),
        "scheduled_auctions": Auction.objects.filter(status="scheduled").count(),
        "sold_auctions": Auction.objects.filter(status="sold").count(),
        "total_bids": AuctionBid.objects.count(),
    }

    paginator = Paginator(qs, 12)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "page_obj": page_obj,
        "auctions": page_obj.object_list,
        "stats": stats,
        "status_filter": status_filter,
        "search_query": search_query,
    }
    return render(request, "auctions_list.html", context)


def admin_auction_create_view(request):
    """
    Renders creation form and handles new Auction listing setup.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Auction, AuctionImage, MainCategory
    from django.contrib import messages

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        item_type = request.POST.get("item_type", "custom")
        item_reference_id = request.POST.get("item_reference_id", "").strip()
        category_id = request.POST.get("category_id")

        starting_bid = Decimal(request.POST.get("starting_bid", "0.00") or "0.00")
        reserve_price = Decimal(request.POST.get("reserve_price", "0.00") or "0.00")
        bid_increment = Decimal(request.POST.get("bid_increment", "25.00") or "25.00")
        buy_now_raw = request.POST.get("buy_now_price", "").strip()
        buy_now_price = Decimal(buy_now_raw) if buy_now_raw else None

        start_time_str = request.POST.get("start_time")
        end_time_str = request.POST.get("end_time")
        auto_extend_minutes = int(request.POST.get("auto_extend_minutes", 3) or 3)

        if not title or not start_time_str or not end_time_str:
            messages.error(request, "Title, Start Time, and End Time are required fields.")
            return redirect("admin_auction_create")

        start_time = timezone.datetime.fromisoformat(start_time_str)
        end_time = timezone.datetime.fromisoformat(end_time_str)
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time)

        now = timezone.now()
        initial_status = "live" if start_time <= now <= end_time else ("scheduled" if start_time > now else "ended")

        category = MainCategory.objects.filter(id=category_id).first() if category_id else None

        # Build snapshot metadata
        item_metadata = {
            "origin": "Admin Portal Creation",
            "created_by": admin_user.username,
            "reference_code": item_reference_id or None,
            "notes": request.POST.get("manifest_notes", "").strip(),
        }

        auction = Auction.objects.create(
            title=title,
            description=description,
            item_type=item_type,
            item_reference_id=item_reference_id,
            item_metadata=item_metadata,
            category=category,
            starting_bid=starting_bid,
            current_bid=starting_bid,
            reserve_price=reserve_price,
            bid_increment=bid_increment,
            buy_now_price=buy_now_price,
            start_time=start_time,
            end_time=end_time,
            auto_extend_minutes=auto_extend_minutes,
            status=initial_status,
        )

        # Handle uploaded images
        images = request.FILES.getlist("images")
        for idx, img in enumerate(images):
            AuctionImage.objects.create(
                auction=auction,
                image=img,
                is_primary=(idx == 0),
                display_order=idx,
            )

        messages.success(request, f"Auction '{auction.title}' (#{auction.auction_id}) created successfully!")
        return redirect("admin_auctions_view")

    categories = MainCategory.objects.all().order_by("name")
    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "categories": categories,
    }
    return render(request, "auction_create.html", context)


def admin_auction_detail_view(request, auction_id):
    """
    Renders live auction monitoring dashboard, real-time bid history, and admin emergency controls.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return redirect("admin_login_page")

    from .models import Auction

    try:
        if str(auction_id).isdigit():
            auction = Auction.objects.select_related("category", "vendor", "winner").prefetch_related("images", "bids").get(id=int(auction_id))
        else:
            auction = Auction.objects.select_related("category", "vendor", "winner").prefetch_related("images", "bids").get(auction_id=auction_id)
    except Auction.DoesNotExist:
        from django.http import Http404
        raise Http404("Auction listing not found")

    auction.sync_status()
    bids = auction.bids.select_related("bidder").order_by("-created_at")

    context = {
        "admin": admin_user,
        "is_super_admin": admin_user.account_type == "SuperAdmin" or admin_user.email == "super@gmail.com",
        "auction": auction,
        "bids": bids,
    }
    return render(request, "auction_detail.html", context)


def admin_auction_action_api(request, auction_id):
    """
    API for admin actions on an auction: extend time, close & evaluate, cancel, or activate live.
    """
    admin_user = _get_authenticated_admin(request)
    if not admin_user:
        return JsonResponse({"success": False, "message": "Admin authorization required."}, status=401)

    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Method not allowed."}, status=405)

    from .models import Auction
    from .auction_engine import AuctionEngine
    from datetime import timedelta

    try:
        auction = Auction.objects.get(auction_id=auction_id) if not str(auction_id).isdigit() else Auction.objects.get(id=int(auction_id))
    except Auction.DoesNotExist:
        return JsonResponse({"success": False, "message": "Auction not found."}, status=404)

    action = request.POST.get("action", "").lower()

    if action == "extend":
        mins = int(request.POST.get("minutes", 5))
        auction.end_time += timedelta(minutes=mins)
        auction.save(update_fields=["end_time", "updated_at"])
        return JsonResponse({
            "success": True,
            "message": f"Auction extended by {mins} minutes. New end time: {auction.end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}.",
            "new_end_time": auction.end_time.isoformat(),
        })

    elif action == "close":
        evaluated = AuctionEngine.evaluate_and_close(auction.id)
        return JsonResponse({
            "success": True,
            "message": f"Auction closed. Final status: '{evaluated.status}'.",
            "status": evaluated.status,
            "winner": evaluated.winner.username if evaluated.winner else None,
            "winning_amount": str(evaluated.winning_bid_amount) if evaluated.winning_bid_amount else None,
        })

    elif action == "cancel":
        auction.status = "cancelled"
        auction.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "message": "Auction cancelled.", "status": "cancelled"})

    elif action == "go_live":
        auction.status = "live"
        auction.save(update_fields=["status", "updated_at"])
        return JsonResponse({"success": True, "message": "Auction is now LIVE.", "status": "live"})

    return JsonResponse({"success": False, "message": f"Unknown action '{action}'."}, status=400)





