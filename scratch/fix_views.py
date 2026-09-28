import os

filepath = r"d:\CORALBEES\surplus-backend\api\views.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# keep up to line 322 (which is index 322 since lines are 0-indexed)
# Wait, let's just keep lines up to the end of submit_lot_enquiry
keep_lines = []
for line in lines:
    if line.strip() == 'serializer = VerifyOTPSerializer(data=request.data)':
        break
    keep_lines.append(line)

code_to_add = """

import random
import uuid
import hashlib
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from AdminApp.models import VendorDetails, VendorOTP
from .serializers import (
    SendRegistrationOTPSerializer,
    VerifyOTPSerializer,
    SendLoginOTPSerializer
)

def generate_otp():
    return str(random.randint(100000, 999999))

@api_view(["POST"])
@permission_classes([AllowAny])
def send_registration_otp(request):
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
        registration_data=data
    )
    
    subject = "Surplus - Your Registration OTP"
    message = f"Hello,\\n\\nYour OTP for registration is: {otp_code}.\\n\\nPlease do not share this code with anyone.\\n\\nThank you,\\nSurplus Team"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yourdomain.com')
    try:
        send_mail(subject, message, from_email, [email], fail_silently=True)
        print(f"--- REGISTRATION OTP FOR {email}: {otp_code} ---")
    except Exception as e:
        print(f"Error sending email: {e}")
    
    return Response({"success": True, "status": "otp_sent", "message": "OTP sent successfully."})

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
    
    username = email.split("@")[0] + "_" + str(random.randint(1000, 9999))
    
    vendor = VendorDetails.objects.create(
        username=username,
        email=email,
        first_name=reg_data.get("full_name", ""),
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
    
    return Response({"success": True, "status": "verified", "message": "Registration successful."})


@api_view(["POST"])
@permission_classes([AllowAny])
def send_login_otp(request):
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
    
    subject = "Surplus - Your Login OTP"
    message = f"Hello,\\n\\nYour OTP to log in is: {otp_code}.\\n\\nPlease do not share this code with anyone.\\n\\nThank you,\\nSurplus Team"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@yourdomain.com')
    try:
        send_mail(subject, message, from_email, [email], fail_silently=True)
        print(f"--- LOGIN OTP FOR {email}: {otp_code} ---")
    except Exception as e:
        print(f"Error sending email: {e}")
    
    return Response({"success": True, "status": "otp_sent", "message": "OTP sent successfully."})

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
        "first_name": vendor.first_name,
        "user_type": vendor.user_type
    })


from .serializers import PartnershipEnquirySerializer

@api_view(["POST"])
@permission_classes([AllowAny])
def submit_partnership_enquiry(request):
    serializer = PartnershipEnquirySerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response({
            "success": True,
            "message": "Partnership enquiry submitted successfully."
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        "success": False,
        "errors": serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)
"""

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(keep_lines)
    f.write(code_to_add)

print("Fixed views.py")
