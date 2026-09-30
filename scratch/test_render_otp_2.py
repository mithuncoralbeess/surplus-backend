import urllib.request
import urllib.error
import json

req = urllib.request.Request(
    'https://surplus-backend-uhg0.onrender.com/api/auth/register/send-otp/',
    data=json.dumps({'full_name': 'Test User', 'email': 'mithunraj1590@gmail.com', 'mobile_number': '9876543210'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
try:
    res = urllib.request.urlopen(req)
    print('Status:', res.status)
    print(res.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print('Status:', e.code)
    print(e.read().decode('utf-8'))
