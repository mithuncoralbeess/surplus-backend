import threading
from django.utils import timezone
from django.db import connection, close_old_connections
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status, viewsets
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
@permission_classes([IsAuthenticated])
def submit_seller_enquiry(request):
    """
    Authenticated REST API for sellers to submit individual product enquiries.
    Endpoint: POST /api/enquiries/seller/
    Auto-generates PRO-XXXXX ID. Requires user authentication.
    """
    from AdminApp.models import Product, VendorDetails
    from AdminApp.serializers import ProductSerializer

    raw_data = {}
    if isinstance(request.data, dict):
        raw_data = dict(request.data)
    
    vendor = None
    if hasattr(request.user, 'vendor'):
        vendor = request.user.vendor
    elif request.user.is_authenticated:
        vendor = VendorDetails.objects.filter(email=request.user.email).first()

    product_name = raw_data.get("product_name") or raw_data.get("title") or "Product Listing"

    enquiry = Product.objects.create(
        product_name=product_name,
        vendor=vendor,
        enquiry_status="PENDING",
        is_active=False,
        raw_data=raw_data
    )

    return Response({
        "success": True,
        "message": "Product enquiry submitted successfully.",
        "enquiry": ProductSerializer(enquiry).data,
        "product_id": enquiry.product_id or enquiry.sku,
        "created_at": enquiry.created_at.strftime("%Y-%m-%d %H:%M"),
    }, status=status.HTTP_201_CREATED)


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
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Surplus Market <mithun.coralbees@gmail.com>')

        try:
            send_mail(
                subject=subject,
                message=message,
                html_message=html_message,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=True,
            )
            print(f"--- REGISTRATION OTP SENT/CREATED FOR {email}: {otp_code} ---")
        except Exception as e:
            print(f"FAILED TO DISPATCH REGISTRATION OTP EMAIL TO {email}: {e}")
    
        return Response({"success": True, "status": "otp_sent", "message": "OTP sent successfully."})
    except Exception as exc:
        print(f"send_registration_otp Exception: {exc}")
        return Response({"success": False, "message": f"Server error: {str(exc)}"}, status=status.HTTP_400_BAD_REQUEST)

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
        email=email,
        mobile_number=reg_data.get("mobile_number", ""),
        company_name=reg_data.get("company_name", ""),
        business_location=reg_data.get("business_location", ""),
        category_interested=reg_data.get("category_interested", ""),
        user_type=reg_data.get("user_type", "BUYER"),
        status=True
    )
    
    otp_record.is_used = True
    otp_record.vendor = vendor
    otp_record.save()
    
    return Response({"success": True, "status": "verified", "message": "OTP verified successfully. Proceed to complete profile."})


@api_view(["POST"])
@permission_classes([AllowAny])
def complete_profile(request):
    serializer = CompleteProfileSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    email = data["email"].strip().lower()
    
    vendor = VendorDetails.objects.filter(email=email).first()
    if not vendor:
        return Response({"success": False, "message": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        
    vendor.account_entity_type = data["account_entity_type"]
    if vendor.account_entity_type == "COMPANY":
        if not data.get("company_name"):
            return Response({"success": False, "message": "Company name is required for Company/Business accounts."}, status=status.HTTP_400_BAD_REQUEST)
        vendor.company_name = data["company_name"]
    else:
        vendor.company_name = ""
        
    vendor.business_location = data["business_location"]
    vendor.user_type = data["user_type"]
    
    cat_inst = data.get("category_interested", [])
    if isinstance(cat_inst, str):
        cat_inst = [c.strip() for c in cat_inst.split(",") if c.strip()]
    vendor.category_interested = cat_inst
    
    vendor.save()
    
    return Response({
        "success": True, 
        "status": "profile_completed", 
        "message": "Profile completed successfully.",
        "vendor_id": vendor.id,
        "email": vendor.email,
        "username": vendor.username,
        "user_type": vendor.user_type,
        "mobile_number": vendor.mobile_number,
        "business_location": vendor.business_location
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def send_login_otp(request):
    try:
        close_old_connections()
        serializer = SendLoginOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"success": False, "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        email = serializer.validated_data["email"].strip().lower()
        
        vendor = VendorDetails.objects.filter(email=email).first()
        if not vendor:
            return Response({"success": False, "message": "No account found with this email."}, status=status.HTTP_404_NOT_FOUND)
            
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
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Surplus Market <mithun.coralbees@gmail.com>')

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
        "vendor_id": vendor.id,
        "email": vendor.email,
        "username": vendor.username,
        "user_type": vendor.user_type,
        "mobile_number": vendor.mobile_number,
        "business_location": vendor.business_location
    })


from .serializers import PartnershipEnquirySerializer
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
@permission_classes([IsAuthenticated])
def submit_product_request(request):
    """
    Endpoint for authenticated vendors/users to submit a single product request.
    Handles multipart/form-data for image and certificate uploads. Requires login.
    """
    from AdminApp.serializers import ProductSerializer
    from AdminApp.models import Product, VendorDetails

    data = request.data.copy()
    vendor_id = data.get('vendor_id')
    
    # Map frontend keys to explicit model fields
    key_mapping = {
        'product_name': 'product_name',
        'title': 'product_name',
        'liquidatingPrice': 'liquidating_price',
        'liquidating_price': 'liquidating_price',
        'price': 'liquidating_price',
        'previousPrice': 'previous_price',
        'previous_price': 'previous_price',
        'originalPrice': 'previous_price',
        'original_price': 'previous_price',
        'currentPrice': 'current_price',
        'current_price': 'current_price',
        'quantity': 'stock_quantity',
        'category': 'category_name',
        'country': 'manufacturing_country',
        'year': 'manufacturing_year',
        'expiry': 'expiry_date',
        'modelNo': 'model_no',
        'model_no': 'model_no',
        'modelPartNo': 'model_no',
        'model_part_no': 'model_no',
        'sku': 'model_no',
        'brandName': 'brand',
        'excludedCountries': 'excluded_countries',
        'reasonToSell': 'reason_to_sell',
        'location': 'inventory_location',
        'condition': 'condition',
        'product_condition': 'condition',
        'stock_condition': 'condition',
    }
    
    for front_key, model_key in key_mapping.items():
        if front_key in data and model_key not in data:
            data[model_key] = data[front_key]
            
    # Handle files
    if 'images' in request.FILES and 'image' not in data:
        images = request.FILES.getlist('images')
        if images:
            data['image'] = images[0]

    if 'certificate' in request.FILES and 'third_party_certificate' not in data:
        data['third_party_certificate'] = request.FILES['certificate']
        
    data['enquiry_status'] = 'PENDING'
    data['is_active'] = False
    data['raw_data'] = {}
    
    serializer = ProductSerializer(data=data)
    if serializer.is_valid():
        enquiry = serializer.save()
        
        # Link to vendor if authenticated user or vendor_id
        vendor = None
        if hasattr(request.user, 'vendor'):
            vendor = request.user.vendor
        elif vendor_id:
            vendor = VendorDetails.objects.filter(id=vendor_id).first()
        elif request.user.is_authenticated:
            vendor = VendorDetails.objects.filter(email=request.user.email).first()

        if vendor:
            enquiry.vendor = vendor
            enquiry.save(update_fields=['vendor'])
                
        return Response({
            "success": True,
            "message": "Product request submitted successfully and is pending approval.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
        
    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)
        
    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


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
            vendor = VendorDetails.objects.filter(id=vendor_id).first()
            if vendor:
                enquiry.uploaded_by = vendor
                enquiry.save(update_fields=['uploaded_by'])
                
        return Response({
            "success": True,
            "message": "Lot request submitted successfully and is pending approval.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)
        
    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)
