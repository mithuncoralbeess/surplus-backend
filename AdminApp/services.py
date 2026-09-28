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
    EMAIL_SEND_ENABLED = os.getenv("EMAIL_SEND_ENABLED", "False").lower() in ("true", "1", "t")

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

        # 2. Backup: Django standard SMTP
        try:
            from_email_str = f"{cls.FROM_NAME} <{cls.FROM_ADDRESS}>"
            send_mail(
                subject=subject,
                message="",
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
    def email_linsting_confirm(cls, seller_email: str, product_title: str) -> bool:
        """Notifies seller when their product listing is approved."""
        html_content = f"<p>Your listing <strong>{product_title}</strong> has been approved and is now live on Surplus Market.</p>"
        return cls.send_email(seller_email, f"Listing Approved: {product_title}", html_content, "ListingConfirm")

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
