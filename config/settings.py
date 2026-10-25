"""
Django settings for surplus-backend project.
Configured with production-grade security, scalability, and performance optimizations.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env", override=True)

# Security Settings
SECRET_KEY = os.getenv(
    "SECRET_KEY", "django-insecure-default-key-change-in-production"
)

DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "t")

allowed_hosts_raw = os.getenv("ALLOWED_HOSTS", "*")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_raw.split(",") if host.strip()]
if "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("*")


# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    # Local apps
    "api.apps.ApiConfig",
    "AdminApp.apps.AdminappConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # High-priority CORS handling (must be first)
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # High-performance response compression
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "AdminApp.middleware.MaintenanceModeMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "AdminApp" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "AdminApp.context_processors.maintenance_mode_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database & Connection Pooling
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "600")),
            ssl_require="sslmode=require" in DATABASE_URL.lower(),
        )
    }
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
    DATABASES["default"]["OPTIONS"] = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# High-Performance Caching Layer
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "surplus-cache-layer",
        "TIMEOUT": 300,
        "OPTIONS": {
            "MAX_ENTRIES": 10000,
        },
    }
}


# High-Performance Session Storage & Cookie Security
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_AGE = 86400 * 7  # 7 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG  # True in production over HTTPS

CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG

# Security Headers & SSL Hardening (OWASP Top 10 Mitigation)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() in ("true", "1", "t")
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# Django REST Framework Settings
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "1000/min",
    },
}


# CORS & CSRF Settings (Allow All Origins Unconditionally)
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://surplusmarket.com",
    "https://www.surplusmarket.com",
    "https://surplus-frontend-staging.vercel.app",
    "https://surplus-backend-uhg0.onrender.com",
]



# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True


# Static & Media Assets
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "AdminApp" / "templates" / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Allow large manifest uploads and bulk lot submissions (No size limit for images or excel)
# ---------------------------------------------------------------------------
# Disable maximum memory and field count limits so large manifests (7,000+ SKUs)
# and multiple warehouse images upload without "RequestDataTooBig" exceptions.
_env_mem_size = os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE")
if _env_mem_size and _env_mem_size.strip().lower() not in ("none", "null", "unlimited", "0", ""):
    DATA_UPLOAD_MAX_MEMORY_SIZE = int(_env_mem_size)
else:
    DATA_UPLOAD_MAX_MEMORY_SIZE = None  # None = no limit (allows 15MB+ manifest payloads and massive files)

_env_file_size = os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE")
FILE_UPLOAD_MAX_MEMORY_SIZE = int(_env_file_size) if _env_file_size and _env_file_size.isdigit() else 104857600  # 100 MB stream threshold before disk spooling

_env_num_fields = os.getenv("DATA_UPLOAD_MAX_NUMBER_FIELDS")
if _env_num_fields and _env_num_fields.strip().lower() not in ("none", "null", "unlimited", "0", ""):
    DATA_UPLOAD_MAX_NUMBER_FIELDS = int(_env_num_fields)
else:
    DATA_UPLOAD_MAX_NUMBER_FIELDS = None  # None = no limit on field count

# Cloudflare R2 / AWS S3 Media Storage Configuration
USE_R2 = os.getenv("USE_R2", "False").lower() in ("true", "1", "t")
USE_S3 = os.getenv("USE_S3", "False").lower() in ("true", "1", "t") or bool(os.getenv("AWS_STORAGE_BUCKET_NAME"))

# Resolve AWS / R2 Credentials from environment
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("R2_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = (
    os.getenv("AWS_STORAGE_BUCKET_NAME")
    or os.getenv("AWS_S3_BUCKET_NAME")
    or os.getenv("R2_BUCKET_NAME")
    or "app-staging-media"
)
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME") or os.getenv("AWS_REGION")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or os.getenv("R2_ENDPOINT_URL")
AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN") or os.getenv("R2_CUSTOM_DOMAIN")
AWS_S3_SIGNATURE_VERSION = os.getenv("AWS_S3_SIGNATURE_VERSION", "s3v4")
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_EXPIRE = int(os.getenv("AWS_QUERYSTRING_EXPIRE", "604800"))
AWS_DEFAULT_ACL = None

# Activate S3/R2 storage backend if USE_S3 or USE_R2 is enabled
if USE_R2 or USE_S3:
    if "storages" not in INSTALLED_APPS:
        INSTALLED_APPS.append("storages")

    s3_options = {
        "location": "media",
        "querystring_expire": AWS_QUERYSTRING_EXPIRE,
        "signature_version": AWS_S3_SIGNATURE_VERSION,
        "file_overwrite": AWS_S3_FILE_OVERWRITE,
        "default_acl": AWS_DEFAULT_ACL,
    }
    if AWS_ACCESS_KEY_ID:
        s3_options["access_key"] = AWS_ACCESS_KEY_ID
    if AWS_SECRET_ACCESS_KEY:
        s3_options["secret_key"] = AWS_SECRET_ACCESS_KEY
    if AWS_STORAGE_BUCKET_NAME:
        s3_options["bucket_name"] = AWS_STORAGE_BUCKET_NAME
    if AWS_S3_REGION_NAME:
        s3_options["region_name"] = AWS_S3_REGION_NAME
    if AWS_S3_ENDPOINT_URL:
        s3_options["endpoint_url"] = AWS_S3_ENDPOINT_URL
    if AWS_S3_CUSTOM_DOMAIN:
        s3_options["custom_domain"] = AWS_S3_CUSTOM_DOMAIN

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": s3_options,
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email Configuration (Brevo HTTP API / SMTP)
EMAIL_BACKEND = "config.backends.BrevoHTTPEmailBackend"
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")

# Fallback SMTP Settings
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("true", "1", "t")
EMAIL_TIMEOUT = 10

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Surplus Market <noreply@surplusmarket.com>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", "noreply@surplusmarket.com")
ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", "contact@surplusmarket.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://surplusmarket.com").rstrip("/")

# Typesense Intelligent Search Configuration
TYPESENSE_ENABLED = os.getenv("TYPESENSE_ENABLED", "False").lower() in ("true", "1", "t")
TYPESENSE_HOST = os.getenv("TYPESENSE_HOST", "localhost")
TYPESENSE_PORT = int(os.getenv("TYPESENSE_PORT", "8108"))
TYPESENSE_PROTOCOL = os.getenv("TYPESENSE_PROTOCOL", "http")
TYPESENSE_API_KEY = os.getenv("TYPESENSE_API_KEY", "surplus_typesense_dev_key_123")
TYPESENSE_COLLECTION_NAME = os.getenv("TYPESENSE_COLLECTION_NAME", "surplus_listings")
TYPESENSE_TIMEOUT = float(os.getenv("TYPESENSE_TIMEOUT", "1.5"))



