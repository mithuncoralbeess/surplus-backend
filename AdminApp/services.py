import os
import json
import base64
import logging
import requests
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Centralized EmailService powered by ZeptoMail (Zoho Transactional Email Service)
    with Django SMTP backup fallback and attachment handling.
    """

    API_URL = os.getenv("ZEPTOMAIL_API_URL", "https://api.zeptomail.in/v1.1/email")
    API_KEY = os.getenv("ZEPTOMAIL_API_KEY", "")
    FROM_NAME = os.getenv("ZEPTOMAIL_FROM_NAME", "Surplus Market")
    FROM_ADDRESS = os.getenv("ZEPTOMAIL_FROM_EMAIL", "noreply@surplusmarket.com")
    EMAIL_SEND_ENABLED = os.getenv("EMAIL_SEND_ENABLED", "True").lower() in ("true", "1", "t")

    @classmethod
    def get_headers(cls):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Zoho-enczapikey {cls.API_KEY}",
        }

    @classmethod
    def send_email(cls, to_email: str, subject: str, html_content: str, service_name=None, context=None) -> bool:
        """
        Dispatches email via ZeptoMail REST API with Django SMTP fallback.
        Respects EMAIL_SEND_ENABLED setting for safety during development/testing.
        """
        if not cls.EMAIL_SEND_ENABLED:
            logger.info(
                f"[EmailService - SAFE MODE (Dispatch Disabled)] "
                f"To: {to_email} | Subject: {subject} | Service: {service_name or 'General'}"
            )
            return True

        # 1. Primary: ZeptoMail REST API
        if cls.API_KEY:
            payload = {
                "from": {
                    "name": cls.FROM_NAME,
                    "address": cls.FROM_ADDRESS,
                },
                "to": [{"email_address": {"address": to_email}}],
                "subject": subject,
                "htmlbody": html_content,
            }

            try:
                response = requests.post(
                    cls.API_URL,
                    headers=cls.get_headers(),
                    data=json.dumps(payload),
                    timeout=10,
                )
                if response.status_code in [200, 201]:
                    logger.info(f"Email sent via ZeptoMail to {to_email}: {subject}")
                    return True
                else:
                    logger.warning(
                        f"ZeptoMail API responded with code {response.status_code}: {response.text}"
                    )
            except Exception as e:
                logger.error(f"ZeptoMail API request error: {e}")

        # 2. Backup: Django standard SMTP / Brevo HTTP Backend
        try:
            import re
            plain_body = re.sub(r'<[^>]+>', ' ', html_content or "")
            plain_body = ' '.join(plain_body.split()).strip() or subject

            from_email_str = f"{cls.FROM_NAME} <{cls.FROM_ADDRESS}>"
            send_mail(
                subject=subject,
                message=plain_body,
                html_message=html_content,
                from_email=from_email_str,
                recipient_list=[to_email],
                fail_silently=False,
            )
            logger.info(f"Email sent via Django SMTP fallback to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP backup to {to_email}: {e}")
            return False

    @classmethod
    def send_email_with_attachments(
        cls, to_email: str, subject: str, html_content: str, file_paths=None, attachments_data=None
    ) -> bool:
        """
        Dispatches email with Base64 encoded attachments via ZeptoMail.
        """
        if not cls.EMAIL_SEND_ENABLED:
            logger.info(
                f"[EmailService - SAFE MODE] To: {to_email} | Subject: {subject} (With Attachments)"
            )
            return True

        attachments = []

        # Read files from disk
        if file_paths:
            for fpath in file_paths:
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        fname = os.path.basename(fpath)
                        attachments.append({
                            "name": fname,
                            "content": base64.b64encode(f.read()).decode("utf-8"),
                            "mime_type": "application/pdf" if fname.endswith(".pdf") else "application/octet-stream",
                        })

        # Extra in-memory attachment dicts
        if attachments_data:
            attachments.extend(attachments_data)

        payload = {
            "from": {"name": cls.FROM_NAME, "address": cls.FROM_ADDRESS},
            "to": [{"email_address": {"address": to_email}}],
            "subject": subject,
            "htmlbody": html_content,
            "attachments": attachments,
        }

        try:
            response = requests.post(
                cls.API_URL,
                headers=cls.get_headers(),
                data=json.dumps(payload),
                timeout=15,
            )
            return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Failed to send email with attachments: {e}")
            return False

    # -------------------------------------------------------------
    # High-Level Email Triggers
    # -------------------------------------------------------------

    @classmethod
    def send_otp_mail(cls, to_email: str, otp: str, first_name="", reset_link=None) -> bool:
        """User registration or login OTP email."""
        html_content = render_to_string(
            "FinalTemplates/partials/email_partials/email_otp.html",
            {"otp": otp, "first_name": first_name, "reset_link": reset_link},
        )
        return cls.send_email(to_email, f"Surplus Market - Your Verification OTP: {otp}", html_content, "OTP")

    @classmethod
    def send_signup_welcome(cls, to_email: str, first_name="") -> bool:
        """Welcome email sent after user creation."""
        html_content = render_to_string(
            "FinalTemplates/partials/email_partials/email_signup_yes.html",
            {"first_name": first_name},
        )
        return cls.send_email(to_email, "Welcome to Surplus Market!", html_content, "Welcome")

    @classmethod
    def send_password_reset_yes(cls, to_email: str, first_name="", reset_link=None) -> bool:
        """Password reset notification."""
        html_content = render_to_string(
            "FinalTemplates/partials/email_partials/email_reset_yes.html",
            {"first_name": first_name, "reset_link": reset_link},
        )
        return cls.send_email(to_email, "Surplus Market - Password Changed", html_content, "PasswordReset")

    @classmethod
    def send_admin_password_reset_otp(cls, email: str, otp: str, first_name="SuperAdmin") -> bool:
        """SuperAdmin 6-digit OTP email."""
        html_content = render_to_string(
            "FinalTemplates/partials/email_partials/email_admin_password_reset_otp.html",
            {"otp": otp, "first_name": first_name},
        )
        return cls.send_email(
            email, f"Surplus Admin - Password Reset OTP [{otp}]", html_content, "AdminOTP"
        )

    @classmethod
    def notify_admin_rfq_submitted(cls, buyer_info: dict, items_list: list) -> bool:
        """Notifies admin when a Request For Quote (RFQ) is submitted."""
        rows_html = "".join([
            f"<tr><td style='padding:8px; border:1px solid #ddd;'>{item.get('title')}</td>"
            f"<td style='padding:8px; border:1px solid #ddd;'>{item.get('quantity')}</td></tr>"
            for item in items_list
        ])
        html_content = (
            f"<h2>New RFQ Quote Request Basket</h2>"
            f"<p>Buyer: <strong>{buyer_info.get('name')}</strong> ({buyer_info.get('email')})</p>"
            f"<table style='border-collapse: collapse; width: 100%;'>"
            f"<thead><tr><th style='border:1px solid #ddd; padding:8px;'>Item</th><th style='border:1px solid #ddd; padding:8px;'>Quantity</th></tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table>"
        )
        admin_email = os.getenv("ADMIN_NOTIFICATION_EMAIL", "super@gmail.com")
        return cls.send_email(admin_email, "New RFQ Quote Basket Submitted", html_content, "RFQ")

    @classmethod
    def notify_admin_multiple_products(cls, seller_info: dict, products_list: list) -> bool:
        """Notifies admin when a seller submits multiple products."""
        html_content = render_to_string(
            "FinalTemplates/partials/email_partials/email_admin_product_added.html",
            {
                "seller_name": seller_info.get("name", "Seller"),
                "seller_email": seller_info.get("email", ""),
                "product_count": len(products_list),
            },
        )
        admin_email = os.getenv("ADMIN_NOTIFICATION_EMAIL", "super@gmail.com")
        return cls.send_email(admin_email, "New Seller Products Submitted for Review", html_content, "ProductReview")

    @classmethod
    def send_product_approved_email(
        cls,
        to_email: str,
        product,
        recipient_name: str = "Valued Seller",
        action_url: str = "",
        is_profile_complete: bool = True,
        profile_completion_percentage: int = 100,
        missing_fields_labels: list = None,
        profile_url: str = "",
    ) -> bool:
        """
        Sends an email notification to the user when their product listing is approved.
        Includes profile completion percentage alert if vendor profile is incomplete.
        """
        if not to_email:
            logger.warning("send_product_approved_email skipped: recipient email is missing.")
            return False

        frontend_base = os.getenv("FRONTEND_URL", "https://surplus-frontend-staging.vercel.app").rstrip("/")
        default_action_url = f"{frontend_base}/profile"
        profile_link = profile_url or f"{frontend_base}/profile"

        # Resolve product attributes safely from model instance or dict
        product_name = (
            getattr(product, "product_name", None)
            or getattr(product, "title", None)
            or (product.get("product_name") if isinstance(product, dict) else "")
            or "Product Listing"
        )
        product_id = (
            getattr(product, "product_id", None)
            or getattr(product, "sku", None)
            or (product.get("product_id") if isinstance(product, dict) else "")
            or ""
        )
        category_name = ""
        if hasattr(product, "category") and product.category:
            category_name = getattr(product.category, "name", "")
        elif isinstance(product, dict):
            category_name = product.get("category") or ""

        brand = getattr(product, "brand_name", None) or getattr(product, "brand", "") or (product.get("brand_name") if isinstance(product, dict) else "")
        model_no = getattr(product, "model_no", None) or (product.get("model_no") if isinstance(product, dict) else "")
        quantity = getattr(product, "quantity", None) or getattr(product, "stock_quantity", "") or (product.get("quantity") if isinstance(product, dict) else "")
        price = getattr(product, "liquidating_price", None) or getattr(product, "current_price", None) or getattr(product, "price", "") or (product.get("liquidating_price") if isinstance(product, dict) else "")
        currency = getattr(product, "currency", "USD") or "USD"
        inventory_location = getattr(product, "inventory_location", "") or (product.get("inventory_location") if isinstance(product, dict) else "")

        context = {
            "user_name": recipient_name or "Valued Seller",
            "product_name": product_name,
            "product_id": product_id,
            "category_name": category_name,
            "brand": brand,
            "model_no": model_no,
            "quantity": quantity,
            "price": price,
            "currency": currency,
            "inventory_location": inventory_location,
            "action_url": action_url or default_action_url,
            "profile_url": profile_link,
            "is_profile_complete": is_profile_complete,
            "profile_completion_percentage": profile_completion_percentage,
            "missing_fields_labels": missing_fields_labels or [],
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_product_approved.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for approved email, using fallback HTML: {e}")
            if not is_profile_complete:
                missing_str = f"<p><strong>Missing details:</strong> {', '.join(missing_fields_labels or [])}</p>" if missing_fields_labels else ""
                html_content = (
                    f"<h2>Your Listing Has Been Approved!</h2>"
                    f"<p>Hello {recipient_name},</p>"
                    f"<p>Your product <strong>{product_name}</strong> ({product_id}) has been approved by admin review.</p>"
                    f"<div style='background-color:#fffbeb;border:1px solid #fde68a;padding:12px;border-radius:6px;'>"
                    f"<p style='color:#92400e;margin:0;'><strong>Action Required: Profile Incomplete ({profile_completion_percentage}%)</strong></p>"
                    f"<p style='color:#b45309;'>To list your product for public visibility, you must complete all your user profile details.</p>"
                    f"{missing_str}"
                    f"<p><a href='{profile_link}' style='color:#d97706;font-weight:bold;'>Complete your profile to publish</a></p>"
                    f"</div>"
                )
            else:
                html_content = (
                    f"<h2>Your Listing Has Been Approved!</h2>"
                    f"<p>Hello {recipient_name},</p>"
                    f"<p>Your product <strong>{product_name}</strong> ({product_id}) has been approved and is now live on Surplus Market.</p>"
                    f"<p><a href='{action_url or default_action_url}'>View your listing</a></p>"
                )

        if not is_profile_complete:
            subject = f"Listing Approved: {product_name} [{product_id or 'PRO'}] - Complete Profile to Publish"
        else:
            subject = f"Listing Approved: {product_name} [{product_id or 'PRO'}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "ProductApproved", context=context)

    @classmethod
    def send_product_declined_email(
        cls,
        to_email: str,
        product,
        recipient_name: str = "Valued Seller",
        reason: str = "",
        action_url: str = ""
    ) -> bool:
        """
        Sends an email notification to the user when their product listing is declined.
        """
        if not to_email:
            logger.warning("send_product_declined_email skipped: recipient email is missing.")
            return False

        frontend_base = os.getenv("FRONTEND_URL", "https://surplus-frontend-staging.vercel.app").rstrip("/")
        default_action_url = f"{frontend_base}/profile"

        product_name = (
            getattr(product, "product_name", None)
            or getattr(product, "title", None)
            or (product.get("product_name") if isinstance(product, dict) else "")
            or "Product Listing"
        )
        product_id = (
            getattr(product, "product_id", None)
            or getattr(product, "sku", None)
            or (product.get("product_id") if isinstance(product, dict) else "")
            or ""
        )
        category_name = ""
        if hasattr(product, "category") and product.category:
            category_name = getattr(product.category, "name", "")
        elif isinstance(product, dict):
            category_name = product.get("category") or ""

        brand = getattr(product, "brand_name", None) or getattr(product, "brand", "") or (product.get("brand_name") if isinstance(product, dict) else "")
        model_no = getattr(product, "model_no", None) or (product.get("model_no") if isinstance(product, dict) else "")

        context = {
            "user_name": recipient_name or "Valued Seller",
            "product_name": product_name,
            "product_id": product_id,
            "category_name": category_name,
            "brand": brand,
            "model_no": model_no,
            "reason": reason or "",
            "action_url": action_url or default_action_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_product_declined.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for declined email, using fallback HTML: {e}")
            html_content = (
                f"<h2>Product Listing Review Notice</h2>"
                f"<p>Hello {recipient_name},</p>"
                f"<p>Your product listing <strong>{product_name}</strong> ({product_id}) could not be approved at this time.</p>"
                f"<p>{reason or 'Please review your listing specifications and resubmit.'}</p>"
                f"<p><a href='{action_url or default_action_url}'>Review your listing</a></p>"
            )

        subject = f"Listing Update: {product_name} [{product_id or 'PRO'}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "ProductDeclined", context=context)

    @classmethod
    def email_linsting_confirm(cls, seller_email: str, product_title: str) -> bool:
        """Legacy helper for listing confirmation."""
        return cls.send_product_approved_email(
            to_email=seller_email,
            product={"product_name": product_title},
            recipient_name="Valued Seller"
        )

    @classmethod
    def send_contact_form_email(cls, user_data: dict, form_type="query") -> bool:
        """Dispatches contact/partnership queries to admins."""
        html_content = (
            f"<h3>Contact Inquiry ({form_type.upper()})</h3>"
            f"<p><strong>Name:</strong> {user_data.get('name')}</p>"
            f"<p><strong>Email:</strong> {user_data.get('email')}</p>"
            f"<p><strong>Message:</strong> {user_data.get('message')}</p>"
        )
        admin_email = os.getenv("ADMIN_NOTIFICATION_EMAIL", "super@gmail.com")
        return cls.send_email(admin_email, f"Contact Form Submission: {form_type}", html_content, "Contact")

    @classmethod
    def send_prize_email(cls, to_email: str, prize_name: str, certificate_path=None) -> bool:
        """Dispatches prize reward email with optional PDF certificate attachment."""
        html_content = f"<h2>Congratulations!</h2><p>You won: <strong>{prize_name}</strong> on Surplus Market!</p>"
        file_paths = [certificate_path] if certificate_path else None
        return cls.send_email_with_attachments(
            to_email, f"Surplus Reward: You won {prize_name}!", html_content, file_paths=file_paths
        )


def create_vendor_notification(vendor, title, message, notification_type="SYSTEM", action_url=""):
    """
    Creates a VendorNotification record for the vendor and logs the event.
    Supports vendor instance, vendor_id ('USR-xxxx' or int), or email string.
    """
    from .models import VendorDetails, VendorNotification
    import logging
    _logger = logging.getLogger(__name__)

    target_vendor = None
    if isinstance(vendor, VendorDetails):
        target_vendor = vendor
    elif vendor:
        v_str = str(vendor).strip()
        v_clean = v_str[4:].strip() if v_str.upper().startswith("USR-") else v_str
        if v_clean.isdigit():
            target_vendor = VendorDetails.objects.filter(id=int(v_clean)).first()
        if not target_vendor:
            target_vendor = VendorDetails.objects.filter(email__iexact=v_str).first()
        if not target_vendor:
            target_vendor = VendorDetails.objects.filter(username__iexact=v_str).first()

    if not target_vendor:
        _logger.warning(f"create_vendor_notification skipped: could not resolve vendor for {vendor}")
        return None

    valid_types = ("LISTING", "RFQ", "AUCTION", "SYSTEM", "ORDER")
    n_type = str(notification_type).upper()
    if n_type not in valid_types:
        n_type = "SYSTEM"

    notification = VendorNotification.objects.create(
        vendor=target_vendor,
        title=title,
        message=message,
        notification_type=n_type,
        action_url=action_url or "",
        is_read=False
    )
    _logger.info(f"[VendorNotification] Created ID {notification.id} for {target_vendor.vendor_id}: {title}")
    return notification

