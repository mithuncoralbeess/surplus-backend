import os
import requests
from django.core.mail.backends.base import BaseEmailBackend
from django.conf import settings

class BrevoHTTPEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
            
        api_key = getattr(settings, 'BREVO_API_KEY', os.getenv('BREVO_API_KEY'))
        if not api_key:
            if not self.fail_silently:
                raise ValueError("BREVO_API_KEY is missing in settings.")
            return 0

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json"
        }

        import email.utils
        sent = 0
        for msg in email_messages:
            html_content = None
            if hasattr(msg, 'alternatives') and msg.alternatives:
                for alt in msg.alternatives:
                    if alt[1] == 'text/html':
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

            payload = {
                "sender": sender,
                "to": to_list,
                "subject": msg.subject,
                "textContent": msg.body,
            }
            
            if html_content:
                payload["htmlContent"] = html_content
            else:
                payload["htmlContent"] = f"<p>{msg.body}</p>"

            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                if response.status_code in (200, 201, 202):
                    sent += 1
                else:
                    if not self.fail_silently:
                        response.raise_for_status()
            except Exception:
                if not self.fail_silently:
                    raise
        return sent
