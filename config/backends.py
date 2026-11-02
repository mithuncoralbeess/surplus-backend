import logging
import os
import requests
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.smtp import EmailBackend as DjangoSMTPEmailBackend
from django.conf import settings

logger = logging.getLogger(__name__)


class BrevoHTTPEmailBackend(BaseEmailBackend):
    """
    Primary Brevo HTTP API email transport with automatic SMTP failover.
    If Brevo's REST API is unreachable, rate-limited, or missing an API key,
    automatically fails over to Django's SMTP backend (EMAIL_HOST / EMAIL_PORT)
    when SMTP credentials are configured.
    """

    def _send_via_smtp_failover(self, failed_messages):
        if not failed_messages:
            return 0
        smtp_user = getattr(settings, "EMAIL_HOST_USER", "")
        smtp_password = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        if not (smtp_user and smtp_password):
            return 0
        try:
            smtp_backend = DjangoSMTPEmailBackend(
                host=getattr(settings, "EMAIL_HOST", "smtp-relay.brevo.com"),
                port=getattr(settings, "EMAIL_PORT", 587),
                username=smtp_user,
                password=smtp_password,
                use_tls=getattr(settings, "EMAIL_USE_TLS", True),
                fail_silently=self.fail_silently,
                timeout=getattr(settings, "EMAIL_TIMEOUT", 10),
            )
            return smtp_backend.send_messages(failed_messages) or 0
        except Exception as exc:
            logger.warning("SMTP email failover also failed: %s", exc)
            if not self.fail_silently:
                raise
            return 0

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        api_key = getattr(settings, "BREVO_API_KEY", os.getenv("BREVO_API_KEY"))
        if not api_key:
            smtp_sent = self._send_via_smtp_failover(list(email_messages))
            if smtp_sent:
                return smtp_sent
            if not self.fail_silently:
                raise ValueError("BREVO_API_KEY is missing in settings and SMTP failover is not configured.")
            return 0

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        import email.utils
        sent = 0
        failed_for_smtp = []

        for msg in email_messages:
            html_content = None
            if hasattr(msg, "alternatives") and msg.alternatives:
                for alt in msg.alternatives:
                    if alt[1] == "text/html":
                        html_content = alt[0]
                        break

            from_name, from_addr = email.utils.parseaddr(msg.from_email)
            sender = {"email": from_addr}
            if from_name:
                sender["name"] = from_name

            to_list = []
            for addr in msg.to:
                t_name, t_addr = email.utils.parseaddr(addr)
                to_obj = {"email": t_addr}
                if t_name:
                    to_obj["name"] = t_name
                to_list.append(to_obj)

            plain_text = (msg.body or "").strip()
            if not plain_text and html_content:
                import re
                plain_text = re.sub(r"<[^>]+>", " ", html_content)
                plain_text = " ".join(plain_text.split()).strip()
            if not plain_text:
                plain_text = msg.subject or "Notification from Surplus Market"

            payload = {
                "sender": sender,
                "to": to_list,
                "subject": msg.subject,
                "textContent": plain_text,
            }

            # Set Reply-To header for deliverability & direct partner communication
            if hasattr(msg, "reply_to") and msg.reply_to:
                r_name, r_addr = email.utils.parseaddr(msg.reply_to[0])
                payload["replyTo"] = {
                    "email": r_addr or msg.reply_to[0],
                    "name": r_name or "Surplus Market Support",
                }
            else:
                payload["replyTo"] = {
                    "email": "contact@surplusmarket.com",
                    "name": "Surplus Market Support",
                }

            if html_content:
                payload["htmlContent"] = html_content
            else:
                payload["htmlContent"] = f"<p>{plain_text}</p>"

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                if response.status_code in (200, 201, 202):
                    sent += 1
                else:
                    logger.warning(
                        "Brevo HTTP API returned %s; queueing message for SMTP failover",
                        response.status_code,
                    )
                    failed_for_smtp.append(msg)
            except Exception as exc:
                logger.warning("Brevo HTTP API request failed (%s); queueing for SMTP failover", exc)
                failed_for_smtp.append(msg)

        if failed_for_smtp:
            smtp_sent = self._send_via_smtp_failover(failed_for_smtp)
            sent += smtp_sent

        return sent
