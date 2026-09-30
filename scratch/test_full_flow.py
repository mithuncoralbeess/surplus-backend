import urllib.request
import urllib.error
import json
import os
import sys

# Setup Django ORM
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from AdminApp.models import VendorOTP, VendorDetails
from AdminApp.models import VendorDetails as AdminVendorDetails

API_BASE = 'https://surplus-backend-uhg0.onrender.com'

print("1. Sending Registration OTP...")
req = urllib.request.Request(
    f'{API_BASE}/api/auth/register/send-otp/',
    data=json.dumps({
        'full_name': 'Test User Flow',
        'email': 'testflow1@example.com',
        'mobile_number': '1234567890'
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'accept': 'application/json'},
    method='POST'
)
try:
    res = urllib.request.urlopen(req)
    print('send-otp Status:', res.status)
except urllib.error.HTTPError as e:
    print('send-otp Status:', e.code)

# Wait a second for DB to sync
import time
time.sleep(2)

# Get OTP
otp_record = VendorOTP.objects.filter(email='testflow1@example.com').order_by('-created_at').first()
if not otp_record:
    print("NO OTP FOUND")
    sys.exit(1)
otp = otp_record.otp
print(f"OTP retrieved: {otp}")

print("2. Verifying Registration OTP...")
req2 = urllib.request.Request(
    f'{API_BASE}/api/auth/register/verify-otp/',
    data=json.dumps({
        'email': 'testflow1@example.com',
        'otp': otp
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'accept': 'application/json'},
    method='POST'
)
try:
    res2 = urllib.request.urlopen(req2)
    print('verify-reg Status:', res2.status)
    print(res2.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('verify-reg Status:', e.code)
    print(e.read().decode('utf-8'))

print("3. Verifying Login OTP (Auto-Login)...")
req3 = urllib.request.Request(
    f'{API_BASE}/api/auth/login/verify-otp/',
    data=json.dumps({
        'email': 'testflow1@example.com',
        'otp': otp
    }).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'accept': 'application/json'},
    method='POST'
)
try:
    res3 = urllib.request.urlopen(req3)
    print('verify-login Status:', res3.status)
    print(res3.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('verify-login Status:', e.code)
    print(e.read().decode('utf-8'))
