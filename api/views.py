import threading
import logging
from django.utils import timezone
from django.db import connection, close_old_connections
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
import json
from .models import Item
from .serializers import ItemSerializer

logger = logging.getLogger(__name__)


@api_view(["GET"])
def api_root(request):
    """
    Root API endpoint providing basic backend info and available entrypoints.
    """
    return Response(
        {
            "project": "Surplus Backend API",
            "version": "1.0.0",
            "status": "online",
            "endpoints": {
                "health": "/api/health/",
                "items": "/api/items/",
                "admin": "/admin/",
            },
        }
    )


@api_view(["GET"])
def health_check(request):
    """
    Health check endpoint verifying backend status and database connection.
    """
    db_status = "ok"
    db_error = None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception as e:
        db_status = "unavailable"
        db_error = str(e)

    http_status = (
        status.HTTP_200_OK
        if db_status == "ok"
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )

    return Response(
        {
            "status": "healthy" if db_status == "ok" else "degraded",
            "timestamp": timezone.now().isoformat(),
            "database": {
                "status": db_status,
                "vendor": connection.vendor,
                "error": db_error,
            },
        },
        status=http_status,
    )


@api_view(["GET"])
def get_maintenance_status(request):
    """
    Public REST API to get global website maintenance status.
    Endpoint: GET /api/maintenance-status/
    """
    from AdminApp.models import SystemSettings
    sys_settings, _ = SystemSettings.objects.get_or_create(id=1)
    return Response({
        "is_maintenance_mode": sys_settings.is_maintenance_mode,
        "maintenance_message": sys_settings.maintenance_message or "Website is currently under maintenance. Please check back later.",
        "status_text": "Maintenance" if sys_settings.is_maintenance_mode else "Live"
    })



class ItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and editing Item instances.
    """
    queryset = Item.objects.all().order_by("-created_at")
    serializer_class = ItemSerializer


# -------------------------------------------------------------
# Public Content Page APIs for Headless Frontend (Another Server)
# -------------------------------------------------------------

@api_view(["GET"])
def get_public_pages_list(request):
    """
    Public REST API to list published content pages for frontend routing & navigation.
    Endpoint: GET /api/pages/
    Query params: ?category=Policy | ?header=true | ?footer=true
    """
    from AdminApp.models import ContentPage
    qs = ContentPage.objects.filter(status="published", is_active=True).order_by("sort_order", "title")

    category = request.GET.get("category")
    if category:
        qs = qs.filter(category=category)

    header_only = request.GET.get("header")
    if header_only in ("true", "1"):
        qs = qs.filter(show_in_header=True)

    footer_only = request.GET.get("footer")
    if footer_only in ("true", "1"):
        qs = qs.filter(show_in_footer=True)

    pages = []
    for p in qs:
        pages.append({
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "category": p.category,
            "url": f"/{p.slug}/",
            "show_in_header": p.show_in_header,
            "show_in_footer": p.show_in_footer,
            "sort_order": p.sort_order,
            "updated_at": p.updated_at.isoformat(),
        })

    return Response({
        "success": True,
        "count": len(pages),
        "pages": pages,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_public_categories(request):
    """
    Public REST API to fetch all Main Categories and their nested Sub Categories.
    Endpoint: GET /api/categories/
    """
    from AdminApp.models import MainCategory
    main_categories = MainCategory.objects.filter(is_active=True).prefetch_related("subcategories").order_by("name")

    categories_data = []
    for main in main_categories:
        subcats = []
        for sub in main.subcategories.filter(is_active=True):
            sub_img = sub.image.url if sub.image else None
            sub_abs_img = request.build_absolute_uri(sub_img) if sub_img else None
            subcats.append({
                "id": sub.id,
                "name": sub.name,
                "slug": sub.slug,
                "description": sub.description,
                "image": sub_img,
                "image_url": sub_abs_img,
                "icon": sub_img,
            })

        main_img = main.image.url if main.image else None
        main_abs_img = request.build_absolute_uri(main_img) if main_img else None
        categories_data.append({
            "id": main.id,
            "name": main.name,
            "slug": main.slug,
            "description": main.description,
            "image": main_img,
            "image_url": main_abs_img,
            "icon": main_img,
            "subcategories": subcats,
        })

    return Response({
        "success": True,
        "count": len(categories_data),
        "categories": categories_data,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_public_page_detail(request, slug):
    """
    Public REST API to fetch complete page payload (HTML content + Yoast SEO metadata) by slug for frontend rendering.
    Endpoint: GET /api/pages/<slug>/
    """
    from AdminApp.models import ContentPage
    try:
        page = ContentPage.objects.get(slug=slug, status="published", is_active=True)
    except ContentPage.DoesNotExist:
        return Response({
            "success": False,
            "message": f"Page with slug '{slug}' not found or not published."
        }, status=status.HTTP_404_NOT_FOUND)

    payload = {
        "id": page.id,
        "title": page.title,
        "slug": page.slug,
        "category": page.category,
        "content": page.content,
        "components": page.components or [],
        "seo": {
            "focus_keyphrase": page.focus_keyphrase or "",
            "meta_title": page.meta_title or page.title or "",
            "meta_description": page.meta_description or "",
            "meta_keywords": page.meta_keywords or "",
            "canonical_url": page.canonical_url or f"https://surplus.com/{page.slug}/",
            "robots_index": page.robots_index or "index",
            "robots_follow": page.robots_follow or "follow",
            "robots_advanced": page.robots_advanced or "",
            "og_title": page.og_title or "",
            "og_description": page.og_description or "",
            "og_image": page.og_image or "",
            "twitter_title": page.twitter_title or "",
            "twitter_description": page.twitter_description or "",
            "twitter_image": page.twitter_image or "",
            "schema_type": page.schema_type or "WebPage",
            "structured_data": page.structured_data or {},
        },
        "navigation": {
            "show_in_header": page.show_in_header,
            "show_in_footer": page.show_in_footer,
            "sort_order": page.sort_order,
        },
        "created_at": page.created_at.isoformat(),
        "updated_at": page.updated_at.isoformat(),
    }

    return Response({
        "success": True,
        "page": payload,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_public_navigation_menu(request):
    """
    Public REST API providing structured header and footer menus for frontend layouts.
    Endpoint: GET /api/pages/navigation/
    """
    from AdminApp.models import ContentPage
    published_pages = ContentPage.objects.filter(status="published", is_active=True).order_by("sort_order", "title")

    header_items = []
    footer_grouped = {}

    for p in published_pages:
        item = {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "url": f"/{p.slug}/",
            "category": p.category,
            "sort_order": p.sort_order,
        }
        if p.show_in_header:
            header_items.append(item)
        if p.show_in_footer:
            cat = p.category
            if cat not in footer_grouped:
                footer_grouped[cat] = []
            footer_grouped[cat].append(item)

    return Response({
        "success": True,
        "header_menu": header_items,
        "footer_menu": footer_grouped,
    }, status=status.HTTP_200_OK)


# -------------------------------------------------------------
# Public Blog REST APIs for Frontend Server
# -------------------------------------------------------------

def _resolve_blog_image_url(b, request=None):
    """
    Helper to resolve the best image URL for a blog post.
    Prioritizes uploaded image file (b.image.url) if present, then falls back to featured_image_url.
    Ensures valid path format.
    """
    img_url = ""
    if b.image:
        try:
            img_url = b.image.url
        except Exception:
            img_url = ""
    if not img_url and b.featured_image_url:
        img_url = b.featured_image_url.strip()

    if img_url and not img_url.startswith("http://") and not img_url.startswith("https://") and not img_url.startswith("/"):
        img_url = f"/{img_url}"
    return img_url or ""


@api_view(["GET"])
def get_public_blogs_list(request):
    """
    Public REST API to list published blog posts for frontend rendering.
    Endpoint: GET /api/blogs/
    Query params: ?category=Tech | ?search=query | ?page=1
    """
    from AdminApp.models import BlogPost
    from django.db.models import Q
    from django.core.paginator import Paginator

    qs = BlogPost.objects.filter(status="published", is_active=True).order_by("-created_at")

    category = request.GET.get("category")
    if category and category.lower() != "all":
        qs = qs.filter(category_name__iexact=category.strip())

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(excerpt__icontains=search) | Q(content__icontains=search))

    page_num = request.GET.get("page", 1)
    paginator = Paginator(qs, 12)
    try:
        page_obj = paginator.page(page_num)
    except Exception:
        page_obj = paginator.page(1)

    blogs_data = []
    for b in page_obj:
        img_url = _resolve_blog_image_url(b, request)
        abs_img_url = request.build_absolute_uri(img_url) if (img_url and request) else img_url

        blogs_data.append({
            "id": b.id,
            "title": b.title,
            "slug": b.slug,
            "blog_code": b.blog_code,
            "author": b.author,
            "category": b.category_name,
            "excerpt": b.excerpt,
            "image": img_url,
            "image_url": img_url,
            "cover_image": img_url,
            "coverImage": img_url,
            "featured_image": img_url,
            "featured_image_url": img_url,
            "absolute_image_url": abs_img_url,
            "read_time": b.read_time,
            "total_reads": b.total_reads,
            "seo": {
                "meta_title": b.meta_title or b.title,
                "meta_description": b.meta_description or b.excerpt,
                "meta_keywords": b.meta_keywords or "",
            },
            "created_at": b.created_at.isoformat(),
            "updated_at": b.updated_at.isoformat(),
        })

    return Response({
        "success": True,
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "blogs": blogs_data,
        "results": blogs_data,
        "data": blogs_data,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_public_blog_detail(request, slug):
    """
    Public REST API to fetch complete blog post by slug.
    Endpoint: GET /api/blogs/<slug>/
    """
    from AdminApp.models import BlogPost
    try:
        blog = BlogPost.objects.get(slug=slug, status="published", is_active=True)
        BlogPost.objects.filter(id=blog.id).update(total_reads=blog.total_reads + 1)
        blog.refresh_from_db()
    except BlogPost.DoesNotExist:
        return Response({
            "success": False,
            "message": f"Blog post with slug '{slug}' not found or not published."
        }, status=status.HTTP_404_NOT_FOUND)

    img_url = _resolve_blog_image_url(blog, request)
    abs_img_url = request.build_absolute_uri(img_url) if (img_url and request) else img_url

    payload = {
        "id": blog.id,
        "title": blog.title,
        "slug": blog.slug,
        "blog_code": blog.blog_code,
        "author": blog.author,
        "category": blog.category_name,
        "excerpt": blog.excerpt,
        "content": blog.content,
        "image": img_url,
        "image_url": img_url,
        "cover_image": img_url,
        "coverImage": img_url,
        "featured_image": img_url,
        "featured_image_url": img_url,
        "absolute_image_url": abs_img_url,
        "read_time": blog.read_time,
        "total_reads": blog.total_reads,
        "seo": {
            "meta_title": blog.meta_title or blog.title,
            "meta_description": blog.meta_description or blog.excerpt,
            "meta_keywords": blog.meta_keywords or "",
        },
        "created_at": blog.created_at.isoformat(),
        "updated_at": blog.updated_at.isoformat(),
    }

    return Response({
        "success": True,
        "blog": payload,
        "data": payload,
        **payload,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_public_blog_categories(request):
    """
    Public REST API to list distinct blog categories with post count.
    Endpoint: GET /api/blog-categories/
    """
    from AdminApp.models import BlogPost
    from django.db.models import Count
    from django.utils.text import slugify

    cats = (
        BlogPost.objects.filter(status="published", is_active=True)
        .exclude(category_name="")
        .values("category_name")
        .annotate(total_blogs=Count("id"))
        .order_by("-total_blogs")
    )
    data = [
        {
            "id": idx + 1,
            "name": c["category_name"],
            "slug": slugify(c["category_name"]),
            "description": f"Articles related to {c['category_name']}",
            "total_blogs": c["total_blogs"],
        }
        for idx, c in enumerate(cats)
    ]
    return Response(data, status=status.HTTP_200_OK)


# -------------------------------------------------------------
# Public Enquiry APIs for Frontend (Product & Lot Batch)
# -------------------------------------------------------------

from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import permission_classes

@api_view(["POST"])
@permission_classes([AllowAny])
def submit_seller_enquiry(request):
    """
    Public/Seller REST API for sellers to submit individual product enquiries.
    Endpoint: POST /api/enquiries/seller/
    Delegates directly to submit_product_request for uniform processing.
    """
    return submit_product_request(request)


@api_view(["POST"])
def submit_lot_enquiry(request):
    """
    Public REST API for sellers to submit bulk lot enquiries with spreadsheet upload.
    Endpoint: POST /api/enquiries/lots/
    Auto-generates BAT-XXXXX ID. Parses Excel/CSV to create LotProducts.
    """
    from AdminApp.models import Lot
    from AdminApp.serializers import LotSerializer
    import pandas as pd
    import io

    file_obj = (
        request.FILES.get("file")
        or request.FILES.get("lot_file")
        or request.FILES.get("excel_file")
        or request.FILES.get("manifest")
        or request.FILES.get("spreadsheet")
        or request.FILES.get("excel")
    )
    if not file_obj:
        return Response({"success": False, "message": "File is required."}, status=status.HTTP_400_BAD_REQUEST)

    raw_data = {}
    if isinstance(request.data, dict):
        raw_data = {k: v for k, v in request.data.items() if k not in ("file", "lot_file", "excel_file", "manifest", "spreadsheet", "excel", "manifest_items", "preview_items", "parsed_items", "lot_details", "products_list", "products")}

    products_list = []
    parse_result = None
    try:
        from lots.importer import parse_spreadsheet
        file_obj.seek(0)
        parse_result = parse_spreadsheet(file_obj)
        products_list = parse_result.get("all_items", [])
    except Exception as e:
        print(f"Error parsing lot file: {e}")

    raw_data["is_saved_to_db"] = False
    if parse_result:
        raw_data["parse_summary"] = parse_result.get("summary")
        raw_data["is_valid"] = parse_result.get("is_valid")
        raw_data["row_errors"] = parse_result.get("row_errors")
        raw_data["missing_mandatory_columns"] = parse_result.get("missing_mandatory_columns")

    lot = Lot.objects.create(
        file=file_obj,
        enquiry_status="pending",
        raw_data=raw_data
    )

    vendor_obj = None
    vendor_param = request.data.get("vendor_id") or request.data.get("user_id") or request.headers.get("X-Vendor-Id")
    if vendor_param:
        vendor_obj = _resolve_vendor_from_param(vendor_param)

    s_email = (vendor_obj.email if vendor_obj else (request.data.get("email") or request.data.get("user_email") or request.data.get("seller_email") or "")).strip()
    if not vendor_obj and s_email:
        vendor_obj = VendorDetails.objects.filter(email__iexact=s_email).first()

    if vendor_obj:
        lot.vendor = vendor_obj
        lot.save(update_fields=["vendor"])
        try:
            from AdminApp.services import create_vendor_notification
            create_vendor_notification(
                vendor=vendor_obj,
                title="Lot Manifest Uploaded",
                message=f"Batch '{lot.lot_number}' has been received and is pending admin review.",
                notification_type="LISTING",
                action_url="/profile"
            )
        except Exception as e:
            print(f"Error creating vendor lot notification: {e}")

    s_name = (vendor_obj.full_name or vendor_obj.company_name or vendor_obj.username) if vendor_obj else (request.data.get("name") or request.data.get("full_name") or "Valued Seller")

    # Send confirmation email to seller
    if s_email:
        try:
            from AdminApp.services import EmailService
            EmailService.send_lot_submitted_email(
                to_email=s_email,
                lot=lot,
                recipient_name=s_name
            )
        except Exception as e:
            print(f"Error sending seller lot submitted email: {e}")

    # Always notify admin via in-app alert and email
    try:
        from AdminApp.services import create_admin_notification, EmailService
        EmailService.notify_admin_lot_submitted(
            seller_info={
                "name": s_name,
                "email": s_email or "Unregistered / Guest"
            },
            lot=lot
        )
        create_admin_notification(
            title=f"New Lot Manifest Uploaded: {lot.lot_number}",
            message=f"Spreadsheet lot manifest '{lot.lot_number}' submitted by {s_name} ({len(products_list)} items).",
            notification_type="LISTING",
            action_url=f"/admin/enquiries/lots/{lot.id}/detail/"
        )
    except Exception as e:
        print(f"Error creating admin lot notification/emails: {e}")

    return Response({
        "success": True,
        "message": "Lot enquiry submitted successfully.",
        "enquiry": LotSerializer(lot).data,
        "batch_id": lot.lot_number,
        "created_at": lot.created_at.strftime("%Y-%m-%d %H:%M"),
        "products_extracted": len(products_list)
    }, status=status.HTTP_201_CREATED)



import json
import random
import uuid
import hashlib
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from AdminApp.models import VendorDetails, VendorOTP
from .serializers import (
    SendRegistrationOTPSerializer,
    VerifyOTPSerializer,
    SendLoginOTPSerializer,
    CompleteProfileSerializer,
    PartnershipEnquirySerializer,
    SellerProductEnquirySerializer,
    LotBatchEnquirySerializer
)

import secrets

def generate_otp():
    return str(secrets.SystemRandom().randint(100000, 999999))

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def send_registration_otp(request):
    try:
        close_old_connections()
        serializer = SendRegistrationOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
        data = serializer.validated_data
        email = data["email"].strip().lower()
    
        if VendorDetails.objects.filter(email=email).exists():
            return Response({"success": False, "message": "Email is already registered. Please login."}, status=status.HTTP_400_BAD_REQUEST)

        otp_code = generate_otp()
    
        VendorOTP.objects.create(
            email=email,
            otp=otp_code,
            registration_data=json.loads(json.dumps(data, default=str))
        )
    
        subject = "Surplus Market - Your Registration OTP Code"
        message = f"Hello,\n\nYour OTP for registration on Surplus Market is: {otp_code}.\n\nThis OTP is valid for 10 minutes. Please do not share this code with anyone.\n\nThank you,\nSurplus Market Team"
        try:
            html_message = render_to_string("emails/register_otp.html", {"otp_code": otp_code})
        except Exception:
            html_message = f"<h2>Surplus Market</h2><p>Your registration verification code: <strong>{otp_code}</strong></p>"
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Surplus Market <noreply@surplusmarket.com>')

        try:
            send_mail(
                subject=subject,
                message=message,
                html_message=html_message,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            print(f"--- REGISTRATION OTP SENT/CREATED FOR {email}: {otp_code} ---")
        except Exception as e:
            return Response({"success": False, "message": f"Email sending failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
        return Response({"success": True, "status": "otp_sent", "message": "OTP sent successfully."})
    except Exception as exc:
        print(f"send_registration_otp Exception: {exc}")
        return Response({"success": False, "message": f"Server error: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_registration_otp(request):
    serializer = VerifyOTPSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    email = serializer.validated_data["email"].strip().lower()
    otp_code = serializer.validated_data["otp"]
    
    otp_record = VendorOTP.objects.filter(email=email, otp=otp_code, is_used=False).order_by("-created_at").first()
    
    if not otp_record or not otp_record.is_valid():
        return Response({"success": False, "message": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
    
    # Create the VendorDetails
    reg_data = otp_record.registration_data
    if not reg_data:
        return Response({"success": False, "message": "Registration data not found."}, status=status.HTTP_400_BAD_REQUEST)
    
    username = email.split("@")[0] + "_" + str(secrets.SystemRandom().randint(1000, 9999))
    
    vendor = VendorDetails.objects.create(
        username=username,
        full_name=reg_data.get("full_name") or "",
        email=email,
        mobile_number=reg_data.get("mobile_number") or "",
        country=reg_data.get("country") or "United Arab Emirates",
        company_name=reg_data.get("company_name") or "",
        business_location=reg_data.get("business_location") or "",
        category_interested=reg_data.get("category_interested") or "",
        user_type=reg_data.get("user_type") or "BUYER",
        status=True
    )
    
    # Trigger notifications: Admin in-app alert, Admin email, User welcome email, User in-app notification
    try:
        from AdminApp.services import notify_new_user_registration
        notify_new_user_registration(vendor)
    except Exception as notif_err:
        logger.error(f"Error triggering registration notifications for vendor {vendor.id}: {notif_err}")
    
    # We do NOT mark the OTP as used here because the frontend will immediately 
    # use this same OTP to call /api/auth/login/verify-otp/ to generate the auth session.
    # The login verify endpoint will mark it as used.
    # otp_record.is_used = True
    # otp_record.vendor = vendor
    # otp_record.save()
    
    return Response({
        "success": True, 
        "status": "verified", 
        "message": "OTP verified successfully. Proceed to complete profile.",
        "vendor_id": vendor.vendor_id,
        "raw_vendor_id": vendor.id,
        "email": vendor.email,
        "username": vendor.username,
        "full_name": vendor.full_name,
        "account_entity_type": vendor.account_entity_type,
        "company_name": vendor.company_name,
        "user_type": vendor.user_type,
        "mobile_number": vendor.mobile_number,
        "country": getattr(vendor, "country", ""),
        "business_location": vendor.business_location,
    })


@csrf_exempt
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def complete_profile(request):
    if request.method == "GET":
        email = (request.query_params.get("email") or request.query_params.get("user") or "").strip().lower()
        if not email:
            return Response({"success": False, "message": "Email parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        vendor = VendorDetails.objects.filter(email=email).first()
        if not vendor and email.upper().startswith("USR-"):
            clean_uid = email[4:].strip()
            if clean_uid.isdigit():
                vendor = VendorDetails.objects.filter(id=int(clean_uid)).first()
        if not vendor:
            return Response({"success": False, "message": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        prof_info = vendor.get_profile_completion_details()
        return Response({
            "success": True, 
            "status": "profile_found", 
            "message": "Profile fetched successfully.",
            "vendor_id": vendor.vendor_id,
            "raw_vendor_id": vendor.id,
            "email": vendor.email,
            "username": vendor.username,
            "full_name": vendor.full_name,
            "account_entity_type": vendor.account_entity_type,
            "company_name": vendor.company_name,
            "user_type": vendor.user_type,
            "mobile_number": vendor.mobile_number,
            "country": getattr(vendor, "country", ""),
            "business_location": vendor.business_location,
            "business_address": vendor.business_address,
            "tax_registration_number": vendor.tax_registration_number,
            "business_type": vendor.business_type,
            "category_interested": vendor.category_interested_list,
            "profile_completion_percentage": prof_info["percentage"],
            "is_profile_complete": prof_info["is_complete"],
            "profile_completion": prof_info
        })
    serializer = CompleteProfileSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    email = data["email"].strip().lower()
    
    vendor = VendorDetails.objects.filter(email=email).first()
    if not vendor:
        return Response({"success": False, "message": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        
    if "full_name" in data and data["full_name"]:
        vendor.full_name = data["full_name"].strip()
    elif "full_name" in request.data and str(request.data["full_name"]).strip():
        vendor.full_name = str(request.data["full_name"]).strip()

    if "mobile_number" in data and data["mobile_number"]:
        vendor.mobile_number = data["mobile_number"].strip()
    elif "mobile_number" in request.data and str(request.data["mobile_number"]).strip():
        vendor.mobile_number = str(request.data["mobile_number"]).strip()

    if "user_type" in data:
        vendor.user_type = data["user_type"]

    country_val = str(
        data.get("country")
        or request.data.get("country")
        or request.data.get("countryName")
        or request.data.get("country_name")
        or ""
    ).strip()
    if country_val:
        vendor.country = country_val
    elif not getattr(vendor, "country", None):
        vendor.country = "United Arab Emirates"

    if "account_entity_type" in data:
        vendor.account_entity_type = data["account_entity_type"]
        vendor.company_name = str(data.get("company_name") or request.data.get("company_name") or "").strip()
    elif "company_name" in data or "company_name" in request.data:
        vendor.company_name = str(data.get("company_name") or request.data.get("company_name") or "").strip()
        
    loc_val = str(
        data.get("business_location")
        or request.data.get("business_location")
        or request.data.get("businessLocation")
        or request.data.get("location")
        or ""
    ).strip()
    if loc_val:
        vendor.business_location = loc_val
    
    if "business_address" in data:
        vendor.business_address = data["business_address"]
    if "tax_registration_number" in data:
        vendor.tax_registration_number = data["tax_registration_number"]
    if "business_type" in data:
        vendor.business_type = data["business_type"]
    
    cat_inst = data.get("category_interested", [])
    if isinstance(cat_inst, str):
        val = cat_inst.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                import json
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    cat_inst = parsed
                else:
                    cat_inst = [c.strip() for c in str(parsed).split(",") if c.strip()]
            except Exception:
                cat_inst = [c.strip().strip("'\"[]") for c in val.split(",") if c.strip().strip("'\"[]")]
        else:
            cat_inst = [c.strip() for c in val.split(",") if c.strip()]
    elif isinstance(cat_inst, list):
        cat_inst = [str(c).strip().strip("'\"[]") for c in cat_inst if str(c).strip().strip("'\"[]")]

    if not cat_inst or len(cat_inst) < 1:
        return Response({"success": False, "message": "Please select at least 1 interested category."}, status=status.HTTP_400_BAD_REQUEST)
    if len(cat_inst) > 3:
        return Response({"success": False, "message": "You can select a maximum of 3 interested categories."}, status=status.HTTP_400_BAD_REQUEST)
    vendor.category_interested = cat_inst
    
    vendor.save()

    prof_info = vendor.get_profile_completion_details()
    activated_products_count = 0
    activated_lots_count = 0
    if prof_info["is_complete"]:
        from AdminApp.models import Product, Lot
        activated_products_count = Product.objects.filter(
            vendor=vendor,
            enquiry_status__iexact="APPROVED",
            is_active=False
        ).update(is_active=True)

        activated_lots_count = Lot.objects.filter(
            vendor=vendor,
            enquiry_status__iexact="approved",
            is_active=False
        ).update(is_active=True, active_status="active")

        total_activated = activated_products_count + activated_lots_count
        if total_activated > 0:
            try:
                from AdminApp.services import create_vendor_notification
                create_vendor_notification(
                    vendor=vendor,
                    title="Profile Completed - Listings Published!",
                    message=f"Congratulations! Your profile is 100% complete and {total_activated} approved listing(s) have now been published live to the marketplace.",
                    notification_type="LISTING",
                    action_url="/profile"
                )
            except Exception:
                pass

        try:
            from AdminApp.services import create_admin_notification
            create_admin_notification(
                title=f"User Profile Completed: {vendor.full_name or vendor.username}",
                message=f"{vendor.full_name or vendor.username} ({vendor.vendor_id}) completed 100% of profile details.",
                notification_type="USER_REGISTRATION",
                action_url=f"/admin/users/?q={vendor.email}",
                for_superadmins_only=False
            )
        except Exception:
            pass
    
    return Response({
        "success": True, 
        "status": "profile_completed", 
        "message": "Profile completed successfully.",
        "vendor_id": vendor.vendor_id,
        "raw_vendor_id": vendor.id,
        "email": vendor.email,
        "username": vendor.username,
        "full_name": vendor.full_name,
        "account_entity_type": vendor.account_entity_type,
        "company_name": vendor.company_name,
        "user_type": vendor.user_type,
        "mobile_number": vendor.mobile_number,
        "country": getattr(vendor, "country", ""),
        "business_location": vendor.business_location,
        "business_address": vendor.business_address,
        "tax_registration_number": vendor.tax_registration_number,
        "business_type": vendor.business_type,
        "category_interested": vendor.category_interested_list,
        "profile_completion_percentage": prof_info["percentage"],
        "is_profile_complete": prof_info["is_complete"],
        "profile_completion": prof_info,
        "activated_products_count": activated_products_count
    })


@csrf_exempt
@api_view(["POST"])
@permission_classes([AllowAny])
def send_login_otp(request):
    try:
        close_old_connections()
        serializer = SendLoginOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        email_or_user = serializer.validated_data["email"].strip()
        
        vendor = VendorDetails.objects.filter(email__iexact=email_or_user).first()
        if not vendor and email_or_user.upper().startswith("USR-"):
            clean_uid = email_or_user[4:].strip()
            if clean_uid.isdigit():
                vendor = VendorDetails.objects.filter(id=int(clean_uid)).first()
        if not vendor:
            vendor = VendorDetails.objects.filter(username__iexact=email_or_user).first()

        if not vendor:
            return Response({"success": False, "message": "No account found with this identifier."}, status=status.HTTP_404_NOT_FOUND)
            
        email = vendor.email
        otp_code = generate_otp()
        
        VendorOTP.objects.create(
            email=email,
            otp=otp_code,
            vendor=vendor
        )
        
        subject = "Surplus Market - Your Login Security Code"
        message = f"Hello,\n\nYour OTP to log in to Surplus Market is: {otp_code}.\n\nThis OTP is valid for 10 minutes. Please do not share this code with anyone.\n\nThank you,\nSurplus Market Team"
        try:
            html_message = render_to_string("emails/login_otp.html", {"otp_code": otp_code})
        except Exception:
            html_message = f"<h2>Surplus Market</h2><p>Your login security code: <strong>{otp_code}</strong></p>"
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Surplus Market <noreply@surplusmarket.com>')

        try:
            send_mail(
                subject=subject,
                message=message,
                html_message=html_message,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=True,
            )
            print(f"--- LOGIN OTP SENT/CREATED FOR {email}: {otp_code} ---")
        except Exception as e:
            print(f"FAILED TO DISPATCH LOGIN OTP EMAIL TO {email}: {e}")
        
        return Response({"success": True, "status": "otp_sent", "message": "OTP sent successfully."})
    except Exception as exc:
        print(f"send_login_otp Exception: {exc}")
        return Response({"success": False, "message": f"Server error: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([AllowAny])
def verify_login_otp(request):
    serializer = VerifyOTPSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    email = serializer.validated_data["email"].strip().lower()
    otp_code = serializer.validated_data["otp"]
    
    otp_record = VendorOTP.objects.filter(email=email, otp=otp_code, is_used=False).order_by("-created_at").first()
    
    if not otp_record or not otp_record.is_valid():
        return Response({"success": False, "message": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
    
    vendor = VendorDetails.objects.filter(email=email).first()
    if not vendor:
        return Response({"success": False, "message": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        
    otp_record.is_used = True
    otp_record.save()
    
    return Response({
        "success": True,
        "status": "verified", 
        "message": "Login successful.",
        "vendor_id": vendor.vendor_id,
        "raw_vendor_id": vendor.id,
        "email": vendor.email,
        "username": vendor.username,
        "full_name": vendor.full_name,
        "account_entity_type": vendor.account_entity_type,
        "company_name": vendor.company_name,
        "user_type": vendor.user_type,
        "mobile_number": vendor.mobile_number,
        "country": getattr(vendor, "country", ""),
        "business_location": vendor.business_location,
        "business_address": vendor.business_address,
        "tax_registration_number": vendor.tax_registration_number,
        "business_type": vendor.business_type,
        "category_interested": vendor.category_interested_list
    })


from .serializers import PartnershipEnquirySerializer, ContactUsEnquirySerializer
@api_view(["POST"])
@permission_classes([AllowAny])
def submit_partnership_enquiry(request):
    payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
    
    # Map frontend field names to model field names if provided
    if "location" in payload and "business_location" not in payload:
        payload["business_location"] = payload.pop("location")
    if "interest" in payload and "partnership_interest" not in payload:
        payload["partnership_interest"] = payload.pop("interest")
    if "message" in payload and "collaboration_details" not in payload:
        payload["collaboration_details"] = payload.pop("message")

    serializer = PartnershipEnquirySerializer(data=payload)
    if serializer.is_valid():
        enquiry = serializer.save()

        # In-app Admin Notification
        try:
            from AdminApp.services import create_admin_notification
            create_admin_notification(
                title=f"New Partnership Proposal - {enquiry.name}",
                message=f"Received a partnership proposal ({enquiry.partnership_interest or 'Strategic Partnership'}) from {enquiry.name} ({enquiry.email}) in {enquiry.business_location or 'N/A'}.",
                notification_type="ENQUIRY",
                action_url="/admin/enquiries/partnership/"
            )
        except Exception as e:
            logger.error(f"[submit_partnership_enquiry] Admin notification error: {e}")

        # In-app Vendor Notification (if registered vendor)
        try:
            vendor_match = VendorDetails.objects.filter(email__iexact=enquiry.email).first()
            if vendor_match:
                from AdminApp.services import create_vendor_notification
                create_vendor_notification(
                    vendor=vendor_match,
                    title="Partnership Proposal Received",
                    message=f"Thank you for submitting your partnership proposal ({enquiry.partnership_interest or 'Strategic Partnership'}). Our team is reviewing it.",
                    notification_type="SYSTEM",
                    action_url="/profile"
                )
        except Exception as e:
            logger.error(f"[submit_partnership_enquiry] Vendor notification error: {e}")

        # Email Notifications (Admin Alert + Partner Confirmation)
        try:
            from AdminApp.services import EmailService
            EmailService.send_partnership_emails(enquiry)
        except Exception as e:
            logger.error(f"[submit_partnership_enquiry] Email dispatch error: {e}")

        return Response({
            "success": True, 
            "message": "Partnership enquiry submitted successfully. We will get back to you soon.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def submit_contact_us_enquiry(request):
    """
    Public API endpoint to submit a Contact Us / General Enquiry from the frontend.
    Accepts: fullName/full_name, email, phone/contactNo, enquiryType/enquiry_type, message
    """
    payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)

    # Normalize incoming field names to model field names
    if "fullName" in payload and "full_name" not in payload:
        payload["full_name"] = payload.get("fullName")
    elif "name" in payload and "full_name" not in payload:
        payload["full_name"] = payload.get("name")

    if "enquiryType" in payload and "enquiry_type" not in payload:
        payload["enquiry_type"] = payload.get("enquiryType")
    elif "type" in payload and "enquiry_type" not in payload:
        payload["enquiry_type"] = payload.get("type")

    if "contactNo" in payload and "phone" not in payload:
        payload["phone"] = payload.get("contactNo")
    elif "mobile" in payload and "phone" not in payload:
        payload["phone"] = payload.get("mobile")

    serializer = ContactUsEnquirySerializer(data=payload)
    if serializer.is_valid():
        enquiry = serializer.save()

        # In-app Admin Notification
        try:
            from AdminApp.services import create_admin_notification
            create_admin_notification(
                title=f"New Contact Enquiry - {enquiry.full_name}",
                message=f"Received a new {enquiry.enquiry_type or 'General'} inquiry from {enquiry.full_name} ({enquiry.email}).",
                notification_type="ENQUIRY",
                action_url="/admin/enquiries/contact-us/"
            )
        except Exception as e:
            logger.error(f"[submit_contact_us_enquiry] Admin notification error: {e}")

        # In-app Vendor Notification (if registered vendor)
        try:
            vendor_match = VendorDetails.objects.filter(email__iexact=enquiry.email).first()
            if vendor_match:
                from AdminApp.services import create_vendor_notification
                create_vendor_notification(
                    vendor=vendor_match,
                    title="Enquiry Received",
                    message=f"Thank you for contacting us regarding {enquiry.enquiry_type or 'General Inquiry'}. Our support team will review your message shortly.",
                    notification_type="SYSTEM",
                    action_url="/profile"
                )
        except Exception as e:
            logger.error(f"[submit_contact_us_enquiry] Vendor notification error: {e}")

        # Email Notifications (Admin Alert + User Confirmation)
        try:
            from AdminApp.services import EmailService
            EmailService.send_contact_us_emails(enquiry)
        except Exception as e:
            logger.error(f"[submit_contact_us_enquiry] Email dispatch error: {e}")

        return Response({
            "success": True,
            "message": "Contact enquiry submitted successfully. Thank you for reaching out!",
            "data": {
                "id": enquiry.id,
                "fullName": enquiry.full_name,
                "email": enquiry.email,
                "phone": enquiry.phone,
                "enquiryType": enquiry.enquiry_type,
                "message": enquiry.message,
                "createdAt": enquiry.created_at.isoformat() if enquiry.created_at else None
            }
        }, status=status.HTTP_201_CREATED)

    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
def submit_rfq_enquiry(request):
    """
    Public REST API endpoint to submit a Buyer Request For Quotation (RFQ) from the frontend cart.
    Endpoint: POST /api/enquiries/rfq/
    """
    from AdminApp.models import RfqEnquiry, RfqEnquiryItem, VendorDetails, Product, Lot
    from AdminApp.services import create_admin_notification, create_vendor_notification
    from .serializers import RfqEnquirySerializer
    from django.db import transaction
    from decimal import Decimal, InvalidOperation

    if request.method == "GET":
        ref = request.GET.get("reference", "").strip()
        if ref:
            rfq = RfqEnquiry.objects.prefetch_related("items").filter(reference__iexact=ref).first()
            if not rfq:
                return Response({"success": False, "message": f"RFQ '{ref}' not found."}, status=status.HTTP_404_NOT_FOUND)
            return Response({"success": True, "data": RfqEnquirySerializer(rfq).data}, status=status.HTTP_200_OK)

        email = (request.GET.get("email") or "").strip().lower()
        vendor_param = request.GET.get("vendor_id") or request.GET.get("vendor") or request.GET.get("user_id")
        if email or vendor_param:
            from django.db.models import Q
            qs = RfqEnquiry.objects.prefetch_related("items").all().order_by("-created_at")
            q_filter = Q()
            if email:
                q_filter |= Q(email__iexact=email)
            if vendor_param:
                vendor_obj = _resolve_vendor_from_param(vendor_param)
                if vendor_obj:
                    q_filter |= Q(buyer=vendor_obj)
            qs = qs.filter(q_filter)
            return Response({"success": True, "data": RfqEnquirySerializer(qs, many=True).data}, status=status.HTTP_200_OK)

        return Response({"success": True, "message": "RFQ endpoint is active. Use POST to submit requests."}, status=status.HTTP_200_OK)

    payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)

    contact_person = (payload.get("contact_person") or payload.get("contactPerson") or payload.get("fullName") or payload.get("name") or "").strip()
    company_name = (payload.get("company_name") or payload.get("companyName") or "").strip()
    email = (payload.get("email") or "").strip().lower()

    if not email:
        return Response({"success": False, "message": "Email address is required."}, status=status.HTTP_400_BAD_REQUEST)

    phone = str(payload.get("phone") or payload.get("contactNo") or payload.get("mobile") or "").strip()
    country = str(payload.get("country") or "").strip()
    business_location = str(payload.get("business_location") or payload.get("businessLocation") or payload.get("location") or "").strip()
    destination_port = str(payload.get("destination_port") or payload.get("destinationPort") or "").strip()
    incoterm = str(payload.get("incoterm") or "EXW").strip().upper()
    payment_method = str(payload.get("payment_method") or payload.get("paymentMethod") or "Escrow").strip()
    additional_notes = str(payload.get("additional_notes") or payload.get("additionalNotes") or payload.get("notes") or "").strip()
    currency = str(payload.get("currency") or "USD").strip().upper()

    ref = str(payload.get("reference") or "").strip()
    current_year = timezone.now().year
    if not ref or not ref.upper().startswith("RFQ-"):
        ref = f"RFQ-{current_year}-{random.randint(100000, 999999)}"

    while RfqEnquiry.objects.filter(reference=ref).exists():
        ref = f"RFQ-{current_year}-{random.randint(100000, 999999)}"

    try:
        raw_units = payload.get("total_units") or payload.get("totalUnits") or 0
        total_units = int(raw_units)
    except (ValueError, TypeError):
        total_units = 0

    try:
        raw_val = payload.get("estimated_value") or payload.get("estimatedValue") or 0
        estimated_value = Decimal(str(raw_val))
    except (InvalidOperation, ValueError, TypeError):
        estimated_value = Decimal("0.00")

    buyer_vendor = None
    buyer_param = payload.get("vendor_id") or payload.get("user_id") or request.headers.get("X-Vendor-Id")
    if buyer_param:
        buyer_vendor = _resolve_vendor_from_param(buyer_param)
    if not buyer_vendor:
        buyer_vendor = VendorDetails.objects.filter(email__iexact=email).first()

    if not contact_person:
        if buyer_vendor and buyer_vendor.full_name:
            contact_person = buyer_vendor.full_name.strip()
        elif company_name and company_name.lower() not in ["individual", "individual buyer", "n/a", "none"]:
            contact_person = company_name
        else:
            contact_person = email.split("@")[0]

    # Clean company_name: avoid personal name or placeholder being recorded as company
    if company_name.lower() in [contact_person.lower(), "individual", "individual buyer", "n/a", "none"]:
        company_name = ""

    # Check buyer_vendor profile if company_name was not provided
    if not company_name and buyer_vendor and getattr(buyer_vendor, "company_name", None):
        saved_comp = buyer_vendor.company_name.strip()
        if saved_comp.lower() not in [contact_person.lower(), "individual", "individual buyer", "n/a", "none"]:
            company_name = saved_comp

    if not country and buyer_vendor and getattr(buyer_vendor, "country", None):
        country = buyer_vendor.country
    if not business_location and buyer_vendor and getattr(buyer_vendor, "business_location", None):
        business_location = buyer_vendor.business_location

    raw_items = payload.get("items") or []
    if isinstance(raw_items, str):
        try:
            raw_items = json.loads(raw_items)
        except Exception:
            raw_items = []

    with transaction.atomic():
        rfq = RfqEnquiry.objects.create(
            reference=ref,
            buyer=buyer_vendor,
            contact_person=contact_person,
            company_name=company_name,
            email=email,
            phone=phone,
            country=country,
            business_location=business_location,
            destination_port=destination_port,
            incoterm=incoterm,
            payment_method=payment_method,
            additional_notes=additional_notes,
            total_units=total_units,
            estimated_value=estimated_value,
            currency=currency,
            status="PENDING",
        )

        item_count = 0
        calc_units = 0
        calc_val = Decimal("0.00")

        for it in raw_items:
            if not isinstance(it, dict):
                continue
            item_title = str(it.get("title") or it.get("product_name") or it.get("name") or "Quotation Item").strip()
            item_sku = str(it.get("sku") or it.get("model_no") or "").strip()
            item_cat = str(it.get("category") or "").strip()
            item_type = str(it.get("type") or "product").strip().lower()

            try:
                qty = int(it.get("quantity") or 1)
            except (ValueError, TypeError):
                qty = 1

            try:
                u_price = Decimal(str(it.get("unit_price") or it.get("unitPrice") or it.get("price") or 0))
            except (InvalidOperation, ValueError, TypeError):
                u_price = Decimal("0.00")

            t_price = None
            if it.get("target_price") or it.get("targetPrice"):
                try:
                    t_price = Decimal(str(it.get("target_price") or it.get("targetPrice")))
                except (InvalidOperation, ValueError, TypeError):
                    t_price = None

            notes = str(it.get("notes") or "").strip()

            prod_id_raw = it.get("productId") or it.get("product_id") or it.get("id")
            linked_product = None
            linked_lot = None

            if item_type == "lot":
                if prod_id_raw:
                    lot_str = str(prod_id_raw).strip()
                    if lot_str.isdigit():
                        linked_lot = Lot.objects.filter(id=int(lot_str)).first()
                    elif lot_str.upper().startswith("LOT-") or lot_str.upper().startswith("BAT-"):
                        linked_lot = Lot.objects.filter(batch_id__iexact=lot_str).first()
                if linked_lot and (not item_title or item_title == "Quotation Item"):
                    item_title = linked_lot.title or getattr(linked_lot, "product_name", "") or f"Lot {linked_lot.batch_id}"
                if linked_lot and not item_sku:
                    item_sku = getattr(linked_lot, "batch_id", "") or ""
            else:
                if prod_id_raw:
                    p_str = str(prod_id_raw).strip()
                    if p_str.isdigit():
                        linked_product = Product.objects.filter(id=int(p_str)).first()
                    elif p_str.upper().startswith("PRO-"):
                        linked_product = Product.objects.filter(product_id__iexact=p_str).first()
                if linked_product and (not item_title or item_title == "Quotation Item"):
                    item_title = linked_product.title or getattr(linked_product, "name", "") or f"Product {linked_product.product_id}"
                if linked_product and not item_sku:
                    item_sku = getattr(linked_product, "sku", "") or getattr(linked_product, "product_id", "") or ""

            RfqEnquiryItem.objects.create(
                rfq=rfq,
                product=linked_product,
                lot=linked_lot,
                item_type=item_type,
                title=item_title,
                sku=item_sku,
                category=item_cat,
                quantity=qty,
                unit_price=u_price,
                target_price=t_price,
                notes=notes,
            )

            item_count += 1
            calc_units += qty
            calc_val += (u_price * qty)

        if total_units == 0 and calc_units > 0:
            rfq.total_units = calc_units
        if estimated_value == Decimal("0.00") and calc_val > Decimal("0.00"):
            rfq.estimated_value = calc_val
        rfq.save(update_fields=["total_units", "estimated_value"])

    try:
        company_label = f" - {rfq.company_name}" if rfq.company_name else f" - {rfq.contact_person}"
        create_admin_notification(
            title=f"New Buyer RFQ {rfq.reference}{company_label}",
            message=f"Buyer {contact_person} ({email}) submitted a consolidated RFQ for {item_count} items ({rfq.total_units} units, est. {rfq.currency} {rfq.estimated_value:,.2f}).",
            notification_type="RFQ",
            action_url=f"/admin/rfq-requests/{rfq.id}/detail/"
        )
        from AdminApp.services import EmailService
        EmailService.notify_admin_rfq_submitted(
            buyer_info={
                "name": contact_person,
                "email": email,
                "phone": phone,
                "company_name": company_name,
                "reference": rfq.reference,
                "total_units": rfq.total_units,
                "estimated_value": rfq.estimated_value,
                "currency": rfq.currency,
            },
            items_list=rfq.items.all(),
            rfq=rfq
        )
    except Exception as e:
        print(f"[submit_rfq_enquiry] Admin notification/email error: {e}")

    if buyer_vendor:
        try:
            create_vendor_notification(
                vendor=buyer_vendor,
                title=f"Quotation Request {rfq.reference} Received",
                message=f"Your consolidated RFQ for {rfq.total_units} units has been submitted. Our commercial team will prepare your proforma quotation.",
                notification_type="RFQ",
                action_url="/profile"
            )
        except Exception as e:
            print(f"[submit_rfq_enquiry] Vendor notification error: {e}")

    # 3. Buyer Confirmation Email
    try:
        from AdminApp.services import EmailService
        EmailService.send_rfq_buyer_confirmation(
            to_email=email,
            rfq=rfq,
            items_list=rfq.items.all(),
            recipient_name=contact_person
        )
    except Exception as e:
        print(f"[submit_rfq_enquiry] Buyer email delivery error: {e}")

    return Response({
        "success": True,
        "message": f"Official RFQ '{rfq.reference}' submitted successfully. Our commercial representative will contact {email} within 12 business hours.",
        "data": {
            "id": rfq.id,
            "reference": rfq.reference,
            "companyName": rfq.company_name,
            "contactPerson": rfq.contact_person,
            "email": rfq.email,
            "itemsCount": item_count,
            "totalUnits": rfq.total_units,
            "estimatedValue": float(rfq.estimated_value),
            "currency": rfq.currency,
            "status": rfq.status,
            "createdAt": rfq.created_at.isoformat() if rfq.created_at else None,
        }
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def submit_product_request(request):
    """
    Endpoint for frontend single product submissions.
    Accepts direct vendor_id without requiring user session authentication.
    Resolves category and sub_category strings to foreign keys, creates Product,
    links gallery images, and sets enquiry_status='PENDING'.
    """
    import json
    from decimal import Decimal
    from django.utils.dateparse import parse_date
    from django.utils.text import slugify
    from django.core.files.storage import default_storage
    from AdminApp.models import Product, ProductImage, MainCategory, SubCategory, VendorDetails

    data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)

    # 1. Vendor resolution directly from user_id / vendor_id (supports USR-xxxx, integer, email, username)
    vendor = None
    vendor_id = (
        data.get('user_id') or 
        data.get('userId') or 
        data.get('vendor_id') or 
        data.get('vendorId') or 
        data.get('vendor') or 
        data.get('user') or 
        data.get('seller_id') or 
        data.get('sellerId') or 
        data.get('seller')
    )

    if not vendor_id:
        for ukey in ('user_information', 'user_info', 'userInfo', 'user_data', 'userData', 'raw_data'):
            if ukey in data:
                uval = data[ukey]
                if isinstance(uval, str):
                    try:
                        uval = json.loads(uval)
                    except Exception:
                        uval = {}
                if isinstance(uval, dict):
                    vendor_id = (
                        uval.get('vendor_id') or 
                        uval.get('vendorId') or 
                        uval.get('user_id') or 
                        uval.get('userId') or 
                        uval.get('id') or 
                        uval.get('email')
                    )
                    if vendor_id:
                        break

    if not vendor_id:
        vendor_id = (
            request.headers.get('X-Vendor-Id') or 
            request.headers.get('X-User-Id') or 
            request.headers.get('Vendor-Id') or 
            request.headers.get('User-Id')
        )

    if not vendor_id:
        vendor_id = request.session.get('vendor_id') or request.session.get('user_id')

    if not vendor_id and getattr(request, 'user', None) and request.user.is_authenticated:
        vendor_id = request.user.email

    if not vendor_id:
        vendor_id = data.get('email') or data.get('user_email') or data.get('vendor_email')

    if vendor_id is not None and str(vendor_id).strip() != "":
        vid_str = str(vendor_id).strip()
        clean_vid = vid_str[4:].strip() if vid_str.upper().startswith("USR-") else vid_str
        
        # Look up by integer ID
        if clean_vid.isdigit():
            vendor = VendorDetails.objects.filter(id=int(clean_vid)).first()

        # Look up by email
        if not vendor:
            vendor = VendorDetails.objects.filter(email__iexact=vid_str).first()
            
        # Look up by username
        if not vendor:
            vendor = VendorDetails.objects.filter(username__iexact=vid_str).first()

    # Never fall back to arbitrary vendors; if no vendor matched, vendor remains None

    # 2. Product Name
    product_name = (data.get('product_name') or data.get('title') or '').strip()
    if not product_name:
        return Response({
            "success": False,
            "errors": {"product_name": ["Product name is required."]}
        }, status=status.HTTP_400_BAD_REQUEST)

    # 3. Category & Subcategory resolution
    category_obj = None
    category_val = data.get('category') or data.get('category_name') or data.get('main_category')
    if category_val is not None:
        if isinstance(category_val, int) or (isinstance(category_val, str) and category_val.strip().isdigit()):
            category_obj = MainCategory.objects.filter(id=int(category_val)).first()
        if not category_obj and isinstance(category_val, str) and category_val.strip():
            cat_name = category_val.strip()
            category_obj = MainCategory.objects.filter(name__iexact=cat_name).first()
            if not category_obj:
                slug = slugify(cat_name) or "category"
                category_obj, _ = MainCategory.objects.get_or_create(
                    name=cat_name,
                    defaults={'slug': slug, 'is_active': True}
                )

    subcategory_obj = None
    subcat_val = data.get('sub_category') or data.get('subcategory') or data.get('sub_category_name')
    if subcat_val is not None:
        if isinstance(subcat_val, int) or (isinstance(subcat_val, str) and subcat_val.strip().isdigit()):
            subcategory_obj = SubCategory.objects.filter(id=int(subcat_val)).first()
        if not subcategory_obj and isinstance(subcat_val, str) and subcat_val.strip():
            sub_name = subcat_val.strip()
            sub_query = SubCategory.objects.filter(name__iexact=sub_name)
            if category_obj:
                sub_query = sub_query.filter(main_category=category_obj)
            subcategory_obj = sub_query.first()
            if not subcategory_obj and category_obj:
                sub_slug = slugify(f"{category_obj.slug}-{sub_name}") or "sub-category"
                subcategory_obj, _ = SubCategory.objects.get_or_create(
                    main_category=category_obj,
                    name=sub_name,
                    defaults={'slug': sub_slug, 'is_active': True}
                )

    if subcategory_obj and not category_obj:
        category_obj = subcategory_obj.main_category

    # 4. Brand & Model
    brand_name = (data.get('brand_name') or data.get('brand') or data.get('brandName') or '').strip()
    model_no = (
        data.get('model_no') or 
        data.get('modelNo') or 
        data.get('model_part_no') or 
        data.get('modelPartNo') or 
        data.get('sku') or ''
    ).strip()

    # 5. Manufacturing Country, Inventory Country & Inventory Location
    inventory_country = (
        data.get('inventory_country') or 
        data.get('inventoryCountry') or 
        data.get('country') or ''
    ).strip()
    manufacturing_country = (
        data.get('manufacturing_country') or 
        data.get('manufacturingCountry') or ''
    ).strip()

    inventory_location = (
        data.get('inventory_location') or 
        data.get('inventoryLocation') or 
        data.get('location') or 
        data.get('warehouse_location') or 
        data.get('stock_location') or ''
    ).strip()

    # 6. Manufacturing Year
    manufacturing_year = None
    year_val = data.get('manufacturing_year') or data.get('year')
    if year_val is not None and str(year_val).strip():
        try:
            manufacturing_year = int(str(year_val).strip())
        except (ValueError, TypeError):
            manufacturing_year = None

    # 7. Dimensions
    dimensions = str(data.get('dimensions') or '').strip()

    # 8. Expiry Date
    expiry_date = None
    expiry_val = data.get('expiry') or data.get('expiry_date')
    if expiry_val:
        try:
            expiry_date = parse_date(str(expiry_val).strip())
        except Exception:
            expiry_date = None

    # 9. Excluded Countries
    excluded_countries = data.get('excluded_countries') or data.get('excludedCountries') or []
    if isinstance(excluded_countries, str):
        try:
            excluded_countries = json.loads(excluded_countries)
        except Exception:
            excluded_countries = [c.strip() for c in excluded_countries.split(',') if c.strip()]
    if not isinstance(excluded_countries, list):
        excluded_countries = []

    # 10. Quantity, Currency & Pricing
    qty_val = data.get('quantity') or data.get('stock_quantity') or 0
    try:
        quantity = max(0, int(str(qty_val).strip()))
    except (ValueError, TypeError):
        quantity = 0

    currency = str(data.get('currency') or 'USD').strip().upper()

    lp_val = (
        data.get('liquidating_price') or 
        data.get('liquidation_price') or 
        data.get('liquidatingPrice') or 
        data.get('liquidationPrice') or 
        data.get('price') or 0
    )
    try:
        liquidating_price = Decimal(str(lp_val).strip())
    except Exception:
        liquidating_price = Decimal("0.00")

    msrp = None
    msrp_val = data.get('msrp') or data.get('MSRP') or data.get('previousPrice') or data.get('previous_price') or data.get('originalPrice')
    if msrp_val is not None and str(msrp_val).strip() != "":
        try:
            msrp = Decimal(str(msrp_val).strip())
        except Exception:
            msrp = None

    offer = Decimal("0.00")
    offer_val = (
        data.get('offer') or 
        data.get('offer_percentage') or 
        data.get('offerPercentage') or 
        data.get('discount') or 
        data.get('discount_percentage') or 
        data.get('discountPercentage')
    )
    if offer_val is not None and str(offer_val).strip() != "":
        try:
            offer = Decimal(str(offer_val).strip())
        except Exception:
            offer = Decimal("0.00")

    # 11. Description & Reason to Sell
    description = str(data.get('description') or '').strip()
    reason_to_sell = str(data.get('reason_to_sell') or data.get('reasonToSell') or '').strip()

    # 12. Warranty & Documents
    warranty = str(data.get('warranty') or '').strip()
    warranty_attachment = str(data.get('warranty_document') or data.get('warranty_attachment') or data.get('warrantyAttachment') or '').strip()
    if 'warranty_document' in request.FILES:
        w_file = request.FILES['warranty_document']
        saved_path = default_storage.save(f"products/documents/{w_file.name}", w_file)
        warranty_attachment = default_storage.url(saved_path)
    elif 'warranty_attachment' in request.FILES:
        w_file = request.FILES['warranty_attachment']
        saved_path = default_storage.save(f"products/documents/{w_file.name}", w_file)
        warranty_attachment = default_storage.url(saved_path)

    # 13. Certificate & Documents
    cert_val = data.get('certificate') if 'certificate' in data else (
        data.get('third_party_certificate') if 'third_party_certificate' in data else data.get('thirdPartyCertificate')
    )
    if isinstance(cert_val, bool):
        third_party_certificate = cert_val
    elif isinstance(cert_val, str):
        third_party_certificate = cert_val.strip().lower() in ('true', '1', 'yes', 't')
    else:
        third_party_certificate = bool(cert_val)

    third_party_documents = str(
        data.get('certificate_document') or 
        data.get('third_party_documents') or 
        data.get('thirdPartyDocuments') or ''
    ).strip()
    if 'certificate_document' in request.FILES:
        c_file = request.FILES['certificate_document']
        saved_path = default_storage.save(f"products/documents/{c_file.name}", c_file)
        third_party_documents = default_storage.url(saved_path)
    elif 'third_party_documents' in request.FILES:
        c_file = request.FILES['third_party_documents']
        saved_path = default_storage.save(f"products/documents/{c_file.name}", c_file)
        third_party_documents = default_storage.url(saved_path)

    # 14. Create Product record
    product = Product.objects.create(
        vendor=vendor,
        product_name=product_name,
        category=category_obj,
        subcategory=subcategory_obj,
        brand_name=brand_name,
        model_no=model_no,
        manufacturing_country=manufacturing_country,
        inventory_country=inventory_country,
        inventory_location=inventory_location,
        manufacturing_year=manufacturing_year,
        dimensions=dimensions,
        expiry_date=expiry_date,
        excluded_countries=excluded_countries,
        quantity=quantity,
        currency=currency,
        liquidating_price=liquidating_price,
        msrp=msrp,
        offer=offer,
        description=description,
        reason_to_sell=reason_to_sell,
        warranty=warranty,
        warranty_attachment=warranty_attachment,
        third_party_certificate=third_party_certificate,
        third_party_documents=third_party_documents,
        enquiry_status='PENDING',
        is_active=False
    )

    # 15. Create Product Images
    raw_images = (
        data.get('images') or data.get('image_urls') or data.get('gallery_urls') 
        or data.get('gallery_image_urls') or data.get('gallery') or data.get('photos')
        or data.get('image') or data.get('product_images') or data.get('product_image') 
        or data.get('featured_image_url') or []
    )
    if isinstance(raw_images, str):
        try:
            raw_images = json.loads(raw_images)
        except Exception:
            raw_images = [img.strip() for img in raw_images.split(',') if img.strip()]
    elif not isinstance(raw_images, list):
        raw_images = [raw_images] if raw_images else []

    if isinstance(raw_images, list):
        for item in raw_images:
            if isinstance(item, dict):
                img_link = item.get("url") or item.get("image_url") or ""
                is_real = bool(item.get("is_real_photo", True))
            else:
                img_link = str(item).strip()
                is_real = True
            if img_link:
                ProductImage.objects.create(
                    product=product,
                    image_url=img_link,
                    is_real_photo=is_real
                )

    file_keys = [
        'images', 'image', 'gallery', 'gallery_images', 'photos',
        'product_images', 'product_image', 'files', 'featured_image'
    ]
    seen_files = set()
    for fkey in file_keys:
        if fkey in request.FILES:
            for img_file in request.FILES.getlist(fkey):
                if img_file not in seen_files:
                    seen_files.add(img_file)
                    ProductImage.objects.create(
                        product=product,
                        image=img_file,
                        is_real_photo=True
                    )
    for key in request.FILES:
        if key not in file_keys and any(sub in key.lower() for sub in ['image', 'photo', 'file', 'pic']):
            for img_file in request.FILES.getlist(key):
                if img_file not in seen_files:
                    seen_files.add(img_file)
                    ProductImage.objects.create(
                        product=product,
                        image=img_file,
                        is_real_photo=True
                    )

    response_obj = Response({
        "success": True,
        "message": "Product request submitted successfully and is pending approval.",
        "product_id": product.product_id,
        "data": {
            "id": product.id,
            "product_id": product.product_id,
            "vendor_id": product.formatted_vendor_id or (f"USR-{product.vendor_id:04d}" if product.vendor_id else None),
            "product_name": product.product_name,
            "category": product.category.name if product.category else None,
            "category_id": product.category_id,
            "sub_category": product.subcategory.name if product.subcategory else None,
            "subcategory_id": product.subcategory_id,
            "brand_name": product.brand_name,
            "model_no": product.model_no,
            "inventory_country": product.inventory_country,
            "inventory_location": product.inventory_location,
            "location": product.inventory_location,
            "manufacturing_country": product.manufacturing_country,
            "manufacturing_year": product.manufacturing_year,
            "dimensions": product.dimensions,
            "expiry": product.expiry_date.isoformat() if product.expiry_date else None,
            "quantity": product.quantity,
            "currency": product.currency,
            "msrp": str(product.msrp) if product.msrp is not None else None,
            "liquidation_price": str(product.liquidating_price),
            "price": str(product.current_price or product.liquidating_price),
            "offer": str(product.offer),
            "excluded_countries": product.excluded_countries,
            "description": product.description,
            "reason_to_sell": product.reason_to_sell,
            "warranty": product.warranty,
            "warranty_document": product.warranty_attachment,
            "certificate": product.third_party_certificate,
            "certificate_document": product.third_party_documents,
            "enquiry_status": product.enquiry_status,
            "is_active": product.is_active,
            "created_at": product.created_at.isoformat(),
            "images": [img.url for img in product.images.all()]
        }
    }, status=status.HTTP_201_CREATED)

    seller_label = (product.vendor.full_name or product.vendor.company_name or product.vendor.username) if product.vendor else (data.get("name") or data.get("full_name") or "Guest Seller")
    seller_email = (product.vendor.email if product.vendor else (data.get("email") or data.get("user_email") or data.get("seller_email") or ""))
    seller_phone = (product.vendor.phone if product.vendor else (data.get("phone") or data.get("mobile") or ""))

    # 1. Vendor In-App Notification
    if product.vendor:
        try:
            from AdminApp.services import create_vendor_notification
            create_vendor_notification(
                vendor=product.vendor,
                title="Product Under Review",
                message=f"Your listing for '{product.product_name}' ({product.product_id}) was received and is pending admin review.",
                notification_type="LISTING",
                action_url="/profile"
            )
        except Exception as e:
            print(f"Error creating product submit notification: {e}")

    # 2. Seller Confirmation Email
    if seller_email:
        try:
            from AdminApp.services import EmailService
            EmailService.send_product_submitted_email(
                to_email=seller_email,
                product=product,
                recipient_name=seller_label
            )
        except Exception as e:
            print(f"Error sending seller product confirmation email: {e}")

    # 3. Admin In-App Alert and Admin Email
    try:
        from AdminApp.services import create_admin_notification, EmailService
        create_admin_notification(
            title=f"New Product Enquiry: {product.product_id} - {product.product_name}",
            message=f"New listing '{product.product_name}' ({product.product_id}) submitted by {seller_label} and is pending review.",
            notification_type="ENQUIRY",
            action_url=f"/admin/enquiries/seller/{product.id}/detail/"
        )
        EmailService.notify_admin_product_submitted(
            seller_info={
                "name": seller_label,
                "email": seller_email or "Unregistered / Guest",
                "phone": seller_phone,
            },
            product=product
        )
    except Exception as e:
        print(f"Error creating admin notification for product enquiry: {e}")

    return response_obj


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def submit_lot_request(request):
    """
    Unified API for creating and querying lot listings.
    Supports both JSON payload from frontend lot creation forms and multipart file uploads.
    GET /api/lots/ - List lots (with filters for vendor_id, category, search, page)
    POST /api/lots/ or /api/submit-lot-request/ - Create a new lot listing
    """
    from AdminApp.models import Lot, VendorDetails
    from AdminApp.serializers import LotSerializer
    from django.db.models import Q

    if request.method == "GET":
        qs = Lot.objects.all().order_by("-created_at")
        vendor_param = request.GET.get("vendor_id") or request.GET.get("vendor") or request.GET.get("user_id")
        if vendor_param:
            vendor_obj = _resolve_vendor_from_param(vendor_param)
            if vendor_obj:
                qs = qs.filter(vendor=vendor_obj)



        status_param = request.GET.get("status")
        if status_param:
            qs = qs.filter(enquiry_status__iexact=status_param)
        elif not vendor_param:
            qs = qs.filter(is_active=True, enquiry_status="approved")

        search = request.GET.get("search", "").strip()
        if search:
            qs = qs.filter(Q(title__icontains=search) | Q(description__icontains=search) | Q(key_brands_included__icontains=search))

        page_num = request.GET.get("page", 1)
        limit = request.GET.get("limit", 12)
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 12

        from django.core.paginator import Paginator
        paginator = Paginator(qs, limit)
        try:
            page_obj = paginator.page(page_num)
        except Exception:
            page_obj = paginator.page(1)

        serializer = LotSerializer(page_obj.object_list, many=True, context={"request": request})
        return Response({
            "success": True,
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "lots": serializer.data,
        }, status=status.HTTP_200_OK)

    # POST request processing
    try:
        import json
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        vendor_param = data.get("vendor_id") or data.get("user_id") or request.headers.get("X-Vendor-Id")

        # Handle legacy nested fields if present (lot_details, user_information, manifest_items)
        lot_details = {}
        if 'lot_details' in data:
            val = data['lot_details']
            lot_details = json.loads(val) if isinstance(val, str) else val
            if isinstance(lot_details, dict):
                if 'title' not in data and 'listing_title' not in data:
                    data['title'] = lot_details.get('title', '')
                if 'description' not in data and 'lot_description_and_notes' not in data:
                    data['description'] = lot_details.get('description', '')
                if 'inventory_country' not in data and 'inventory_country' in lot_details:
                    data['inventory_country'] = lot_details.get('inventory_country', '')
                if 'inventory_location' not in data and ('inventory_location' in lot_details or 'location' in lot_details):
                    data['inventory_location'] = lot_details.get('inventory_location') or lot_details.get('location', '')


        user_info = {}
        if 'user_information' in data:
            val = data['user_information']
            user_info = json.loads(val) if isinstance(val, str) else val
            if isinstance(user_info, dict):
                if 'inventory_location' not in data:
                    data['inventory_location'] = user_info.get('location', '')
                if not vendor_param and 'vendor_id' in user_info:
                    vendor_param = user_info['vendor_id']

        # Normalize title and description from frontend payload format
        title_val = data.get("listing_title") or data.get("title") or ""
        desc_val = data.get("lot_description_and_notes") or data.get("description") or ""
        data["title"] = title_val
        data["description"] = desc_val




        # Map file fields from request.FILES (supports all Excel file aliases)
        file_candidates = ["manifest_file", "file", "excel_file", "spreadsheet", "manifest", "lot_file", "excel"]
        for fkey in file_candidates:
            if fkey in request.FILES:
                data["file"] = request.FILES[fkey]
                break

        # Collect raw image files passed for warehouse_images / media
        wh_file_keys = ["warehouse_images", "warehouse_image", "images", "image", "media", "media_files", "photos", "row_image", "raw_image"]
        raw_files_found = []
        for fkey in wh_file_keys:
            if fkey in request.FILES:
                for img_file in request.FILES.getlist(fkey):
                    if hasattr(img_file, "name"):
                        raw_files_found.append(img_file)
        if raw_files_found:
            data["warehouse_images"] = raw_files_found

        # Helper to convert arbitrary data structures into clean JSON-serializable primitives
        def _clean_json_val(val):
            if isinstance(val, (str, int, float, bool)) or val is None:
                return val
            if isinstance(val, dict):
                return {str(k): _clean_json_val(v) for k, v in val.items() if not hasattr(v, 'read')}
            if isinstance(val, (list, tuple)):
                return [_clean_json_val(v) for v in val if not hasattr(v, 'read')]
            if hasattr(val, 'name'):
                return str(val.name)
            return str(val)

        # Extract parsed manifest items if provided from frontend
        parsed_manifest_items = None
        for m_key in ['manifest_items', 'preview_items', 'parsed_items', 'products_list', 'products']:
            if m_key in data and data[m_key]:
                m_val = data[m_key]
                if isinstance(m_val, str):
                    try:
                        parsed_manifest_items = json.loads(m_val)
                    except Exception:
                        parsed_manifest_items = None
                elif isinstance(m_val, list):
                    parsed_manifest_items = m_val
                if parsed_manifest_items:
                    break

        # Build clean raw_payload copy for audit storage
        raw_payload = _clean_json_val(dict(data))
        for key in ['manifest_items', 'preview_items', 'parsed_items', 'lot_details', 'products_list', 'products']:
            raw_payload.pop(key, None)

        serializer = LotSerializer(data=data)
        if serializer.is_valid():
            lot = serializer.save()

            # Resolve and link vendor record if provided
            vendor_obj = None
            if vendor_param:
                vendor_obj = _resolve_vendor_from_param(vendor_param)
                if vendor_obj:
                    lot.vendor = vendor_obj
                    lot.save(update_fields=["vendor"])

            # Store complete raw payload with manifest items safely
            if isinstance(raw_payload, dict):
                raw_payload["is_saved_to_db"] = True
                if lot.warehouse_images:
                    raw_payload["warehouse_images"] = lot.warehouse_images
                if parsed_manifest_items:
                    raw_payload["manifest_items"] = parsed_manifest_items
                    raw_payload["products"] = parsed_manifest_items
            lot.raw_data = raw_payload
            lot.save(update_fields=["raw_data"])

            # Auto-parse spreadsheet if manifest items were not sent directly as JSON
            if not parsed_manifest_items and lot.file:
                try:
                    from lots.importer import parse_spreadsheet
                    lot.file.seek(0)
                    parse_res = parse_spreadsheet(lot.file)
                    extracted = parse_res.get("all_items", [])
                    if extracted:
                        raw_payload["products"] = extracted
                        raw_payload["manifest_items"] = extracted
                        raw_payload["parse_summary"] = parse_res.get("summary")
                        lot.raw_data = raw_payload
                        lot.save(update_fields=["raw_data"])
                except Exception as e:
                    print(f"[submit_lot_request] Auto-parse spreadsheet error: {e}")

            # Dispatch vendor in-app notification and email alerts
            seller_email = None
            seller_name = "Valued Seller"
            if vendor_obj:
                seller_email = vendor_obj.email
                seller_name = vendor_obj.full_name or vendor_obj.company_name or vendor_obj.username or "Valued Seller"
                try:
                    from AdminApp.services import create_vendor_notification
                    create_vendor_notification(
                        vendor=vendor_obj,
                        title="Lot Listing Received",
                        message=f"Your lot listing '{lot.title or lot.lot_number}' ({lot.lot_number}) has been submitted and is currently pending review.",
                        notification_type="LISTING",
                        action_url="/profile"
                    )
                except Exception as e:
                    print(f"Error creating vendor notification for lot: {e}")

            if not seller_email:
                seller_email = (
                    data.get("email") or data.get("user_email") or data.get("seller_email") or
                    (raw_payload.get("user_email") if isinstance(raw_payload, dict) else None) or
                    (raw_payload.get("email") if isinstance(raw_payload, dict) else None)
                )

            # 1. Send confirmation email to seller
            if seller_email:
                try:
                    from AdminApp.services import EmailService
                    EmailService.send_lot_submitted_email(
                        to_email=seller_email,
                        lot=lot,
                        recipient_name=seller_name
                    )
                except Exception as e:
                    print(f"Error sending lot submitted confirmation email: {e}")

            # 2. Send notification email and create in-app notification for admin
            try:
                from AdminApp.services import EmailService, create_admin_notification
                EmailService.notify_admin_lot_submitted(
                    seller_info={
                        "name": seller_name,
                        "email": seller_email or "Unregistered / Guest"
                    },
                    lot=lot
                )
                create_admin_notification(
                    title=f"New Lot Listing: {lot.lot_number}",
                    message=f"New lot listing '{lot.title or lot.lot_number}' ({lot.lot_number}) submitted by {seller_name} and is pending review.",
                    notification_type="LISTING",
                    action_url=f"/admin/enquiries/lots/{lot.id}/detail/"
                )
            except Exception as e:
                print(f"Error sending admin lot notification: {e}")

            serialized_lot_data = LotSerializer(lot, context={"request": request}).data
            return Response({
                "success": True,
                "message": "Lot listing submitted successfully and is pending review.",
                "lot_id": lot.lot_number,
                "raw_id": lot.id,
                "enquiry": serialized_lot_data,
                "data": serialized_lot_data
            }, status=status.HTTP_201_CREATED)

        err_msg = ", ".join([f"{k}: {v[0] if isinstance(v, list) else v}" for k, v in serializer.errors.items()])
        return Response({
            "success": False,
            "message": f"Validation failed for lot submission: {err_msg}",
            "errors": serializer.errors,
            "error_details": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return Response({
            "success": False,
            "message": f"Error processing lot request: {str(exc)}",
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"])
@permission_classes([AllowAny])
def public_lot_detail_api(request, lot_id):
    """
    Public GET API to fetch a single Lot listing with all model fields.
    Supports lookup by numeric ID (e.g. /api/lots/6/) or lot_number (e.g. /api/lots/LOT-00006/).
    """
    from AdminApp.models import Lot
    from AdminApp.serializers import LotSerializer
    from django.db.models import Q

    try:
        if str(lot_id).isdigit():
            lot = Lot.objects.get(Q(id=int(lot_id)) | Q(lot_number__iexact=str(lot_id)))
        else:
            lot = Lot.objects.get(lot_number__iexact=str(lot_id))
    except Lot.DoesNotExist:
        return Response(
            {"success": False, "message": f"Lot '{lot_id}' not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = LotSerializer(lot, context={"request": request})
    return Response({
        "success": True,
        "lot": serializer.data,
        "data": serializer.data
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def lot_warehouse_explorer_api(request, lot_id):
    """
    Public GET API for the Interactive Virtual Warehouse Explorer.
    Fetches structured SKU grid items and wholesale analytics:
    (Total SKUs, Units, MSRP vs Ask, Brand % Breakdown, Condition Distribution, Top Profit Drivers).
    """
    from AdminApp.models import Lot
    from AdminApp.warehouse_explorer import get_lot_warehouse_explorer_data
    from django.db.models import Q

    try:
        if str(lot_id).isdigit():
            lot = Lot.objects.get(Q(id=int(lot_id)) | Q(lot_number__iexact=str(lot_id)))
        else:
            lot = Lot.objects.get(lot_number__iexact=str(lot_id))
    except Lot.DoesNotExist:
        return Response(
            {"success": False, "message": f"Lot '{lot_id}' not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    data = get_lot_warehouse_explorer_data(lot)
    return Response(data, status=status.HTTP_200_OK)


from datetime import timedelta
from django.db.models import F, Q
from AdminApp.models import PageViewLog, BlogPost, Product, Lot

@api_view(["POST"])
@permission_classes([AllowAny])
def track_view_api(request):
    """
    Public API endpoint to record page/entity view pings and dwell-time analytics from Next.js frontend.
    Supports initial pageview logging, continuous heartbeats, duration updates, and stuck-user detection.
    """
    data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)

    log_id = data.get("log_id") or data.get("id")
    duration_seconds = data.get("duration_seconds")
    session_id = str(data.get("session_id", "")).strip()
    visitor_id = str(data.get("visitor_id", "")).strip()
    is_stuck = bool(data.get("is_stuck", False))

    # Duration update / Heartbeat / Exit Beacon for existing page view log
    if log_id:
        try:
            log_entry = PageViewLog.objects.filter(id=int(log_id)).first()
            if log_entry:
                if duration_seconds is not None:
                    try:
                        dur = max(0, int(float(duration_seconds)))
                        log_entry.duration_seconds = max(log_entry.duration_seconds, dur)
                        if dur >= 180 or is_stuck:
                            log_entry.is_stuck = True
                    except (ValueError, TypeError):
                        pass
                if is_stuck:
                    log_entry.is_stuck = True
                log_entry.save(update_fields=["duration_seconds", "is_stuck"])
                return Response({
                    "success": True,
                    "message": "Dwell time updated successfully",
                    "data": {
                        "id": log_entry.id,
                        "log_id": log_entry.id,
                        "duration_seconds": log_entry.duration_seconds,
                        "is_stuck": log_entry.is_stuck
                    }
                }, status=status.HTTP_200_OK)
        except Exception as e:
            pass

    entity_type = str(data.get("entity_type", "page")).lower().strip()
    entity_id = data.get("entity_id")
    entity_slug = str(data.get("entity_slug", "")).strip()
    path = str(data.get("path", "")).strip()
    referrer = str(data.get("referrer", "")).strip() or request.META.get("HTTP_REFERER", "")
    user_agent = str(data.get("user_agent", "")).strip() or request.META.get("HTTP_USER_AGENT", "")

    # Extract client IP address
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.META.get("REMOTE_ADDR")

    # Clean up entity_id if non-numeric
    try:
        if entity_id is not None:
            entity_id = int(entity_id)
    except (ValueError, TypeError):
        entity_id = None

    # Deduplication check: check if the same IP has logged a view for this entity_type + (entity_id or entity_slug or path) within last 1 hour
    one_hour_ago = timezone.now() - timedelta(hours=1)
    
    dedup_query = Q(entity_type=entity_type)
    if ip_address:
        dedup_query &= Q(ip_address=ip_address)

    entity_match = Q()
    if entity_id:
        entity_match |= Q(entity_id=entity_id)
    if entity_slug:
        entity_match |= Q(entity_slug=entity_slug)
    if path:
        entity_match |= Q(path=path)

    dedup_query &= entity_match

    is_duplicate = PageViewLog.objects.filter(dedup_query, created_at__gte=one_hour_ago).exists()

    # Clean duration and stuck state
    dur = 0
    if duration_seconds is not None:
        try:
            dur = max(0, int(float(duration_seconds)))
        except (ValueError, TypeError):
            dur = 0
    if dur >= 180:
        is_stuck = True

    # Log the page view entry with dwell time & visitor session tracking
    page_view_log = PageViewLog.objects.create(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_slug=entity_slug,
        path=path,
        ip_address=ip_address,
        user_agent=user_agent,
        referrer=referrer,
        duration_seconds=dur,
        session_id=session_id,
        visitor_id=visitor_id,
        is_stuck=is_stuck,
    )

    incremented = False
    if not is_duplicate:
        # Atomic F() counter increment based on entity_type
        if entity_type == "blog":
            blog_q = Q()
            if entity_id:
                blog_q |= Q(id=entity_id)
            if entity_slug:
                blog_q |= Q(slug=entity_slug)
            if blog_q:
                updated = BlogPost.objects.filter(blog_q).update(
                    views_count=F("views_count") + 1,
                    total_reads=F("total_reads") + 1
                )
                incremented = bool(updated)

        elif entity_type == "product":
            prod_q = Q()
            if entity_id:
                prod_q |= Q(id=entity_id)
            if entity_slug:
                prod_q |= Q(product_id=entity_slug) | Q(model_no=entity_slug)
            if prod_q:
                updated = Product.objects.filter(prod_q).update(views_count=F("views_count") + 1)
                incremented = bool(updated)

        elif entity_type == "lot":
            lot_q = Q()
            if entity_id:
                lot_q |= Q(id=entity_id)
            if entity_slug:
                lot_q |= Q(lot_number=entity_slug)
            if lot_q:
                updated = Lot.objects.filter(lot_q).update(views_count=F("views_count") + 1)
                incremented = bool(updated)

    return Response({
        "success": True,
        "message": "View tracked successfully",
        "data": {
            "id": page_view_log.id,
            "log_id": page_view_log.id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_slug": entity_slug,
            "duration_seconds": page_view_log.duration_seconds,
            "is_stuck": page_view_log.is_stuck,
            "is_duplicate": is_duplicate,
            "incremented": incremented,
            "created_at": page_view_log.created_at.isoformat()
        }
    }, status=status.HTTP_201_CREATED)


# ==============================================================================
# Vendor In-App Notification REST APIs
# ==============================================================================

def _resolve_vendor_from_param(vendor_param):
    """Helper to resolve a VendorDetails record from USR-xxxx, int ID, username, or email."""
    if not vendor_param:
        return None
    from AdminApp.models import VendorDetails
    v_str = str(vendor_param).strip()
    v_clean = v_str[4:].strip() if v_str.upper().startswith("USR-") else v_str
    vendor = None
    if v_clean.isdigit():
        vendor = VendorDetails.objects.filter(id=int(v_clean)).first()
    if not vendor:
        vendor = VendorDetails.objects.filter(email__iexact=v_str).first()
    if not vendor:
        vendor = VendorDetails.objects.filter(username__iexact=v_str).first()
    return vendor


@api_view(["GET"])
@permission_classes([AllowAny])
def get_vendor_notifications(request):
    """
    GET /api/notifications/
    Returns paginated notifications for the given vendor.
    Query params: vendor_id, unread (true/false), type (LISTING, RFQ, etc.), page, limit
    """
    from AdminApp.models import VendorNotification
    from .serializers import VendorNotificationSerializer
    from django.core.paginator import Paginator

    vendor_param = (
        request.query_params.get("vendor_id")
        or request.query_params.get("user_id")
        or request.query_params.get("email")
        or request.headers.get("X-Vendor-Id")
        or request.headers.get("X-User-Id")
        or request.headers.get("Vendor-Id")
        or request.headers.get("User-Id")
    )
    if not vendor_param and getattr(request, "user", None) and request.user.is_authenticated:
        vendor_param = request.user.email

    vendor = _resolve_vendor_from_param(vendor_param)
    if not vendor:
        return Response({
            "success": False,
            "message": "Valid vendor_id parameter is required.",
            "results": [],
            "count": 0,
            "unread_count": 0
        }, status=status.HTTP_400_BAD_REQUEST)

    qs = VendorNotification.objects.filter(vendor=vendor).order_by("-created_at")

    unread_filter = request.query_params.get("unread")
    if unread_filter is not None:
        if str(unread_filter).lower() in ("true", "1", "t", "yes"):
            qs = qs.filter(is_read=False)
        elif str(unread_filter).lower() in ("false", "0", "f", "no"):
            qs = qs.filter(is_read=True)

    type_filter = request.query_params.get("type")
    if type_filter and type_filter.upper() != "ALL":
        qs = qs.filter(notification_type=type_filter.upper())

    total_count = qs.count()
    unread_count = VendorNotification.objects.filter(vendor=vendor, is_read=False).count()

    page_num = request.query_params.get("page", 1)
    limit = request.query_params.get("limit") or request.query_params.get("page_size", 20)
    try:
        limit = max(1, min(100, int(limit)))
    except (ValueError, TypeError):
        limit = 20

    paginator = Paginator(qs, limit)
    try:
        page_obj = paginator.page(page_num)
    except Exception:
        page_obj = paginator.page(1)

    serializer = VendorNotificationSerializer(page_obj, many=True)
    return Response({
        "success": True,
        "count": total_count,
        "unread_count": unread_count,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "results": serializer.data
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def get_vendor_unread_count(request):
    """
    GET /api/notifications/unread-count/
    Returns the total unread notification count for the vendor.
    Query param: vendor_id
    """
    from AdminApp.models import VendorNotification

    vendor_param = (
        request.query_params.get("vendor_id")
        or request.query_params.get("user_id")
        or request.query_params.get("email")
        or request.headers.get("X-Vendor-Id")
        or request.headers.get("X-User-Id")
        or request.headers.get("Vendor-Id")
        or request.headers.get("User-Id")
    )
    if not vendor_param and getattr(request, "user", None) and request.user.is_authenticated:
        vendor_param = request.user.email

    vendor = _resolve_vendor_from_param(vendor_param)
    if not vendor:
        return Response({
            "success": False,
            "message": "Valid vendor_id parameter is required.",
            "unread_count": 0
        }, status=status.HTTP_400_BAD_REQUEST)

    unread_count = VendorNotification.objects.filter(vendor=vendor, is_read=False).count()
    return Response({
        "success": True,
        "unread_count": unread_count
    }, status=status.HTTP_200_OK)


@api_view(["POST", "PATCH"])
@permission_classes([AllowAny])
def mark_notification_read(request, pk):
    """
    POST /api/notifications/<int:pk>/mark-read/
    Marks a specific notification as read.
    """
    from AdminApp.models import VendorNotification

    notif = VendorNotification.objects.filter(id=pk).first()
    if not notif:
        return Response({
            "success": False,
            "message": "Notification not found."
        }, status=status.HTTP_404_NOT_FOUND)

    notif.is_read = True
    notif.save(update_fields=["is_read"])
    return Response({
        "success": True,
        "message": "Notification marked as read"
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
def mark_all_notifications_read(request):
    """
    POST /api/notifications/mark-all-read/
    Marks all notifications for a vendor as read.
    """
    from AdminApp.models import VendorNotification

    data = request.data if isinstance(request.data, dict) else {}
    vendor_param = (
        data.get("vendor_id")
        or data.get("user_id")
        or request.query_params.get("vendor_id")
        or request.query_params.get("user_id")
        or request.headers.get("X-Vendor-Id")
        or request.headers.get("Vendor-Id")
    )
    if not vendor_param and getattr(request, "user", None) and request.user.is_authenticated:
        vendor_param = request.user.email

    vendor = _resolve_vendor_from_param(vendor_param)
    if not vendor:
        return Response({
            "success": False,
            "message": "Valid vendor_id is required."
        }, status=status.HTTP_400_BAD_REQUEST)

    updated_count = VendorNotification.objects.filter(vendor=vendor, is_read=False).update(is_read=True)
    return Response({
        "success": True,
        "message": "All notifications marked as read",
        "updated_count": updated_count
    }, status=status.HTTP_200_OK)


@api_view(["DELETE", "POST"])
@permission_classes([AllowAny])
def delete_vendor_notification(request, pk):
    """
    DELETE /api/notifications/<int:pk>/ or POST /api/notifications/<int:pk>/delete/
    Deletes/dismisses a notification.
    """
    from AdminApp.models import VendorNotification

    notif = VendorNotification.objects.filter(id=pk).first()
    if not notif:
        return Response({
            "success": False,
            "message": "Notification not found."
        }, status=status.HTTP_404_NOT_FOUND)

    notif.delete()
    return Response({
        "success": True,
        "message": "Notification deleted"
    }, status=status.HTTP_200_OK)


@api_view(["POST", "DELETE"])
@permission_classes([AllowAny])
def clear_all_vendor_notifications(request):
    """
    POST/DELETE /api/notifications/clear-all/
    Permanently deletes all notifications for the specified vendor.
    """
    from AdminApp.models import VendorNotification

    data = request.data if isinstance(request.data, dict) else {}
    vendor_param = (
        data.get("vendor_id")
        or data.get("user_id")
        or data.get("email")
        or request.query_params.get("vendor_id")
        or request.query_params.get("user_id")
        or request.query_params.get("email")
        or request.headers.get("X-Vendor-Id")
        or request.headers.get("X-User-Id")
        or request.headers.get("Vendor-Id")
        or request.headers.get("User-Id")
    )
    if not vendor_param and getattr(request, "user", None) and request.user.is_authenticated:
        vendor_param = request.user.email

    vendor = _resolve_vendor_from_param(vendor_param)
    if not vendor:
        return Response({
            "success": False,
            "message": "Valid vendor_id is required."
        }, status=status.HTTP_400_BAD_REQUEST)

    deleted_count, _ = VendorNotification.objects.filter(vendor=vendor).delete()
    return Response({
        "success": True,
        "message": "All notifications cleared",
        "deleted_count": deleted_count
    }, status=status.HTTP_200_OK)


def _serialize_product_summary(p):
    all_imgs = [img.url for img in p.images.all() if img.url]
    main_img = all_imgs[0] if all_imgs else None
    return {
        "id": p.id,
        "product_id": p.product_id,
        "product_name": p.product_name,
        "brand": p.brand_name,
        "model_no": p.model_no,
        "category": {
            "id": p.category.id,
            "name": p.category.name,
            "slug": p.category.slug,
        } if p.category else None,
        "subcategory": {
            "id": p.subcategory.id,
            "name": p.subcategory.name,
            "slug": p.subcategory.slug,
        } if p.subcategory else None,
        "manufacturing_country": p.manufacturing_country or "",
        "inventory_country": getattr(p, "inventory_country", "") or "",
        "inventory_location": p.inventory_location or "",
        "location": p.inventory_location,
        "manufacturing_year": p.manufacturing_year,
        "dimensions": p.dimensions or "",
        "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
        "excluded_countries": p.excluded_countries or [],
        "quantity": p.quantity,
        "currency": p.currency,
        "price": str(p.current_price or p.liquidating_price or "0.00"),
        "liquidation_price": str(p.liquidating_price),
        "msrp": str(p.msrp) if p.msrp is not None else None,
        "offer": str(p.offer),
        "description": p.description or "",
        "reason_to_sell": p.reason_to_sell or "",
        "warranty": p.warranty or "",
        "warranty_document": p.warranty_attachment or "",
        "third_party_certificate": p.third_party_certificate,
        "certificate_document": p.third_party_documents or "",
        "date_approved": p.date_approved.isoformat() if p.date_approved else None,
        "views_count": p.views_count,
        "is_featured": p.is_featured,
        "is_best_selling": p.is_best_selling,
        "is_new_arrival": p.is_new_arrival,
        "display_order": p.display_order,
        "featured_order": p.featured_order,
        "best_selling_order": p.best_selling_order,
        "new_arrival_order": p.new_arrival_order,
        "image": main_img,
        "images": all_imgs,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }



@api_view(["GET"])
def get_public_products_list(request):
    """
    Public REST API to list products with collection filters and custom sequence ordering.
    Endpoint: GET /api/products/
    Query params:
      ?collection=featured | best_selling | new_arrivals
      ?category=slug
      ?search=query
      ?limit=12&page=1
    """
    from AdminApp.models import Product
    from django.db.models import Case, When, Value, IntegerField, Q
    from django.core.paginator import Paginator

    vendor_param = request.GET.get("vendor_id") or request.GET.get("vendor") or request.GET.get("user_id")
    if vendor_param:
        vendor_obj = _resolve_vendor_from_param(vendor_param)
        if vendor_obj:
            qs = Product.objects.filter(vendor=vendor_obj).select_related("category", "subcategory").prefetch_related("images")
        else:
            qs = Product.objects.none()
    else:
        qs = Product.objects.filter(is_active=True, enquiry_status__iexact="APPROVED").select_related("category", "subcategory").prefetch_related("images")

    collection = (request.GET.get("collection") or request.GET.get("badge") or "").lower()
    order_field = "display_order"

    if collection in ("featured", "featured_deals", "featured-deals"):
        qs = qs.filter(is_featured=True)
        order_field = "featured_order"
    elif collection in ("best_selling", "best-selling", "bestseller", "best_seller"):
        qs = qs.filter(is_best_selling=True)
        order_field = "best_selling_order"
    elif collection in ("new_arrivals", "new-arrivals", "new_arrival", "new"):
        qs = qs.filter(is_new_arrival=True)
        order_field = "new_arrival_order"

    cat = request.GET.get("category")
    if cat:
        qs = qs.filter(Q(category__slug=cat) | Q(category__name__iexact=cat))

    search = request.GET.get("search", "").strip()
    if search:
        qs = qs.filter(Q(product_name__icontains=search) | Q(brand_name__icontains=search) | Q(model_no__icontains=search))

    qs = qs.annotate(
        priority=Case(
            When(**{order_field: 0}, then=Value(999999)),
            default=order_field,
            output_field=IntegerField()
        )
    ).order_by("priority", "-created_at")

    page_num = int(request.GET.get("page", 1))
    limit = int(request.GET.get("limit", 20))
    paginator = Paginator(qs, limit)

    try:
        page_obj = paginator.page(page_num)
    except Exception:
        page_obj = paginator.page(1)

    return Response({
        "success": True,
        "count": paginator.count,
        "total_pages": paginator.num_pages,
        "current_page": page_obj.number,
        "collection": collection or "all",
        "products": [_serialize_product_summary(p) for p in page_obj],
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_homepage_collections(request):
    """
    Combined Public REST API returning Featured Deals, Best Selling, and New Arrivals
    in a single lightweight request, pre-sorted by their custom display sequences.
    Endpoint: GET /api/products/collections/
    """
    from AdminApp.models import Product
    from django.db.models import Case, When, Value, IntegerField

    base_qs = Product.objects.filter(is_active=True, enquiry_status__iexact="APPROVED").select_related("category", "subcategory").prefetch_related("images")

    feat_qs = base_qs.filter(is_featured=True).annotate(
        p=Case(When(featured_order=0, then=Value(999999)), default="featured_order", output_field=IntegerField())
    ).order_by("p", "-created_at")[:12]

    best_qs = base_qs.filter(is_best_selling=True).annotate(
        p=Case(When(best_selling_order=0, then=Value(999999)), default="best_selling_order", output_field=IntegerField())
    ).order_by("p", "-created_at")[:12]

    new_qs = base_qs.filter(is_new_arrival=True).annotate(
        p=Case(When(new_arrival_order=0, then=Value(999999)), default="new_arrival_order", output_field=IntegerField())
    ).order_by("p", "-created_at")[:12]

    return Response({
        "success": True,
        "featured_deals": [_serialize_product_summary(p) for p in feat_qs],
        "best_selling": [_serialize_product_summary(p) for p in best_qs],
        "new_arrivals": [_serialize_product_summary(p) for p in new_qs],
    }, status=status.HTTP_200_OK)


def _format_typesense_hit(hit):
    """
    Normalizes a Typesense search hit into the standard unified listing payload.
    """
    doc = hit.get("document", {})
    item_type = doc.get("item_type", "product")
    is_lot = doc.get("is_lot", False)
    db_id = doc.get("db_id")
    title = doc.get("title", "")
    brand = doc.get("brand", "")
    category = doc.get("category", "")
    subcategory = doc.get("subcategory", "")
    condition = doc.get("condition", "")
    location = doc.get("inventory_location") or doc.get("location", "")
    inventory_country = doc.get("inventory_country", "")
    price = doc.get("price", 0.0)
    msrp = doc.get("msrp", 0.0)
    currency = doc.get("currency", "USD")
    image = doc.get("image", "")
    images = doc.get("images", [])
    listing_url = doc.get("listing_url", "")
    quantity = doc.get("quantity", 1)

    highlights = hit.get("highlights", [])
    highlight_text = ""
    if highlights:
        for h in highlights:
            if h.get("snippet"):
                highlight_text = h["snippet"]
                break

    return {
        "id": db_id,
        "typesense_id": doc.get("id"),
        "item_type": item_type,
        "is_lot": is_lot,
        "title": title,
        "product_name": title,
        "description": doc.get("description", ""),
        "brand": brand,
        "model_no": doc.get("model_no", ""),
        "category": category,
        "subcategory": subcategory,
        "condition": condition,
        "location": location,
        "inventory_location": location,
        "inventory_country": inventory_country,
        "manufacturing_country": doc.get("manufacturing_country", ""),
        "price": price,
        "liquidation_price": doc.get("liquidation_price") or doc.get("liquidating_price") or price,
        "msrp": msrp,
        "currency": currency,
        "quantity": quantity,
        "estQty": quantity,
        "moq": 1,
        "pallet_count": doc.get("pallet_count", 0),
        "pallets": doc.get("pallet_count", 0),
        "distinct_skus": doc.get("distinct_skus", 1),
        "unit_type": doc.get("unit_type", "units"),
        "image": image,
        "images": images,
        "listing_url": listing_url,
        "is_featured": doc.get("is_featured", False),
        "is_best_selling": doc.get("is_best_selling", False),
        "is_new_arrival": doc.get("is_new_arrival", False),
        "highlight": highlight_text,
        "text_match": hit.get("text_match", 0),
    }


def _fallback_postgresql_search(query_text, entity_type, page, limit, category, subcategory, brand, condition, country, min_usd, max_usd, sort_by):
    """
    Zero-downtime PostgreSQL source-of-truth fallback when Typesense is unavailable.
    """
    from AdminApp.models import Product, Lot
    from django.db.models import Q

    results = []

    # 1. Products
    if entity_type in ("all", "product"):
        p_qs = Product.objects.filter(is_active=True, enquiry_status__iexact="APPROVED").select_related("category", "subcategory").prefetch_related("images")
        if query_text:
            p_qs = p_qs.filter(
                Q(product_name__icontains=query_text) |
                Q(brand_name__icontains=query_text) |
                Q(model_no__icontains=query_text) |
                Q(description__icontains=query_text) |
                Q(inventory_location__icontains=query_text)
            )
        if category:
            p_qs = p_qs.filter(Q(category__name__icontains=category) | Q(category__slug__iexact=category))
        if subcategory:
            p_qs = p_qs.filter(Q(subcategory__name__icontains=subcategory) | Q(subcategory__slug__iexact=subcategory))
        if brand:
            p_qs = p_qs.filter(brand_name__icontains=brand)
        if country:
            p_qs = p_qs.filter(Q(inventory_country__icontains=country) | Q(inventory_location__icontains=country))
        if min_usd is not None:
            p_qs = p_qs.filter(liquidating_price__gte=min_usd)
        if max_usd is not None:
            p_qs = p_qs.filter(liquidating_price__lte=max_usd)

        for p in p_qs[:100]:
            all_imgs = [img.url for img in p.images.all() if getattr(img, "url", None)]
            main_img = all_imgs[0] if all_imgs else ""
            results.append({
                "id": p.id,
                "typesense_id": f"product_{p.id}",
                "item_type": "product",
                "is_lot": False,
                "title": p.product_name,
                "product_name": p.product_name,
                "description": p.description or "",
                "brand": p.brand_name or "",
                "model_no": p.model_no or "",
                "category": p.category.name if p.category else "",
                "subcategory": p.subcategory.name if p.subcategory else "",
                "location": p.inventory_location or "",
                "inventory_location": p.inventory_location or "",
                "inventory_country": getattr(p, "inventory_country", "") or "",
                "manufacturing_country": p.manufacturing_country or "",
                "price": float(p.current_price or p.liquidating_price or 0.0),
                "liquidation_price": float(p.liquidating_price or 0.0),
                "msrp": float(p.msrp or 0.0),
                "currency": p.currency or "USD",
                "quantity": p.quantity or 1,
                "estQty": p.quantity or 1,
                "moq": 1,
                "pallet_count": 0,
                "pallets": 0,
                "distinct_skus": 1,
                "unit_type": "units",
                "image": main_img,
                "images": all_imgs,
                "listing_url": f"/product/{p.product_id or p.id}",
                "product_id": p.product_id or "",
                "is_featured": bool(p.is_featured),
                "is_best_selling": bool(p.is_best_selling),
                "is_new_arrival": bool(p.is_new_arrival),
                "created_at": int(p.created_at.timestamp()) if p.created_at else 0,
                "text_match": 100,
            })

    # 2. Lots
    if entity_type in ("all", "lot"):
        l_qs = Lot.objects.filter(is_active=True, enquiry_status__iexact="approved")
        if query_text:
            l_qs = l_qs.filter(
                Q(title__icontains=query_text) |
                Q(description__icontains=query_text) |
                Q(key_brands_included__icontains=query_text) |
                Q(inventory_location__icontains=query_text)
            )
        if brand:
            l_qs = l_qs.filter(key_brands_included__icontains=brand)
        if condition:
            l_qs = l_qs.filter(condition__icontains=condition)
        if country:
            l_qs = l_qs.filter(Q(inventory_country__icontains=country) | Q(inventory_location__icontains=country))

        for lot in l_qs[:100]:
            imgs = [str(x) for x in lot.warehouse_images] if isinstance(lot.warehouse_images, list) else []
            main_img = imgs[0] if imgs else ""
            results.append({
                "id": lot.id,
                "typesense_id": f"lot_{lot.id}",
                "item_type": "lot",
                "is_lot": True,
                "title": lot.title or f"Lot #{lot.lot_number}",
                "product_name": lot.title or "",
                "description": lot.description or "",
                "brand": lot.key_brands_included or "",
                "model_no": "",
                "category": "Wholesale Lots",
                "subcategory": "",
                "condition": lot.condition or "Liquidation Lot",
                "location": lot.inventory_location or "",
                "inventory_location": lot.inventory_location or "",
                "inventory_country": getattr(lot, "inventory_country", "") or "",
                "price": float(lot.ask_price_surplus_payout or 0.0),
                "liquidation_price": float(lot.ask_price_surplus_payout or 0.0),
                "msrp": float(lot.total_est_retail_value_msrp or 0.0),
                "currency": lot.currency or "USD",
                "quantity": int(lot.total_units_quantity or 0),
                "estQty": int(lot.total_units_quantity or 0),
                "moq": 1,
                "pallet_count": int(lot.pallet_count or 0),
                "pallets": int(lot.pallet_count or 0),
                "distinct_skus": int(lot.number_of_distinct_skus or 1),
                "unit_type": lot.primary_unit_type or "units",
                "image": main_img,
                "images": imgs,
                "listing_url": f"/lots/{lot.lot_number or lot.id}",
                "lot_number": lot.lot_number or "",
                "is_featured": False,
                "is_best_selling": False,
                "is_new_arrival": False,
                "created_at": int(lot.created_at.timestamp()) if lot.created_at else 0,
                "text_match": 100,
            })

    total_count = len(results)
    start_idx = (page - 1) * limit
    paged_results = results[start_idx:start_idx + limit]
    return paged_results, total_count


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def typesense_search_view(request):
    """
    Intelligent Search API backed by Typesense with automatic PostgreSQL fallback.
    Supports typo-tolerant prefix searching, multi-currency normalization,
    rule-based natural language constraint extraction, and faceted categorization.
    Endpoint: GET /api/search/ or POST /api/search/
    """
    from AdminApp.typesense_service import (
        is_typesense_available,
        get_typesense_client,
        get_collection_name,
        to_usd,
    )
    from AdminApp.typesense_query_parser import TypesenseQueryParser

    if request.method == "POST":
        data = request.data
    else:
        data = request.query_params

    raw_query = (data.get("q") or data.get("query") or "").strip()
    entity_type = (data.get("type") or data.get("entity_type") or "all").strip().lower()

    try:
        page = max(1, int(data.get("page", 1) or 1))
    except (ValueError, TypeError):
        page = 1

    try:
        limit = int(data.get("limit") or data.get("per_page") or 20)
    except (ValueError, TypeError):
        limit = 20
    limit = max(1, min(limit, 100))

    # Filters
    category_param = (data.get("category") or "").strip()
    subcategory_param = (data.get("subcategory") or "").strip()
    brand_param = (data.get("brand") or "").strip()
    condition_param = (data.get("condition") or "").strip()
    country_param = (data.get("country") or "").strip()
    city_param = (data.get("city") or "").strip()
    currency_param = (data.get("currency") or "USD").strip().upper()
    min_price_param = data.get("min_price")
    max_price_param = data.get("max_price")
    sort_by_param = (data.get("sort_by") or "").strip()

    # Rule-Based Natural Language Query Parsing
    parsed_intent = TypesenseQueryParser.parse(raw_query) if raw_query else {
        "cleaned_query": "",
        "is_lot": None,
        "currency": None,
        "min_price": None,
        "max_price": None,
        "min_price_usd": None,
        "max_price_usd": None,
        "location": None,
        "brand": None,
        "condition": None,
        "category": None,
        "has_warranty": None,
        "has_filters": False,
    }

    # Query text: use cleaned query if NLP stripped conversational phrases, or raw query
    query_text = parsed_intent.get("cleaned_query") if parsed_intent.get("has_filters") else raw_query
    if not query_text:
        query_text = "*"

    # Resolve entity type
    if entity_type == "all" and parsed_intent.get("is_lot") is True:
        target_entity = "lot"
    else:
        target_entity = entity_type

    # Multi-currency price normalization to USD
    min_usd = None
    if min_price_param not in (None, ""):
        try:
            min_usd = to_usd(float(min_price_param), currency_param)
        except (ValueError, TypeError):
            pass
    elif parsed_intent.get("min_price_usd") is not None:
        min_usd = parsed_intent["min_price_usd"]

    max_usd = None
    if max_price_param not in (None, ""):
        try:
            max_usd = to_usd(float(max_price_param), currency_param)
        except (ValueError, TypeError):
            pass
    elif parsed_intent.get("max_price_usd") is not None:
        max_usd = parsed_intent["max_price_usd"]

    # Active filters
    active_cat = category_param or parsed_intent.get("category") or ""
    active_subcat = subcategory_param or ""
    active_brand = brand_param or parsed_intent.get("brand") or ""
    active_cond = condition_param or parsed_intent.get("condition") or ""
    active_country = country_param or parsed_intent.get("location") or ""
    active_city = city_param or ""

    # Check Typesense availability
    is_healthy, _ = is_typesense_available()

    if is_healthy:
        try:
            client = get_typesense_client()
            coll_name = get_collection_name()

            filter_clauses = ["is_active:=true", "enquiry_status:=[APPROVED, approved]"]

            if target_entity == "product":
                filter_clauses.append("is_lot:=false")
            elif target_entity == "lot":
                filter_clauses.append("is_lot:=true")

            if active_cat:
                escaped_cat = active_cat.replace("`", "")
                filter_clauses.append(f"(category:={escaped_cat} || category_slug:={escaped_cat})")

            if active_subcat:
                escaped_subcat = active_subcat.replace("`", "")
                filter_clauses.append(f"(subcategory:={escaped_subcat} || subcategory_slug:={escaped_subcat})")

            if active_brand:
                escaped_brand = active_brand.replace("`", "")
                filter_clauses.append(f"brand:={escaped_brand}")

            if active_cond:
                escaped_cond = active_cond.replace("`", "")
                filter_clauses.append(f"condition:={escaped_cond}")

            if active_country:
                escaped_country = active_country.replace("`", "")
                filter_clauses.append(f"country:={escaped_country}")

            if active_city:
                escaped_city = active_city.replace("`", "")
                filter_clauses.append(f"city:={escaped_city}")

            # Price filter in USD
            if min_usd is not None and max_usd is not None:
                filter_clauses.append(f"price_usd:[{min_usd}..{max_usd}]")
            elif min_usd is not None:
                filter_clauses.append(f"price_usd:>={min_usd}")
            elif max_usd is not None:
                filter_clauses.append(f"price_usd:<={max_usd}")

            filter_by_str = " && ".join(filter_clauses)

            # Sort parameters
            sort_by = "created_at:desc"
            if sort_by_param in ("price:asc", "price_asc", "low_to_high"):
                sort_by = "price_usd:asc"
            elif sort_by_param in ("price:desc", "price_desc", "high_to_low"):
                sort_by = "price_usd:desc"
            elif sort_by_param in ("views", "views_count:desc", "popular"):
                sort_by = "views_count:desc"
            elif query_text != "*":
                sort_by = "_text_match:desc,created_at:desc"

            search_params = {
                "q": query_text,
                "query_by": "title,product_name,description,brand,category,subcategory,model_no,sku,location,country,city",
                "query_by_weights": "4,4,2,3,3,3,3,3,2,2,2",
                "prefix": "true",
                "num_typos": "2",
                "drop_tokens_threshold": 1,
                "filter_by": filter_by_str,
                "page": page,
                "per_page": limit,
                "sort_by": sort_by,
                "facet_by": "category,brand,condition,country,currency,item_type",
                "max_facet_values": 20,
            }

            resp = client.collections[coll_name].documents.search(search_params)

            hits = resp.get("hits", [])
            results = [_format_typesense_hit(h) for h in hits]
            total_count = resp.get("found", len(results))
            total_pages = max(1, (total_count + limit - 1) // limit)

            # Format facet counts
            facets_dict = {}
            for fc in resp.get("facet_counts", []):
                fname = fc.get("field_name")
                counts = [{"value": c.get("value"), "count": c.get("count")} for c in fc.get("counts", [])]
                facets_dict[fname] = counts

            return Response({
                "success": True,
                "engine": "typesense",
                "query": raw_query,
                "count": total_count,
                "total_results": total_count,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": limit,
                "parsed_intent": parsed_intent,
                "facets": facets_dict,
                "results": results,
                "products": results,  # Backwards compatibility
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.warning(f"Typesense query execution failed: {e}. Falling back to PostgreSQL.")

    # PostgreSQL Source-of-truth Fallback
    results, total_count = _fallback_postgresql_search(
        query_text=query_text if query_text != "*" else "",
        entity_type=target_entity,
        page=page,
        limit=limit,
        category=active_cat,
        subcategory=active_subcat,
        brand=active_brand,
        condition=active_cond,
        country=active_country,
        min_usd=min_usd,
        max_usd=max_usd,
        sort_by=sort_by_param
    )
    total_pages = max(1, (total_count + limit - 1) // limit)

    return Response({
        "success": True,
        "engine": "postgresql_fallback",
        "query": raw_query,
        "count": total_count,
        "total_results": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "per_page": limit,
        "parsed_intent": parsed_intent,
        "facets": {},
        "results": results,
        "products": results,
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def typesense_suggestions_view(request):
    """
    Ultra-fast autocomplete suggestions endpoint for search input debouncing.
    Endpoint: GET /api/search/suggestions/?q=ser&limit=6
    """
    from AdminApp.typesense_service import (
        is_typesense_available,
        get_typesense_client,
        get_collection_name,
    )

    q = (request.GET.get("q") or request.GET.get("query") or "").strip()
    try:
        limit = int(request.GET.get("limit", 6))
    except (ValueError, TypeError):
        limit = 6
    limit = max(1, min(limit, 20))

    if len(q) < 2:
        return Response({"success": True, "suggestions": []}, status=status.HTTP_200_OK)

    is_healthy, _ = is_typesense_available()
    if is_healthy:
        try:
            client = get_typesense_client()
            coll_name = get_collection_name()

            resp = client.collections[coll_name].documents.search({
                "q": q,
                "query_by": "title,product_name,brand,category,model_no",
                "prefix": "true",
                "per_page": limit,
                "filter_by": "is_active:=true && enquiry_status:=[APPROVED, approved]",
            })

            suggestions = []
            for hit in resp.get("hits", []):
                doc = hit.get("document", {})
                suggestions.append({
                    "id": doc.get("db_id"),
                    "title": doc.get("title", ""),
                    "item_type": doc.get("item_type", "product"),
                    "is_lot": doc.get("is_lot", False),
                    "category": doc.get("category", ""),
                    "brand": doc.get("brand", ""),
                    "price": doc.get("price", 0.0),
                    "currency": doc.get("currency", "USD"),
                    "image": doc.get("image", ""),
                    "url": doc.get("listing_url", ""),
                })

            return Response({
                "success": True,
                "engine": "typesense",
                "query": q,
                "suggestions": suggestions,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.warning(f"Typesense suggestions failed: {e}. Falling back to PostgreSQL.")

    # PostgreSQL suggestions fallback
    from AdminApp.models import Product, Lot
    from django.db.models import Q

    suggestions = []
    p_qs = Product.objects.filter(
        is_active=True, enquiry_status__iexact="APPROVED"
    ).filter(
        Q(product_name__icontains=q) | Q(brand_name__icontains=q)
    ).prefetch_related("images")[:limit]

    for p in p_qs:
        all_imgs = [img.url for img in p.images.all() if getattr(img, "url", None)]
        main_img = all_imgs[0] if all_imgs else ""
        suggestions.append({
            "id": p.id,
            "title": p.product_name,
            "item_type": "product",
            "is_lot": False,
            "category": p.category.name if p.category else "",
            "brand": p.brand_name or "",
            "price": float(p.liquidating_price or p.current_price or 0.0),
            "currency": p.currency or "USD",
            "image": main_img,
            "url": f"/product/{p.product_id or p.id}",
        })

    if len(suggestions) < limit:
        remaining = limit - len(suggestions)
        l_qs = Lot.objects.filter(
            is_active=True, enquiry_status__iexact="approved"
        ).filter(
            Q(title__icontains=q) | Q(key_brands_included__icontains=q)
        )[:remaining]

        for lot in l_qs:
            imgs = [str(x) for x in lot.warehouse_images] if isinstance(lot.warehouse_images, list) else []
            main_img = imgs[0] if imgs else ""
            suggestions.append({
                "id": lot.id,
                "title": lot.title or f"Lot #{lot.lot_number}",
                "item_type": "lot",
                "is_lot": True,
                "category": "Wholesale Lots",
                "brand": lot.key_brands_included or "",
                "price": float(lot.ask_price_surplus_payout or 0.0),
                "currency": lot.currency or "USD",
                "image": main_img,
                "url": f"/lots/{lot.lot_number or lot.id}",
            })

    return Response({
        "success": True,
        "engine": "postgresql_fallback",
        "query": q,
        "suggestions": suggestions,
    }, status=status.HTTP_200_OK)


# Backwards compatibility alias
semantic_search_products = typesense_search_view




