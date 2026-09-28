# Surplus Backend (Django + PostgreSQL)

A robust Django REST API backend with PostgreSQL database support, multi-tier Admin Dashboard authentication (AdminApp), role management, and session invalidation.

---

## 🛠️ Tech Stack

- **Framework:** Python Django
- **Admin App:** Multi-tier role management (`AdminApp`)
- **API Toolkit:** Django REST Framework (DRF)
- **Database:** PostgreSQL (via `psycopg2-binary`)
- **CORS Management:** `django-cors-headers`
- **Environment Management:** `python-dotenv`

---

## 📁 Project Structure

```
surplus-backend/
├── .env                  # Local environment configuration
├── .env.example          # Sample environment template
├── requirements.txt      # Python dependencies
├── manage.py             # Django CLI
├── config/               # Project root settings & global URLs
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── AdminApp/             # Multi-Tier Admin Dashboard & Authentication
│   ├── admin.py          # Admin site registrations
│   ├── models.py         # AdminDetails & AdminPasswordResetOTP
│   ├── serializers.py    # Admin serializers & validation
│   ├── services.py       # EmailService (OTP dispatcher)
│   ├── views.py          # admin_register, admin_login, OTP reset, dashboards
│   ├── urls.py           # Admin routes
│   └── tests.py          # Comprehensive test suite
└── api/                  # General API app (items, health check)
    ├── admin.py
    ├── models.py
    ├── serializers.py
    ├── views.py
    └── urls.py
```

---

## 🔐 AdminApp Architecture

### Key Model: `AdminDetails`
- `username`, `email`, `first_name`, `last_name`
- `pass_word`: Salted SHA-256 hash string (`<hash>:<salt>`)
- `account_type`: `'SuperAdmin'`, `'Admin'`, `'XLSXAdmin'`, `'Vendor'`
- `status`: Active/inactive toggle
- `session_version`: Incrementing integer used to invalidate active sessions during password reset
- `web_is_active`: Controls global site maintenance state (`'live'`)

---

## 📡 API Endpoints

### 🔑 Admin Authentication & Management (`/api/admin/`)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/admin/register/` | Register new Admin / SuperAdmin |
| `POST` | `/api/admin/login/` | Admin login & role routing |
| `POST` | `/api/admin/logout/` | Flush admin session & logout |
| `GET` | `/api/admin/me/` | Current session admin profile |
| `POST` | `/api/admin/password-reset/` | Dispatches 6-digit OTP to email (10-min expiry) |
| `POST` | `/api/admin/verify-otp/` | Verifies OTP, updates password, increments `session_version` |
| `GET` | `/api/admin/dashboard/` | SuperAdmin & Admin dashboard data |
| `GET` | `/api/admin/xlsx-dashboard/` | XLSX Admin bulk management dashboard |
| `GET` | `/api/admin/vendor-index/` | Vendor portal index view |

---

### 🌐 General Endpoints (`/api/`)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/` | API index & overview |
| `GET` | `/api/health/` | Health check & DB connection status |
| `GET/POST` | `/api/items/` | Item management |
| `GET` | `/django-admin/` | Standard Django administration portal |

---

## 🚀 Running the Project

```powershell
# 1. Run migrations
.\.venv\Scripts\python.exe manage.py migrate

# 2. Run test suite
.\.venv\Scripts\python.exe manage.py test

# 3. Start development server
.\.venv\Scripts\python.exe manage.py runserver
```
