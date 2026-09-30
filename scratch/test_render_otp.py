import urllib.request
import urllib.error
import json

payload = json.dumps({
    "full_name": "Postman User",
    "email": "mithunraj1590@gmail.com",
    "mobile_number": "9876543210"
}).encode('utf-8')

urls = [
    "https://surplus-backend-uhg0.onrender.com/api/auth/register/send-otp/",
    "https://surplus-backend-uhg0.onrender.com/send-registration-otp/"
]

for url in urls:
    print(f"\nTesting POST to {url} ...")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        res = urllib.request.urlopen(req)
        print("STATUS:", res.status)
        print("BODY:", res.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print("HTTP ERROR CODE:", e.code)
        print("HEADERS:", dict(e.headers))
        print("BODY:", e.read().decode('utf-8'))
    except Exception as exc:
        print("OTHER EXCEPTION:", exc)
