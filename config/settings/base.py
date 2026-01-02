"""
Base settings shared across all environments.
"""

from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from config.env import env

# ── Paths ──
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Core ──
SECRET_KEY = env.SECRET_KEY
DEBUG = env.DEBUG
ALLOWED_HOSTS = env.ALLOWED_HOSTS

# ── Application Definition ──
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    "rest_framework_simplejwt.token_blacklist",
    # Local apps
    "apps.health",
    "apps.accounts",
    "apps.companies",
    "apps.jobs",
    "apps.applications",
    "apps.notifications",
    "apps.dashboard",
    # Frontend
    "frontend",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "middleware.request_logger.RequestLoggerMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "frontend.context_processors.frontend_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Database ──
_db_hosts = env.DATABASE_URL.hosts()
_db_host = _db_hosts[0] if _db_hosts else {}
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (env.DATABASE_URL.path or "/hireflow").lstrip("/"),
        "USER": _db_host.get("username") or "",
        "PASSWORD": _db_host.get("password") or "",
        "HOST": _db_host.get("host") or "localhost",
        "PORT": str(_db_host.get("port") or 5432),
    }
}

# ── Cache ──
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(env.REDIS_URL),
    }
}

# ── Password Validation ──
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalization ──
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static & Media ──
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── Default Primary Key ──
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Django REST Framework ──
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "common.pagination.HireFlowCursorPagination",
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "applications": "10/hour",
        "auth": "5/minute",
        "search": "30/minute",
    },
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ── SimpleJWT ──
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.JWT_ACCESS_TOKEN_LIFETIME_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.JWT_REFRESH_TOKEN_LIFETIME_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── Celery ──
CELERY_BROKER_URL = str(env.CELERY_BROKER_URL)
CELERY_RESULT_BACKEND = "django-db"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = env.CELERY_TASK_TIME_LIMIT
CELERY_TASK_SOFT_TIME_LIMIT = env.CELERY_TASK_SOFT_TIME_LIMIT
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "close-expired-jobs": {
        "task": "apps.jobs.tasks.close_expired_jobs",
        "schedule": crontab(hour=0, minute=0),
    },
}

# ── CORS ──
CORS_ALLOWED_ORIGINS = env.CORS_ALLOWED_ORIGINS

# ── Email ──
EMAIL_BACKEND = env.EMAIL_BACKEND
EMAIL_HOST = env.EMAIL_HOST
EMAIL_PORT = env.EMAIL_PORT
EMAIL_USE_TLS = env.EMAIL_USE_TLS
EMAIL_HOST_USER = env.EMAIL_HOST_USER
EMAIL_HOST_PASSWORD = env.EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL = env.DEFAULT_FROM_EMAIL

# ── drf-spectacular ──
SPECTACULAR_SETTINGS = {
    "TITLE": "HireFlow API",
    "DESCRIPTION": (
        "Multi-Tenant Job Board REST API.\n\n"
        "## Authentication\n"
        "Most endpoints require JWT authentication. "
        "Obtain tokens via `POST /api/auth/login/` and include "
        "`Authorization: Bearer <access_token>` in requests.\n\n"
        "## Roles\n"
        "- **Candidate**: Apply to jobs, track applications\n"
        "- **Recruiter**: Post jobs, manage applications, company admin\n\n"
        "## Pagination\n"
        "List endpoints use cursor-based pagination with `next`/`previous` URLs."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": [
        {"name": "Auth", "description": "Registration, login, JWT tokens, email verification"},
        {"name": "Jobs", "description": "Job listings with full-text search and filtering"},
        {"name": "Applications", "description": "Job applications with status workflow state machine"},
        {"name": "Companies", "description": "Company profiles and member management"},
        {"name": "Notifications", "description": "In-app notification management"},
        {"name": "Dashboard", "description": "Role-specific dashboard aggregations"},
        {"name": "Health", "description": "System health checks"},
    ],
    "COMPONENT_SPLIT_REQUEST": True,
}

# ── WhiteNoise (static file serving) ──
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ── Company Verification ──
COMPANY_DOMAIN_TOKEN_EXPIRY_HOURS = 48
COMPANY_DOMAIN_RESEND_COOLDOWN_MINUTES = 5

# ── Upload Limits ──
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# ── Authentication backends (session auth for frontend) ──
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"
