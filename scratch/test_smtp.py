import os
import django
from django.core.mail import send_mail

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

try:
    send_mail(
        subject="Test SMTP Connection",
        message="This is a test email to verify SMTP configuration.",
        from_email="noreply@surplusmarket.com",
        recipient_list=["mithunraj1590@gmail.com"],
        fail_silently=False,
    )
    print("Email sent successfully!")
except Exception as e:
    print(f"Failed to send email: {e}")
