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
    def get_frontend_url(cls) -> str:
        """Resolves the production frontend URL from environment or settings."""
        return os.getenv("FRONTEND_URL", getattr(settings, "FRONTEND_URL", "https://surplusmarket.com")).rstrip("/")

    @classmethod
    def get_headers(cls):
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Zoho-enczapikey {cls.API_KEY}",
        }

    @classmethod
    def send_email(cls, to_email, subject: str, html_content: str, service_name=None, context=None) -> bool:
        """
        Dispatches email via ZeptoMail REST API with Django SMTP / Brevo fallback.
        Supports single email string, comma-separated string, or list/tuple of recipients.
        Respects EMAIL_SEND_ENABLED setting for safety during development/testing.
        """
        if isinstance(to_email, (list, tuple, set)):
            to_recipients = [str(e).strip() for e in to_email if str(e).strip()]
        elif isinstance(to_email, str):
            to_recipients = [e.strip() for e in to_email.split(",") if e.strip()]
        else:
            to_recipients = [str(to_email).strip()]

        if not to_recipients:
            logger.warning("[EmailService] No valid recipient email address provided.")
            return False

        to_str = ", ".join(to_recipients)

        if not cls.EMAIL_SEND_ENABLED:
            logger.info(
                f"[EmailService - SAFE MODE (Dispatch Disabled)] "
                f"To: {to_str} | Subject: {subject} | Service: {service_name or 'General'}"
            )
            return True

        # 1. Primary: ZeptoMail REST API
        if cls.API_KEY:
            payload = {
                "from": {
                    "name": cls.FROM_NAME,
                    "address": cls.FROM_ADDRESS,
                },
                "to": [{"email_address": {"address": addr}} for addr in to_recipients],
                "reply_to": [{"address": "contact@surplusmarket.com", "name": "Surplus Market"}],
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
                    logger.info(f"Email sent via ZeptoMail to {to_str}: {subject}")
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

            from django.core.mail import EmailMultiAlternatives
            from_email_str = f"{cls.FROM_NAME} <{cls.FROM_ADDRESS}>"
            mail_msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_body,
                from_email=from_email_str,
                to=to_recipients,
                reply_to=["contact@surplusmarket.com"],
            )
            mail_msg.attach_alternative(html_content, "text/html")
            mail_msg.send(fail_silently=False)
            logger.info(f"Email sent via Django SMTP / Brevo backend to {to_str}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP backup to {to_str}: {e}")
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
    def send_signup_welcome(cls, to_email: str, first_name="", vendor=None) -> bool:
        """Rich welcome email sent after user completes registration / onboarding."""
        frontend_base = cls.get_frontend_url()
        marketplace_url = f"{frontend_base}/"
        profile_url = f"{frontend_base}/profile"

        vendor_id = getattr(vendor, "vendor_id", None) or (vendor.get("vendor_id") if isinstance(vendor, dict) else "")
        raw_id = getattr(vendor, "id", None) or (vendor.get("id") if isinstance(vendor, dict) else "")
        if not vendor_id and raw_id:
            vendor_id = f"USR-{int(raw_id):04d}"

        full_name = getattr(vendor, "full_name", None) or (vendor.get("full_name") if isinstance(vendor, dict) else "") or first_name or "Valued Member"
        resolved_first_name = first_name or (getattr(vendor, "first_name", "") if vendor else "") or full_name.split()[0]
        user_type = getattr(vendor, "user_type", None) or (vendor.get("user_type") if isinstance(vendor, dict) else "BUYER")
        account_entity_type = getattr(vendor, "account_entity_type", None) or (vendor.get("account_entity_type") if isinstance(vendor, dict) else "COMPANY")
        company_name = getattr(vendor, "company_name", None) or (vendor.get("company_name") if isinstance(vendor, dict) else "")
        country = getattr(vendor, "country", None) or (vendor.get("country") if isinstance(vendor, dict) else "United Arab Emirates")
        business_location = getattr(vendor, "business_location", None) or (vendor.get("business_location") if isinstance(vendor, dict) else "")

        cats = getattr(vendor, "category_interested_list", None) or []
        if not cats and hasattr(vendor, "category_interested"):
            cats = vendor.category_interested if isinstance(vendor.category_interested, list) else [str(vendor.category_interested)]
        elif isinstance(vendor, dict):
            cats = vendor.get("category_interested", [])
            if isinstance(cats, str):
                cats = [c.strip() for c in cats.split(",") if c.strip()]
        categories_str = ", ".join(cats) if cats else ""

        context = {
            "first_name": resolved_first_name,
            "full_name": full_name,
            "vendor_id": vendor_id,
            "email": to_email,
            "user_type": user_type,
            "account_entity_type": account_entity_type,
            "company_name": company_name,
            "country": country,
            "business_location": business_location,
            "categories_str": categories_str,
            "marketplace_url": marketplace_url,
            "contact_email": "contact@surplusmarket.com",
            "support_email": "contact@surplusmarket.com",
        }

        html_content = render_to_string(
            "FinalTemplates/partials/email_partials/email_signup_yes.html",
            context,
        )
        return cls.send_email(to_email, "Welcome to Surplus Market - Your Sourcing & Liquidation Gateway!", html_content, "Welcome", context=context)

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
    def notify_admin_rfq_submitted(cls, buyer_info: dict, items_list: list = None, rfq=None) -> bool:
        """Notifies admin when a Request For Quote (RFQ) is submitted."""
        backend_base = os.getenv("BACKEND_URL", "https://surplus-backend-uhg0.onrender.com").rstrip("/")
        rfq_id = getattr(rfq, "id", None) or (rfq.get("id") if isinstance(rfq, dict) else "") or (buyer_info.get("id") if isinstance(buyer_info, dict) else "")
        admin_review_url = f"{backend_base}/admin/rfq-requests/{rfq_id}/detail/" if rfq_id else f"{backend_base}/admin/rfq-requests/"

        ref = getattr(rfq, "reference", None) or (rfq.get("reference") if isinstance(rfq, dict) else "") or buyer_info.get("reference", "RFQ-PENDING")
        buyer_name = buyer_info.get("name") or buyer_info.get("contact_person") or getattr(rfq, "contact_person", "Valued Buyer")
        buyer_email = buyer_info.get("email") or getattr(rfq, "email", "")
        company_name = buyer_info.get("company_name") or getattr(rfq, "company_name", "")
        total_units = getattr(rfq, "total_units", None) or buyer_info.get("total_units", 0)
        estimated_value = getattr(rfq, "estimated_value", None) or buyer_info.get("estimated_value", "0.00")
        currency = getattr(rfq, "currency", "USD") or buyer_info.get("currency", "USD")

        country = getattr(rfq, "country", None) or (rfq.get("country") if isinstance(rfq, dict) else "") or buyer_info.get("country", "")
        business_location = getattr(rfq, "business_location", None) or (rfq.get("business_location") if isinstance(rfq, dict) else "") or buyer_info.get("business_location", "")
        phone = getattr(rfq, "phone", None) or (rfq.get("phone") if isinstance(rfq, dict) else "") or buyer_info.get("phone", "")

        resolved_items = items_list or (rfq.items.all() if hasattr(rfq, "items") else [])

        context = {
            "rfq": rfq,
            "ref": ref,
            "buyer_name": buyer_name,
            "buyer_email": buyer_email,
            "buyer_phone": phone,
            "company_name": company_name,
            "country": country,
            "business_location": business_location,
            "total_units": total_units,
            "estimated_value": estimated_value,
            "currency": currency,
            "items_list": resolved_items,
            "admin_review_url": admin_review_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_rfq_admin_alert.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for admin rfq alert, using fallback HTML: {e}")
            items_html = "".join([
                f"<tr><td style='padding:8px; border:1px solid #ddd;'>{getattr(it, 'title', it.get('title') if isinstance(it, dict) else str(it))}</td>"
                f"<td style='padding:8px; border:1px solid #ddd;'>{getattr(it, 'quantity', it.get('quantity') if isinstance(it, dict) else '')}</td></tr>"
                for it in resolved_items
            ])
            loc_str = f" | Location: {business_location}" if business_location else ""
            country_str = f" | Country: {country}" if country else ""
            html_content = (
                f"<h2>New RFQ Quote Request Basket</h2>"
                f"<p>Reference: <strong>{ref}</strong></p>"
                f"<p>Buyer: <strong>{buyer_name}</strong> ({buyer_email}){country_str}{loc_str}</p>"
                f"<p>Total Units: {total_units} | Value: {currency} {estimated_value}</p>"
                f"<table style='border-collapse: collapse; width: 100%;'>"
                f"<thead><tr><th style='border:1px solid #ddd; padding:8px;'>Item</th><th style='border:1px solid #ddd; padding:8px;'>Quantity</th></tr></thead>"
                f"<tbody>{items_html}</tbody>"
                f"</table>"
                f"<p><a href='{admin_review_url}'>Review in Admin Dashboard</a></p>"
            )

        admin_emails = cls.get_admin_notification_emails()
        subject = f"New Buyer RFQ Received: {ref} - {buyer_name}"
        return cls.send_email(admin_emails, subject, html_content, "RFQAdminAlert", context=context)

    @classmethod
    def notify_admin_product_submitted(cls, seller_info: dict, product) -> bool:
        """
        Notifies admin when a seller submits a product listing / enquiry for review.
        """
        backend_base = os.getenv("BACKEND_URL", "https://surplus-backend-uhg0.onrender.com").rstrip("/")
        prod_id = getattr(product, "id", None) or (product.get("id") if isinstance(product, dict) else "")
        admin_review_url = f"{backend_base}/admin/enquiries/seller/{prod_id}/detail/" if prod_id else f"{backend_base}/admin/enquiries/seller/"

        product_name = (
            getattr(product, "product_name", None)
            or getattr(product, "title", None)
            or (product.get("product_name") if isinstance(product, dict) else "")
            or "Product Listing"
        )
        product_code = (
            getattr(product, "product_id", None)
            or (product.get("product_id") if isinstance(product, dict) else "")
            or (f"PRO-{prod_id}" if prod_id else "PRO-PENDING")
        )
        category_name = ""
        if hasattr(product, "category") and product.category:
            category_name = getattr(product.category, "name", str(product.category))
        elif isinstance(product, dict):
            category_name = product.get("category", "")

        quantity = getattr(product, "quantity", None) or (product.get("quantity") if isinstance(product, dict) else 0)
        currency = getattr(product, "currency", "USD") or "USD"
        liquidating_price = getattr(product, "liquidating_price", None) or (product.get("liquidating_price") if isinstance(product, dict) else None)
        msrp = getattr(product, "msrp", None) or (product.get("msrp") if isinstance(product, dict) else None)

        seller_name = seller_info.get("name") or seller_info.get("full_name") or "Seller"
        seller_email = seller_info.get("email") or ""
        seller_phone = seller_info.get("phone") or ""

        context = {
            "seller_name": seller_name,
            "seller_email": seller_email,
            "seller_phone": seller_phone,
            "product_name": product_name,
            "product_code": product_code,
            "category_name": category_name,
            "quantity": quantity,
            "currency": currency,
            "liquidating_price": liquidating_price,
            "msrp": msrp,
            "admin_review_url": admin_review_url,
            "product": product,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_admin_product_added.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for admin product alert: {e}")
            html_content = (
                f"<h2>New Product Submitted for Review</h2>"
                f"<p>Product: <strong>{product_name}</strong> ({product_code})</p>"
                f"<p>Seller: <strong>{seller_name}</strong> ({seller_email})</p>"
                f"<p>Category: {category_name} | Qty: {quantity} | Price: {currency} {liquidating_price}</p>"
                f"<p><a href='{admin_review_url}'>Review in Admin Dashboard</a></p>"
            )

        admin_emails = cls.get_admin_notification_emails()
        subject = f"New Product Submitted for Review: {product_name} [{product_code}]"
        return cls.send_email(admin_emails, subject, html_content, "AdminProductReview", context=context)

    # Backwards-compatibility alias for existing code
    notify_admin_enquiry_received = notify_admin_product_submitted

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
        admin_emails = cls.get_admin_notification_emails()
        return cls.send_email(admin_emails, "New Seller Products Submitted for Review", html_content, "ProductReview")

    @classmethod
    def send_product_submitted_email(
        cls,
        to_email: str,
        product,
        recipient_name: str = "Valued Seller",
        action_url: str = "",
    ) -> bool:
        """
        Sends an email confirmation to the seller when they submit a product listing.
        """
        if not to_email:
            logger.warning("send_product_submitted_email skipped: recipient email is missing.")
            return False

        frontend_base = cls.get_frontend_url()
        default_action_url = f"{frontend_base}/profile"

        prod_id = getattr(product, "id", None) or (product.get("id") if isinstance(product, dict) else "")
        product_name = (
            getattr(product, "product_name", None)
            or getattr(product, "title", None)
            or (product.get("product_name") if isinstance(product, dict) else "")
            or "Product Listing"
        )
        product_code = (
            getattr(product, "product_id", None)
            or (product.get("product_id") if isinstance(product, dict) else "")
            or (f"PRO-{prod_id}" if prod_id else "PRO-PENDING")
        )
        category_name = ""
        if hasattr(product, "category") and product.category:
            category_name = getattr(product.category, "name", str(product.category))
        elif isinstance(product, dict):
            category_name = product.get("category", "")

        brand = getattr(product, "brand_name", "") or (product.get("brand_name") if isinstance(product, dict) else "")
        model_no = getattr(product, "model_no", "") or (product.get("model_no") if isinstance(product, dict) else "")
        brand_model = f"{brand} ({model_no})" if brand and model_no else (brand or model_no or "")

        quantity = getattr(product, "quantity", None) or (product.get("quantity") if isinstance(product, dict) else None)
        currency = getattr(product, "currency", "USD") or "USD"
        liquidating_price = getattr(product, "liquidating_price", None) or (product.get("liquidating_price") if isinstance(product, dict) else None)
        inventory_location = getattr(product, "inventory_location", "") or (product.get("inventory_location") if isinstance(product, dict) else "")

        context = {
            "user_name": recipient_name or "Valued Seller",
            "product_name": product_name,
            "product_id": product_code,
            "category_name": category_name,
            "brand_model": brand_model,
            "quantity": quantity,
            "currency": currency,
            "liquidating_price": liquidating_price,
            "inventory_location": inventory_location,
            "action_url": action_url or default_action_url,
            "product": product,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_product_submitted.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for product submitted email, using fallback HTML: {e}")
            html_content = (
                f"<h2>Product Listing Received</h2>"
                f"<p>Hello {recipient_name},</p>"
                f"<p>Thank you for submitting your product listing <strong>{product_name}</strong> ({product_code}). Our team is reviewing your inventory.</p>"
                f"<p><a href='{action_url or default_action_url}'>View Your Listings</a></p>"
            )

        subject = f"Product Listing Received: {product_name} [{product_code}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "ProductSubmitted", context=context)

    @classmethod
    def send_rfq_buyer_confirmation(
        cls,
        to_email: str,
        rfq,
        items_list=None,
        recipient_name: str = "Valued Buyer",
    ) -> bool:
        """
        Sends an official RFQ confirmation email to the buyer after submitting an RFQ basket.
        """
        if not to_email:
            logger.warning("send_rfq_buyer_confirmation skipped: recipient email is missing.")
            return False

        frontend_base = cls.get_frontend_url()
        action_url = f"{frontend_base}/profile"

        ref = getattr(rfq, "reference", "") or "RFQ-PENDING"
        company_name = getattr(rfq, "company_name", "") or ""
        resolved_items = items_list if items_list is not None else (rfq.items.all() if hasattr(rfq, "items") else [])

        context = {
            "rfq": rfq,
            "items": resolved_items,
            "contact_person": recipient_name or getattr(rfq, "contact_person", "Valued Buyer"),
            "company_name": company_name,
            "action_url": action_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_rfq_buyer_confirmation.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for rfq buyer confirmation email, using fallback HTML: {e}")
            html_content = (
                f"<h2>Surplus Market RFQ Confirmation</h2>"
                f"<p>Hello {recipient_name},</p>"
                f"<p>Your quotation request <strong>{ref}</strong> has been received. Our team will review your requirements.</p>"
                f"<p><a href='{action_url}'>View Profile & RFQs</a></p>"
            )

        subject = f"Official RFQ Confirmation [{ref}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "RFQBuyerConfirm", context=context)

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

        frontend_base = cls.get_frontend_url()
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

        frontend_base = cls.get_frontend_url()
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
    def send_lot_submitted_email(
        cls,
        to_email: str,
        lot,
        recipient_name: str = "Valued Seller",
        action_url: str = ""
    ) -> bool:
        """
        Sends an email confirmation to the vendor when their bulk lot listing is submitted and under review.
        """
        if not to_email:
            logger.warning("send_lot_submitted_email skipped: recipient email is missing.")
            return False

        frontend_base = cls.get_frontend_url()
        default_action_url = f"{frontend_base}/profile"

        lot_title = (
            getattr(lot, "title", None)
            or (lot.get("title") if isinstance(lot, dict) else "")
            or "Bulk Lot Listing"
        )
        lot_number = (
            getattr(lot, "lot_number", None)
            or getattr(lot, "batch_id", None)
            or (lot.get("lot_number") if isinstance(lot, dict) else "")
            or "LOT-PENDING"
        )
        distinct_skus = getattr(lot, "number_of_distinct_skus", None) or (lot.get("number_of_distinct_skus") if isinstance(lot, dict) else None)
        total_units = getattr(lot, "total_units_quantity", None) or (lot.get("total_units_quantity") if isinstance(lot, dict) else None)
        ask_price = getattr(lot, "ask_price_surplus_payout", None) or (lot.get("ask_price_surplus_payout") if isinstance(lot, dict) else None)
        msrp = getattr(lot, "total_est_retail_value_msrp", None) or (lot.get("total_est_retail_value_msrp") if isinstance(lot, dict) else None)
        currency = getattr(lot, "currency", "USD") or "USD"
        inventory_location = getattr(lot, "inventory_location", "") or (lot.get("inventory_location") if isinstance(lot, dict) else "")

        context = {
            "user_name": recipient_name or "Valued Seller",
            "lot_title": lot_title,
            "lot_number": lot_number,
            "distinct_skus": distinct_skus,
            "total_units": total_units,
            "ask_price": ask_price,
            "msrp": msrp,
            "currency": currency,
            "inventory_location": inventory_location,
            "action_url": action_url or default_action_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_lot_submitted.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for lot submitted email, using fallback HTML: {e}")
            html_content = (
                f"<h2>Lot Listing Received</h2>"
                f"<p>Hello {recipient_name},</p>"
                f"<p>Thank you for submitting your lot listing <strong>{lot_title}</strong> ({lot_number}). Our team is reviewing your inventory.</p>"
                f"<p><a href='{action_url or default_action_url}'>View Your Listings</a></p>"
            )

        subject = f"Lot Listing Received: {lot_title} [{lot_number}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "LotSubmitted", context=context)

    @classmethod
    def notify_admin_lot_submitted(cls, seller_info: dict, lot) -> bool:
        """
        Notifies admin when a seller submits a bulk lot listing for review.
        """
        backend_base = os.getenv("BACKEND_URL", "https://surplus-backend-uhg0.onrender.com").rstrip("/")
        lot_id = getattr(lot, "id", None) or (lot.get("id") if isinstance(lot, dict) else "")
        admin_review_url = f"{backend_base}/admin/enquiries/lots/{lot_id}/detail/" if lot_id else f"{backend_base}/admin/enquiries/lots/"

        lot_title = (
            getattr(lot, "title", None)
            or (lot.get("title") if isinstance(lot, dict) else "")
            or "Bulk Lot Listing"
        )
        lot_number = (
            getattr(lot, "lot_number", None)
            or getattr(lot, "batch_id", None)
            or (lot.get("lot_number") if isinstance(lot, dict) else "")
            or "LOT-PENDING"
        )
        distinct_skus = getattr(lot, "number_of_distinct_skus", None) or (lot.get("number_of_distinct_skus") if isinstance(lot, dict) else None)
        total_units = getattr(lot, "total_units_quantity", None) or (lot.get("total_units_quantity") if isinstance(lot, dict) else None)
        ask_price = getattr(lot, "ask_price_surplus_payout", None) or (lot.get("ask_price_surplus_payout") if isinstance(lot, dict) else None)
        msrp = getattr(lot, "total_est_retail_value_msrp", None) or (lot.get("total_est_retail_value_msrp") if isinstance(lot, dict) else None)
        currency = getattr(lot, "currency", "USD") or "USD"
        inventory_location = getattr(lot, "inventory_location", "") or (lot.get("inventory_location") if isinstance(lot, dict) else "")

        seller_name = seller_info.get("name") or seller_info.get("full_name") or "Seller"
        seller_email = seller_info.get("email") or ""

        context = {
            "seller_name": seller_name,
            "seller_email": seller_email,
            "lot_title": lot_title,
            "lot_number": lot_number,
            "distinct_skus": distinct_skus,
            "total_units": total_units,
            "ask_price": ask_price,
            "msrp": msrp,
            "currency": currency,
            "inventory_location": inventory_location,
            "admin_review_url": admin_review_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_admin_lot_added.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for admin lot added email, using fallback HTML: {e}")
            html_content = (
                f"<h2>New Lot Submitted for Review</h2>"
                f"<p>Seller: <strong>{seller_name}</strong> ({seller_email})</p>"
                f"<p>Lot: <strong>{lot_title}</strong> ({lot_number})</p>"
                f"<p><a href='{admin_review_url}'>Review in Admin Dashboard</a></p>"
            )

        admin_emails = cls.get_admin_notification_emails()
        subject = f"New Lot Submitted for Review: {lot_title} [{lot_number}]"
        return cls.send_email(admin_emails, subject, html_content, "AdminLotReview", context=context)

    @classmethod
    def send_lot_approved_email(
        cls,
        to_email: str,
        lot,
        recipient_name: str = "Valued Seller",
        action_url: str = "",
        is_profile_complete: bool = True,
        profile_completion_percentage: int = 100,
        missing_fields_labels: list = None,
        profile_url: str = "",
    ) -> bool:
        """
        Sends an email notification to the vendor when their lot listing is approved.
        Includes profile completion alert if vendor profile is incomplete.
        """
        if not to_email:
            logger.warning("send_lot_approved_email skipped: recipient email is missing.")
            return False

        frontend_base = cls.get_frontend_url()
        default_action_url = f"{frontend_base}/profile"
        profile_link = profile_url or f"{frontend_base}/profile"

        lot_title = (
            getattr(lot, "title", None)
            or (lot.get("title") if isinstance(lot, dict) else "")
            or "Bulk Lot Listing"
        )
        lot_number = (
            getattr(lot, "lot_number", None)
            or getattr(lot, "batch_id", None)
            or (lot.get("lot_number") if isinstance(lot, dict) else "")
            or "LOT-APPROVED"
        )
        distinct_skus = getattr(lot, "number_of_distinct_skus", None) or (lot.get("number_of_distinct_skus") if isinstance(lot, dict) else None)
        total_units = getattr(lot, "total_units_quantity", None) or (lot.get("total_units_quantity") if isinstance(lot, dict) else None)
        ask_price = getattr(lot, "ask_price_surplus_payout", None) or (lot.get("ask_price_surplus_payout") if isinstance(lot, dict) else None)
        msrp = getattr(lot, "total_est_retail_value_msrp", None) or (lot.get("total_est_retail_value_msrp") if isinstance(lot, dict) else None)
        currency = getattr(lot, "currency", "USD") or "USD"
        inventory_location = getattr(lot, "inventory_location", "") or (lot.get("inventory_location") if isinstance(lot, dict) else "")

        context = {
            "user_name": recipient_name or "Valued Seller",
            "lot_title": lot_title,
            "lot_number": lot_number,
            "distinct_skus": distinct_skus,
            "total_units": total_units,
            "ask_price": ask_price,
            "msrp": msrp,
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
                "FinalTemplates/partials/email_partials/email_lot_approved.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for approved lot email, using fallback HTML: {e}")
            if not is_profile_complete:
                missing_str = f"<p><strong>Missing details:</strong> {', '.join(missing_fields_labels or [])}</p>" if missing_fields_labels else ""
                html_content = (
                    f"<h2>Your Lot Listing Has Been Approved!</h2>"
                    f"<p>Hello {recipient_name},</p>"
                    f"<p>Your bulk lot <strong>{lot_title}</strong> ({lot_number}) has been approved by admin review.</p>"
                    f"<div style='background-color:#fffbeb;border:1px solid #fde68a;padding:12px;border-radius:6px;'>"
                    f"<p style='color:#92400e;margin:0;'><strong>Action Required: Profile Incomplete ({profile_completion_percentage}%)</strong></p>"
                    f"<p style='color:#b45309;'>To list your lot for public visibility, you must complete all your user profile details.</p>"
                    f"{missing_str}"
                    f"<p><a href='{profile_link}' style='color:#d97706;font-weight:bold;'>Complete your profile to publish</a></p>"
                    f"</div>"
                )
            else:
                html_content = (
                    f"<h2>Your Lot Listing Has Been Approved!</h2>"
                    f"<p>Hello {recipient_name},</p>"
                    f"<p>Your bulk lot <strong>{lot_title}</strong> ({lot_number}) has been approved and is now live on Surplus Market.</p>"
                    f"<p><a href='{action_url or default_action_url}'>View your lot listing</a></p>"
                )

        subject = f"Lot Approved: {lot_title} [{lot_number}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "LotApproved", context=context)

    @classmethod
    def send_lot_declined_email(
        cls,
        to_email: str,
        lot,
        recipient_name: str = "Valued Seller",
        reason: str = "",
        action_url: str = ""
    ) -> bool:
        """
        Sends an email notification to the vendor when their lot listing is declined.
        """
        if not to_email:
            logger.warning("send_lot_declined_email skipped: recipient email is missing.")
            return False

        frontend_base = cls.get_frontend_url()
        default_action_url = f"{frontend_base}/profile"

        lot_title = (
            getattr(lot, "title", None)
            or (lot.get("title") if isinstance(lot, dict) else "")
            or "Bulk Lot Listing"
        )
        lot_number = (
            getattr(lot, "lot_number", None)
            or getattr(lot, "batch_id", None)
            or (lot.get("lot_number") if isinstance(lot, dict) else "")
            or "LOT-DECLINED"
        )
        distinct_skus = getattr(lot, "number_of_distinct_skus", None) or (lot.get("number_of_distinct_skus") if isinstance(lot, dict) else None)
        total_units = getattr(lot, "total_units_quantity", None) or (lot.get("total_units_quantity") if isinstance(lot, dict) else None)
        currency = getattr(lot, "currency", "USD") or "USD"

        context = {
            "user_name": recipient_name or "Valued Seller",
            "lot_title": lot_title,
            "lot_number": lot_number,
            "distinct_skus": distinct_skus,
            "total_units": total_units,
            "currency": currency,
            "reason": reason or "",
            "action_url": action_url or default_action_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_lot_declined.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for declined lot email, using fallback HTML: {e}")
            html_content = (
                f"<h2>Lot Listing Review Notice</h2>"
                f"<p>Hello {recipient_name},</p>"
                f"<p>Your bulk lot listing <strong>{lot_title}</strong> ({lot_number}) could not be approved at this time.</p>"
                f"<p>{reason or 'Please review your lot manifest and resubmit.'}</p>"
                f"<p><a href='{action_url or default_action_url}'>Review your listing</a></p>"
            )

        subject = f"Lot Listing Update: {lot_title} [{lot_number}] - Surplus Market"
        return cls.send_email(to_email, subject, html_content, "LotDeclined", context=context)

    @classmethod
    def email_linsting_confirm(cls, seller_email: str, product_title: str) -> bool:
        """Legacy helper for listing confirmation."""
        return cls.send_product_approved_email(
            to_email=seller_email,
            product={"product_name": product_title},
            recipient_name="Valued Seller"
        )

    @classmethod
    def get_admin_notification_emails(cls) -> list:
        """
        Resolves list of target email addresses for admin alerts:
        1. Reads ADMIN_NOTIFICATION_EMAIL from env/settings (supports comma-separated list).
        2. Includes active SuperAdmins and Admins from AdminDetails table.
        3. Deduplicates and cleans addresses.
        """
        recipients = []
        seen = set()

        def _add(email_str):
            clean = str(email_str or "").strip().strip("'\"")
            clean_lower = clean.lower()
            # Explicitly exclude mithun.coralbees from admin alerts per user directive
            if (
                clean
                and "@" in clean
                and "mithun.coralbees" not in clean_lower
                and clean_lower not in seen
            ):
                seen.add(clean_lower)
                recipients.append(clean)

        env_val = os.getenv("ADMIN_NOTIFICATION_EMAIL", getattr(settings, "ADMIN_NOTIFICATION_EMAIL", "") or "")
        if env_val:
            for em in str(env_val).split(","):
                _add(em)

        try:
            from .models import AdminDetails
            for adm in AdminDetails.objects.filter(status=True).exclude(email="").values_list("email", flat=True):
                clean_adm = str(adm).strip().strip("'\"")
                if not clean_adm.endswith("@example.com"):
                    _add(clean_adm)
        except Exception:
            pass

        if not recipients:
            recipients.append("contact@surplusmarket.com")

        return recipients

    @classmethod
    def get_admin_notification_email(cls) -> str:
        """Resolves primary target email for admin alerts."""
        emails = cls.get_admin_notification_emails()
        return emails[0] if emails else "contact@surplusmarket.com"

    @classmethod
    def send_contact_us_emails(cls, enquiry) -> dict:
        """
        Sends admin alert email and user confirmation email for a ContactUsEnquiry.
        Accepts model instance or dictionary.
        """
        full_name = getattr(enquiry, "full_name", None) or (enquiry.get("full_name") if isinstance(enquiry, dict) else "") or "Valued Customer"
        email = getattr(enquiry, "email", None) or (enquiry.get("email") if isinstance(enquiry, dict) else "")
        phone = getattr(enquiry, "phone", None) or (enquiry.get("phone") if isinstance(enquiry, dict) else "")
        enquiry_type = getattr(enquiry, "enquiry_type", None) or (enquiry.get("enquiry_type") if isinstance(enquiry, dict) else "") or "General Inquiry"
        message = getattr(enquiry, "message", None) or (enquiry.get("message") if isinstance(enquiry, dict) else "")
        enquiry_id = getattr(enquiry, "id", None) or (enquiry.get("id") if isinstance(enquiry, dict) else "")

        backend_base = os.getenv("BACKEND_URL", "https://surplus-backend-uhg0.onrender.com").rstrip("/")
        admin_url = f"{backend_base}/admin/enquiries/contact-us/"
        admin_emails = cls.get_admin_notification_emails()

        context = {
            "enquiry": enquiry,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "enquiry_type": enquiry_type,
            "message": message,
            "enquiry_id": enquiry_id,
            "admin_url": admin_url,
        }

        results = {"admin_email": False, "user_email": False}

        # 1. Admin Alert Email (sent to all active admins)
        try:
            admin_html = render_to_string(
                "FinalTemplates/partials/email_partials/email_contact_us_admin_alert.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for contact us admin alert email, using fallback HTML: {e}")
            admin_html = (
                f"<h2>New Contact Enquiry Received</h2>"
                f"<p><strong>Name:</strong> {full_name}</p>"
                f"<p><strong>Email:</strong> {email}</p>"
                f"<p><strong>Phone:</strong> {phone}</p>"
                f"<p><strong>Type:</strong> {enquiry_type}</p>"
                f"<p><strong>Message:</strong></p><blockquote>{message}</blockquote>"
                f"<p><a href='{admin_url}'>View in Admin Dashboard</a></p>"
            )

        admin_subject = f"New Contact Enquiry from {full_name} [{enquiry_type}]"
        results["admin_email"] = cls.send_email(admin_emails, admin_subject, admin_html, "ContactAdminAlert", context=context)

        # 2. User Confirmation Email
        if email:
            try:
                user_html = render_to_string(
                    "FinalTemplates/partials/email_partials/email_contact_us_user_confirmation.html",
                    context
                )
            except Exception as e:
                logger.warning(f"Template rendering failed for contact us user confirmation email, using fallback HTML: {e}")
                user_html = (
                    f"<h2>Thank You for Contacting Surplus Market</h2>"
                    f"<p>Hello {full_name},</p>"
                    f"<p>We have received your enquiry regarding {enquiry_type}. Our support team will review it and reply within 24 to 48 business hours.</p>"
                    f"<p><strong>Your Message:</strong></p><blockquote>{message}</blockquote>"
                )

            user_subject = f"We have received your enquiry - Surplus Market [Ref #{enquiry_id or 'General'}]"
            results["user_email"] = cls.send_email(email, user_subject, user_html, "ContactUserConfirm", context=context)

        return results

    @classmethod
    def send_partnership_emails(cls, enquiry) -> dict:
        """
        Sends admin alert email and partner confirmation email for a PartnershipEnquiry.
        Accepts model instance or dictionary.
        """
        name = getattr(enquiry, "name", None) or (enquiry.get("name") if isinstance(enquiry, dict) else "") or "Prospective Partner"
        email = getattr(enquiry, "email", None) or (enquiry.get("email") if isinstance(enquiry, dict) else "")
        business_location = getattr(enquiry, "business_location", None) or (enquiry.get("business_location") if isinstance(enquiry, dict) else "")
        partnership_interest = getattr(enquiry, "partnership_interest", None) or (enquiry.get("partnership_interest") if isinstance(enquiry, dict) else "") or "Strategic Partnership"
        subject_text = getattr(enquiry, "subject", None) or (enquiry.get("subject") if isinstance(enquiry, dict) else "")
        collaboration_details = getattr(enquiry, "collaboration_details", None) or (enquiry.get("collaboration_details") if isinstance(enquiry, dict) else "")
        enquiry_id = getattr(enquiry, "id", None) or (enquiry.get("id") if isinstance(enquiry, dict) else "")

        backend_base = os.getenv("BACKEND_URL", "https://surplus-backend-uhg0.onrender.com").rstrip("/")
        admin_url = f"{backend_base}/admin/enquiries/partnership/"
        admin_emails = cls.get_admin_notification_emails()

        context = {
            "enquiry": enquiry,
            "name": name,
            "email": email,
            "business_location": business_location,
            "partnership_interest": partnership_interest,
            "subject": subject_text,
            "collaboration_details": collaboration_details,
            "enquiry_id": enquiry_id,
            "admin_url": admin_url,
        }

        results = {"admin_email": False, "user_email": False}

        # 1. Admin Alert Email (sent to all active admins)
        try:
            admin_html = render_to_string(
                "FinalTemplates/partials/email_partials/email_partnership_admin_alert.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for partnership admin alert email, using fallback HTML: {e}")
            admin_html = (
                f"<h2>New Partnership Proposal Received</h2>"
                f"<p><strong>Partner Name:</strong> {name}</p>"
                f"<p><strong>Email:</strong> {email}</p>"
                f"<p><strong>Location:</strong> {business_location}</p>"
                f"<p><strong>Interest:</strong> {partnership_interest}</p>"
                f"<p><strong>Subject:</strong> {subject_text}</p>"
                f"<p><strong>Collaboration Details:</strong></p><blockquote>{collaboration_details}</blockquote>"
                f"<p><a href='{admin_url}'>Review in Admin Dashboard</a></p>"
            )

        admin_subject = f"New Partnership Proposal from {name} [{partnership_interest}]"
        results["admin_email"] = cls.send_email(admin_emails, admin_subject, admin_html, "PartnershipAdminAlert", context=context)

        # 2. Partner/User Confirmation Email
        if email:
            try:
                user_html = render_to_string(
                    "FinalTemplates/partials/email_partials/email_partnership_user_confirmation.html",
                    context
                )
            except Exception as e:
                logger.warning(f"Template rendering failed for partnership user confirmation email, using fallback HTML: {e}")
                user_html = (
                    f"<h2>Partnership Proposal Received</h2>"
                    f"<p>Hello {name},</p>"
                    f"<p>Thank you for reaching out regarding a partnership with Surplus Market. Our Business Development team is reviewing your proposal and will be in touch shortly.</p>"
                )

            user_subject = f"Thank You for Reaching Out - Surplus Market Partnership [#{enquiry_id or 'General'}]"
            results["user_email"] = cls.send_email(email, user_subject, user_html, "PartnershipUserConfirm", context=context)

        return results

    @classmethod
    def send_contact_form_email(cls, user_data: dict, form_type="query") -> bool:
        """Dispatches contact/partnership queries to admins."""
        if str(form_type).lower() in ("partnership", "partnership_enquiry"):
            res = cls.send_partnership_emails(user_data)
            return res.get("admin_email", False)
        res = cls.send_contact_us_emails(user_data)
        return res.get("admin_email", False)

    @classmethod
    def send_prize_email(cls, to_email: str, prize_name: str, certificate_path=None) -> bool:
        """Dispatches prize reward email with optional PDF certificate attachment."""
        html_content = f"<h2>Congratulations!</h2><p>You won: <strong>{prize_name}</strong> on Surplus Market!</p>"
        file_paths = [certificate_path] if certificate_path else None
        return cls.send_email_with_attachments(
            to_email, f"Surplus Reward: You won {prize_name}!", html_content, file_paths=file_paths
        )

    @classmethod
    def notify_admin_user_registered(cls, vendor) -> bool:
        """
        Notifies admin when a new user completes registration on the marketplace.
        Accepts VendorDetails instance or dict.
        """
        backend_base = os.getenv("BACKEND_URL", "https://surplus-backend-uhg0.onrender.com").rstrip("/")
        vendor_id = getattr(vendor, "vendor_id", None) or (vendor.get("vendor_id") if isinstance(vendor, dict) else "")
        raw_id = getattr(vendor, "id", None) or (vendor.get("id") if isinstance(vendor, dict) else "")
        if not vendor_id and raw_id:
            vendor_id = f"USR-{int(raw_id):04d}"

        email = getattr(vendor, "email", None) or (vendor.get("email") if isinstance(vendor, dict) else "")
        username = getattr(vendor, "username", None) or (vendor.get("username") if isinstance(vendor, dict) else "")
        full_name = getattr(vendor, "full_name", None) or (vendor.get("full_name") if isinstance(vendor, dict) else "") or username or "New User"
        phone = getattr(vendor, "mobile_number", None) or (vendor.get("mobile_number") if isinstance(vendor, dict) else "")
        user_type = getattr(vendor, "user_type", None) or (vendor.get("user_type") if isinstance(vendor, dict) else "BUYER")
        account_entity_type = getattr(vendor, "account_entity_type", None) or (vendor.get("account_entity_type") if isinstance(vendor, dict) else "COMPANY")
        company_name = getattr(vendor, "company_name", None) or (vendor.get("company_name") if isinstance(vendor, dict) else "")
        country = getattr(vendor, "country", None) or (vendor.get("country") if isinstance(vendor, dict) else "United Arab Emirates")
        business_location = getattr(vendor, "business_location", None) or (vendor.get("business_location") if isinstance(vendor, dict) else "")
        business_address = getattr(vendor, "business_address", None) or (vendor.get("business_address") if isinstance(vendor, dict) else "")
        business_type = getattr(vendor, "business_type", None) or (vendor.get("business_type") if isinstance(vendor, dict) else "")
        tax_registration_number = getattr(vendor, "tax_registration_number", None) or (vendor.get("tax_registration_number") if isinstance(vendor, dict) else "")

        cats = getattr(vendor, "category_interested_list", None) or []
        if not cats and hasattr(vendor, "category_interested"):
            cats = vendor.category_interested if isinstance(vendor.category_interested, list) else [str(vendor.category_interested)]
        elif isinstance(vendor, dict):
            cats = vendor.get("category_interested", [])
            if isinstance(cats, str):
                cats = [c.strip() for c in cats.split(",") if c.strip()]
        categories_str = ", ".join(cats) if cats else ""

        from django.utils import timezone
        registered_at = getattr(vendor, "created_at", None)
        if registered_at:
            reg_time_str = registered_at.strftime("%b %d, %Y %I:%M %p UTC")
        else:
            reg_time_str = timezone.now().strftime("%b %d, %Y %I:%M %p UTC")

        admin_url = f"{backend_base}/admin/users/?q={email}" if email else f"{backend_base}/admin/users/"
        admin_emails = cls.get_admin_notification_emails()

        context = {
            "vendor": vendor,
            "vendor_id": vendor_id,
            "username": username,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "user_type": user_type,
            "account_entity_type": account_entity_type,
            "company_name": company_name,
            "country": country,
            "business_location": business_location,
            "business_address": business_address,
            "business_type": business_type,
            "tax_registration_number": tax_registration_number,
            "categories_str": categories_str,
            "registered_at": reg_time_str,
            "admin_url": admin_url,
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_admin_user_registered.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for admin user registration alert: {e}")
            html_content = (
                f"<h2>New User Registered: {full_name}</h2>"
                f"<p>User ID: <strong>{vendor_id}</strong> | Username: <strong>@{username}</strong></p>"
                f"<p>Email: <strong>{email}</strong> | Phone: <strong>{phone}</strong></p>"
                f"<p>User Type: <strong>{user_type}</strong> | Entity Type: <strong>{account_entity_type}</strong></p>"
                f"<p>Company: <strong>{company_name or '-'}</strong> | Business Type: <strong>{business_type or '-'}</strong></p>"
                f"<p>Country: <strong>{country}</strong> | Location: <strong>{business_location or '-'}</strong></p>"
                f"<p>Address: <strong>{business_address or '-'}</strong></p>"
                f"<p>TRN: <strong>{tax_registration_number or '-'}</strong></p>"
                f"<p>Categories: <strong>{categories_str or '-'}</strong></p>"
                f"<p><a href='{admin_url}'>View User in Admin Portal</a></p>"
            )

        subject = f"New User Registration: {full_name} [{vendor_id}]"
        return cls.send_email(admin_emails, subject, html_content, "AdminUserRegistered", context=context)

    @classmethod
    def send_profile_completion_reminder_email(cls, vendor) -> bool:
        """
        Sends an email reminder to a vendor with an incomplete profile (low completion score)
        instructing them to complete missing details so their products can be listed live.
        """
        email = getattr(vendor, "email", "")
        if not email or email.endswith(".local"):
            return False

        frontend_base = cls.get_frontend_url()
        profile_url = f"{frontend_base}/profile"
        user_name = getattr(vendor, "full_name", "") or getattr(vendor, "company_name", "") or "Valued Seller"
        company_name = getattr(vendor, "company_name", "")

        details = vendor.get_profile_completion_details() if hasattr(vendor, "get_profile_completion_details") else {}
        percentage = details.get("percentage", 65)
        raw_missing = details.get("missing_fields_labels", [])
        excluded_labels = {
            "tax / gst registration number", "tax registration number", "tax registration number (trn)", "trn",
            "interested categories", "category interested",
            "company name"
        }
        missing_fields_labels = [
            lbl for lbl in raw_missing
            if lbl.strip().lower() not in excluded_labels
        ]

        context = {
            "user_name": user_name,
            "company_name": company_name,
            "profile_completion_percentage": percentage,
            "missing_fields_labels": missing_fields_labels,
            "profile_url": profile_url,
            "support_email": "contact@surplusmarket.com",
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_vendor_profile_completion_reminder.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for profile completion reminder email, using fallback: {e}")
            missing_html = "".join([f"<li>{f}</li>" for f in missing_fields_labels])
            html_content = (
                f"<h2>Action Required: Complete Your Vendor Profile</h2>"
                f"<p>Hello {user_name},</p>"
                f"<p>Your profile is currently {percentage}% complete. In order to list and publish your inventory for corporate buyers on Surplus Market, please complete the following details:</p>"
                f"<ul>{missing_html}</ul>"
                f"<p><a href='{profile_url}' style='background:#2563eb;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;font-weight:bold;'>Complete My Profile</a></p>"
            )

        subject = "Action Required: Complete Your Vendor Profile to List Your Products - Surplus Market"
        return cls.send_email(email, subject, html_content, "ProfileCompletionReminder", context=context)

    @classmethod
    def send_product_info_incomplete_email(cls, vendor, incomplete_products: list, total_count: int = 0) -> bool:
        """
        Sends an email notice to a vendor indicating their products have missing/incomplete specifications
        (such as Model Number, Brand, Dimensions, Origin Country).
        """
        email = getattr(vendor, "email", "")
        if not email or email.endswith(".local") or not incomplete_products:
            return False

        frontend_base = cls.get_frontend_url()
        action_url = f"{frontend_base}/profile"
        user_name = getattr(vendor, "full_name", "") or getattr(vendor, "company_name", "") or "Valued Seller"
        company_name = getattr(vendor, "company_name", "")

        context = {
            "user_name": user_name,
            "company_name": company_name,
            "incomplete_products": incomplete_products,
            "total_incomplete_count": len(incomplete_products),
            "total_products_count": total_count or len(incomplete_products),
            "action_url": action_url,
            "support_email": "contact@surplusmarket.com",
        }

        try:
            html_content = render_to_string(
                "FinalTemplates/partials/email_partials/email_vendor_product_info_incomplete.html",
                context
            )
        except Exception as e:
            logger.warning(f"Template rendering failed for product info incomplete email, using fallback: {e}")
            items_html = "".join([
                f"<li><strong>{p.get('product_name')}</strong> ({p.get('product_id')}) - Missing: {', '.join(p.get('missing_fields', []))}</li>"
                for p in incomplete_products[:8]
            ])
            html_content = (
                f"<h2>Action Needed: Complete Missing Product Specifications</h2>"
                f"<p>Hello {user_name},</p>"
                f"<p>We noticed that {len(incomplete_products)} of your product listings are missing essential technical specifications:</p>"
                f"<ul>{items_html}</ul>"
                f"<p><a href='{action_url}' style='background:#0f766e;color:#fff;padding:10px 20px;text-decoration:none;border-radius:6px;font-weight:bold;'>Update Product Specifications</a></p>"
            )

        subject = "Action Needed: Complete Missing Product Information for Your Listings - Surplus Market"
        return cls.send_email(email, subject, html_content, "ProductInfoIncomplete", context=context)


# Backwards compatibility alias
EmailNotificationService = EmailService


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


def create_admin_notification(
    title,
    message,
    notification_type="SYSTEM",
    action_url="",
    target_admin=None,
    for_superadmins_only=False,
):
    """
    Creates an AdminNotification record for admin staff or SuperAdmins.
    - target_admin: Specific AdminDetails instance or None (broadcast)
    - for_superadmins_only: Boolean flag to restrict visibility to SuperAdmins
    - notification_type: ADMIN_REGISTRATION, APPROVAL, ENQUIRY, LISTING, SYSTEM
    """
    from .models import AdminDetails, AdminNotification
    import logging
    _logger = logging.getLogger(__name__)

    admin_obj = None
    if isinstance(target_admin, AdminDetails):
        admin_obj = target_admin
    elif target_admin:
        adm_str = str(target_admin).strip()
        if adm_str.isdigit():
            admin_obj = AdminDetails.objects.filter(id=int(adm_str)).first()
        elif adm_str.upper().startswith("ADM-") and adm_str[4:].isdigit():
            admin_obj = AdminDetails.objects.filter(id=int(adm_str[4:])).first()
        if not admin_obj:
            admin_obj = AdminDetails.objects.filter(email__iexact=adm_str).first()
        if not admin_obj:
            admin_obj = AdminDetails.objects.filter(username__iexact=adm_str).first()

    valid_types = ("ADMIN_REGISTRATION", "USER_REGISTRATION", "APPROVAL", "ENQUIRY", "LISTING", "RFQ", "SYSTEM")
    n_type = str(notification_type).upper()
    if n_type not in valid_types:
        n_type = "SYSTEM"

    notification = AdminNotification.objects.create(
        admin=admin_obj,
        for_superadmins_only=for_superadmins_only,
        title=title,
        message=message,
        notification_type=n_type,
        action_url=action_url or "",
        is_read=False,
    )
    _logger.info(f"[AdminNotification] Created ID {notification.id} ({n_type}): {title}")
    return notification


def notify_new_user_registration(vendor):
    """
    Central handler triggered whenever a new user registers:
    1. Creates in-app AdminNotification for SuperAdmins and admin staff.
    2. Sends admin alert email to ADMIN_NOTIFICATION_EMAIL.
    3. Sends welcome email to the newly registered user.
    4. Creates in-app VendorNotification welcoming user.
    """
    import logging
    logger = logging.getLogger(__name__)

    vendor_id = getattr(vendor, "vendor_id", "") or (f"USR-{vendor.id:04d}" if getattr(vendor, "id", None) else "")
    full_name = getattr(vendor, "full_name", "").strip() or getattr(vendor, "username", "User")
    user_type = getattr(vendor, "user_type", "BUYER")
    email = getattr(vendor, "email", "")
    country = getattr(vendor, "country", "") or "UAE"
    company_name = getattr(vendor, "company_name", "") or ""
    business_location = getattr(vendor, "business_location", "") or ""

    # 1. In-app Admin Notification
    try:
        company_tag = f" ({company_name})" if company_name else ""
        location_tag = country
        if business_location and business_location != country:
            location_tag = f"{country} - {business_location}"

        create_admin_notification(
            title=f"New User Registration: {full_name}{company_tag}",
            message=f"New {user_type} account ({vendor_id}) registered: {email} from {location_tag}.",
            notification_type="USER_REGISTRATION",
            action_url=f"/admin/users/?q={email}" if email else "/admin/users/",
            for_superadmins_only=False
        )
    except Exception as e:
        logger.error(f"Failed to create AdminNotification for new user {getattr(vendor, 'id', '')}: {e}")

    # 2. Admin Alert Email
    try:
        EmailService.notify_admin_user_registered(vendor)
    except Exception as e:
        logger.error(f"Failed to send admin email alert for new user {getattr(vendor, 'id', '')}: {e}")

    # 3. User Welcome Email
    try:
        if email:
            first_name = getattr(vendor, "first_name", "") or full_name
            EmailService.send_signup_welcome(to_email=email, first_name=first_name, vendor=vendor)
    except Exception as e:
        logger.error(f"Failed to send welcome email to user {email}: {e}")

    # 4. In-app Vendor Notification
    try:
        create_vendor_notification(
            vendor=vendor,
            title="Welcome to Surplus Market!",
            message=f"Your account {vendor_id} has been registered successfully. You can now explore surplus listings, RFQs, and auctions.",
            notification_type="SYSTEM",
            action_url="/profile"
        )
    except Exception as e:
        logger.error(f"Failed to create VendorNotification for user {getattr(vendor, 'id', '')}: {e}")


def align_vendor_sequence():
    """
    Ensures postgres vendor_details_id_seq matches the current state of VendorDetails:
    - If 0 vendors exist, resets sequence to 1 with is_called=False (so next insert gets 1).
    - If vendors exist, sets sequence to max(id) with is_called=True (so next insert gets max(id)+1).
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from django.db import connection
        from .models import VendorDetails
        with connection.cursor() as cursor:
            max_id = VendorDetails.objects.order_by("-id").values_list("id", flat=True).first()
            if not max_id:
                cursor.execute("SELECT setval('vendor_details_id_seq', 1, false);")
                logger.info("[Sequence] vendor_details_id_seq reset to 1 (table empty).")
                return 1
            else:
                cursor.execute("SELECT setval('vendor_details_id_seq', %s, true);", [max_id])
                logger.info(f"[Sequence] vendor_details_id_seq aligned to {max_id}.")
                return max_id
    except Exception as e:
        logger.error(f"Failed to align vendor_details_id_seq: {e}")
        return None



