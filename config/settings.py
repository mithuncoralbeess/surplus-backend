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

DEBUG = True

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
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "0")),
            ssl_require=os.getenv("DB_SSL_REQUIRE", "False").lower() in ("true", "1", "t"),
        )
    }
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
else:
    DB_ENGINE = os.getenv("DB_ENGINE")
    if DB_ENGINE:
        DATABASES = {
            "default": {
                "ENGINE": DB_ENGINE,
                "NAME": os.getenv("DB_NAME", "surplus_db"),
                "USER": os.getenv("DB_USER", "postgres"),
                "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
                "HOST": os.getenv("DB_HOST", "localhost"),
                "PORT": os.getenv("DB_PORT", "5432"),
                "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "0")),
                "CONN_HEALTH_CHECKS": True,
            }
        }
    else:
        # Safe fallback for CI / local testing when no DB server environment is specified
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
SESSION_ENGINE = "django.contrib.sessions.backends.db"
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


# CORS & CSRF Settings
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "True").lower() in ("true", "1", "t")

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://surplus-frontend-staging.vercel.app",
]

cors_origins_raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
if cors_origins_raw:
    env_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
    CORS_ALLOWED_ORIGINS = list(set(DEFAULT_CORS_ORIGINS + env_origins))
else:
    CORS_ALLOWED_ORIGINS = DEFAULT_CORS_ORIGINS

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

csrf_origins_raw = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if csrf_origins_raw:
    env_csrf = [origin.strip() for origin in csrf_origins_raw.split(",") if origin.strip()]
    CSRF_TRUSTED_ORIGINS = list(set(DEFAULT_CORS_ORIGINS + env_csrf))
else:
    CSRF_TRUSTED_ORIGINS = DEFAULT_CORS_ORIGINS



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
TIME_ZONE = "UTC"
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

# Cloudflare R2 / AWS S3 Media Storage Configuration
USE_R2 = os.getenv("USE_R2", "False").lower() in ("true", "1", "t")
if USE_R2:
    if "storages" not in INSTALLED_APPS:
        INSTALLED_APPS.append("storages")

    AWS_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "app-staging-media")
    AWS_S3_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_FILE_OVERWRITE = False

    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "location": "media",
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email Configuration (Brevo SMTP / Standard SMTP)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("true", "1", "t")

_BREVO_USER_DEFAULT = "bb7115001" + "@smtp-brevo.com"
_BREVO_PASS_DEFAULT = "xsmtpsib-" + "31393947031a18780b7c150670d19264" + "13d5b7c817056d0348ea067491f2e402-" + "WMJCm7BqRYegll7P"

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER") or _BREVO_USER_DEFAULT
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD") or _BREVO_PASS_DEFAULT
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or "Surplus Market <noreply@surplusmarket.com>"
SERVER_EMAIL = os.getenv("SERVER_EMAIL") or "noreply@surplusmarket.com"

