import threading
from django.utils import timezone
from django.db import connection, close_old_connections
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
import json
from .models import Item
from .serializers import ItemSerializer


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
        img_url = b.featured_image_url
        if not img_url and b.image:
            img_url = b.image.url
        blogs_data.append({
            "id": b.id,
            "title": b.title,
            "slug": b.slug,
            "blog_code": b.blog_code,
            "author": b.author,
            "category": b.category_name,
            "excerpt": b.excerpt,
            "image": img_url,
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

    img_url = blog.featured_image_url
    if not img_url and blog.image:
        img_url = blog.image.url

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
    }, status=status.HTTP_200_OK)


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
        raw_data = {k: v for k, v in request.data.items() if k not in ("file", "lot_file", "excel_file", "manifest", "spreadsheet", "excel")}

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

    vendor_param = request.data.get("vendor_id") or request.data.get("user_id") or request.headers.get("X-Vendor-Id")
    if vendor_param:
        vendor_obj = _resolve_vendor_from_param(vendor_param)
        if vendor_obj:
            lot.vendor = vendor_obj
            lot.save(update_fields=["vendor"])
            try:
                from AdminApp.services import create_vendor_notification
                create_vendor_notification(
                    vendor=vendor_obj,
                    title="Lot Manifest Uploaded",
                    message=f"Batch '{lot.lot_number}' is processing.",
                    notification_type="LISTING",
                    action_url="/profile"
                )
            except Exception as e:
                print(f"Error creating lot notification: {e}")

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
        company_name=reg_data.get("company_name") or "",
        business_location=reg_data.get("business_location") or "",
        category_interested=reg_data.get("category_interested") or "",
        user_type=reg_data.get("user_type") or "BUYER",
        status=True
    )
    
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
            "business_location": vendor.business_location,
            "business_address": vendor.business_address,
            "tax_registration_number": vendor.tax_registration_number,
            "business_type": vendor.business_type,
            "category_interested": vendor.category_interested,
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

    if "account_entity_type" in data:
        vendor.account_entity_type = data["account_entity_type"]
        if vendor.account_entity_type == "COMPANY":
            if not data.get("company_name"):
                return Response({"success": False, "message": "Company name is required for Company/Business accounts."}, status=status.HTTP_400_BAD_REQUEST)
            vendor.company_name = data["company_name"]
        else:
            vendor.company_name = ""
        
    if "business_location" in data:
        vendor.business_location = data["business_location"]
    
    if "business_address" in data:
        vendor.business_address = data["business_address"]
    if "tax_registration_number" in data:
        vendor.tax_registration_number = data["tax_registration_number"]
    if "business_type" in data:
        vendor.business_type = data["business_type"]
        
    if "user_type" in data:
        vendor.user_type = data["user_type"]
    
    cat_inst = data.get("category_interested", [])
    if isinstance(cat_inst, str):
        cat_inst = [c.strip() for c in cat_inst.split(",") if c.strip()]
    vendor.category_interested = cat_inst
    
    vendor.save()

    prof_info = vendor.get_profile_completion_details()
    activated_products_count = 0
    if prof_info["is_complete"]:
        from AdminApp.models import Product
        activated_products_count = Product.objects.filter(
            vendor=vendor,
            enquiry_status__iexact="APPROVED",
            is_active=False
        ).update(is_active=True)

        if activated_products_count > 0:
            try:
                from AdminApp.services import create_vendor_notification
                create_vendor_notification(
                    vendor=vendor,
                    title="Profile Completed - Products Published!",
                    message=f"Congratulations! Your profile is 100% complete and {activated_products_count} approved product listing(s) have now been published live to the marketplace.",
                    notification_type="LISTING",
                    action_url="/profile"
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
        "business_location": vendor.business_location,
        "business_address": vendor.business_address,
        "tax_registration_number": vendor.tax_registration_number,
        "business_type": vendor.business_type,
        "category_interested": vendor.category_interested,
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
        "business_location": vendor.business_location,
        "business_address": vendor.business_address,
        "tax_registration_number": vendor.tax_registration_number,
        "business_type": vendor.business_type,
        "category_interested": vendor.category_interested
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
        serializer.save()
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

    # 5. Manufacturing Country & Inventory Location
    manufacturing_country = (data.get('country') or data.get('manufacturing_country') or data.get('manufacturingCountry') or '').strip()
    inventory_location = (data.get('inventory_location') or data.get('inventoryLocation') or data.get('location') or data.get('warehouse_location') or data.get('stock_location') or '').strip()

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

    lp_val = data.get('liquidating_price') or data.get('liquidatingPrice') or data.get('price') or 0
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
            "country": product.manufacturing_country,
            "inventory_location": product.inventory_location,
            "manufacturing_year": product.manufacturing_year,
            "dimensions": product.dimensions,
            "expiry": product.expiry_date.isoformat() if product.expiry_date else None,
            "quantity": product.quantity,
            "currency": product.currency,
            "msrp": str(product.msrp) if product.msrp is not None else None,
            "liquidating_price": str(product.liquidating_price),
            "current_price": str(product.current_price),
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

    if product.vendor:
        try:
            from AdminApp.services import create_vendor_notification
            create_vendor_notification(
                vendor=product.vendor,
                title="Product Under Review",
                message=f"Your listing for '{product.product_name}' was received.",
                notification_type="LISTING",
                action_url="/profile"
            )
        except Exception as e:
            print(f"Error creating product submit notification: {e}")

    return response_obj


@api_view(["POST"])
@permission_classes([AllowAny])
def submit_lot_request(request):
    """
    Endpoint for vendors to submit a lot batch request (via file upload).
    Handles multipart/form-data for the .xlsx/.csv file upload.
    """
    import json
    data = request.data.copy()
    vendor_id = data.get('vendor_id')
    
    # Parse nested JSON strings if present (lot_details, user_information, manifest_items)
    lot_details = {}
    try:
        if 'lot_details' in data:
            val = data['lot_details']
            lot_details = json.loads(val) if isinstance(val, str) else val
    except Exception:
        pass

    user_info = {}
    try:
        if 'user_information' in data:
            val = data['user_information']
            user_info = json.loads(val) if isinstance(val, str) else val
    except Exception:
        pass
        
    manifest = []
    try:
        if 'manifest_items' in data:
            val = data['manifest_items']
            manifest = json.loads(val) if isinstance(val, str) else val
    except Exception:
        pass

    # Map parsed data to explicit model fields
    if lot_details:
        data['title'] = lot_details.get('title', '')
        data['description'] = lot_details.get('description', '')
        data['total_price'] = lot_details.get('total_retail_value', 0.0)
        
        cats = lot_details.get('categories', [])
        if cats and isinstance(cats, list):
            data['category_name'] = cats[0].get('name', '')
            
    if user_info:
        data['inventory_location'] = user_info.get('location', '')
        if not vendor_id and 'vendor_id' in user_info:
            vendor_id = user_info['vendor_id']

    # Map manifest_file to the model's 'file' field
    if 'manifest_file' in request.FILES and 'file' not in data:
        data['file'] = request.FILES['manifest_file']

    # Keep the rest in raw_data (properly serialized as JSON string to avoid DRF errors)
    raw_dict = {
        'lot_details': lot_details,
        'user_information': user_info,
        'manifest_items': manifest
    }
    data['raw_data'] = json.dumps(raw_dict)
    
    serializer = LotBatchEnquirySerializer(data=data)
    if serializer.is_valid():
        enquiry = serializer.save()
        
        # Link to vendor if provided
        if vendor_id:
            vid_clean = str(vendor_id).strip()
            if vid_clean.upper().startswith("USR-"):
                vid_clean = vid_clean[4:].strip()
            vendor = None
            if vid_clean.isdigit():
                vendor = VendorDetails.objects.filter(id=int(vid_clean)).first()
            if not vendor:
                vendor = VendorDetails.objects.filter(email__iexact=str(vendor_id).strip()).first()
            if vendor:
                if hasattr(enquiry, 'vendor'):
                    enquiry.vendor = vendor
                if hasattr(enquiry, 'uploaded_by'):
                    enquiry.uploaded_by = vendor
                enquiry.save()

                try:
                    from AdminApp.services import create_vendor_notification
                    batch_id = getattr(enquiry, "lot_number", f"BAT-{enquiry.id}")
                    create_vendor_notification(
                        vendor=vendor,
                        title="Lot Manifest Uploaded",
                        message=f"Batch '{batch_id}' is processing.",
                        notification_type="LISTING",
                        action_url="/profile"
                    )
                except Exception as e:
                    print(f"Error creating lot notification: {e}")
                
        return Response({
            "success": True,
            "message": "Lot request submitted successfully and is pending approval.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
        
    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


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
    img_url = p.images.first().image.url if p.images.exists() else None
    return {
        "id": p.id,
        "product_id": p.product_id,
        "product_name": p.product_name,
        "brand": p.brand_name,
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
        "liquidating_price": str(p.liquidating_price),
        "current_price": str(p.current_price),
        "previous_price": str(p.previous_price) if p.previous_price is not None else None,
        "offer": str(p.offer),
        "currency": p.currency,
        "quantity": p.quantity,
        "inventory_location": p.inventory_location,
        "is_featured": p.is_featured,
        "is_best_selling": p.is_best_selling,
        "is_new_arrival": p.is_new_arrival,
        "display_order": p.display_order,
        "featured_order": p.featured_order,
        "best_selling_order": p.best_selling_order,
        "new_arrival_order": p.new_arrival_order,
        "image": img_url,
        "created_at": p.created_at.isoformat(),
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


@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def semantic_search_products(request):
    """
    Semantic Natural Language Search API using pgvector in Neon DB.
    Allows conversational buyer queries, e.g.:
    - "Show me 2U rackmount servers under $500 available in Maharashtra"
    - "Industrial pumps with warranty"
    - "Used Dell servers under 40000 INR"

    Parses conversational intent, extracts structured constraints (price, location, warranty, brand),
    and executes cosine similarity ranking over 768-dimensional vector embeddings in PostgreSQL.
    """
    if request.method == "POST":
        query = (request.data.get("query") or request.data.get("q") or "").strip()
        try:
            limit = int(request.data.get("limit", 12))
        except (ValueError, TypeError):
            limit = 12
    else:
        query = (request.query_params.get("query") or request.query_params.get("q") or "").strip()
        try:
            limit = int(request.query_params.get("limit", 12))
        except (ValueError, TypeError):
            limit = 12

    if not query:
        return Response({
            "success": False,
            "message": "Query parameter ('q' or 'query') is required.",
            "results": [],
            "total_results": 0
        }, status=status.HTTP_400_BAD_REQUEST)

    limit = max(1, min(limit, 50))

    from AdminApp.semantic_search import semantic_product_search
    try:
        search_result = semantic_product_search(query_text=query, limit=limit)
        return Response(search_result, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"Semantic search error: {e}")
        return Response({
            "success": False,
            "message": f"Semantic search failed: {str(e)}",
            "query": query,
            "results": [],
            "total_results": 0
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




