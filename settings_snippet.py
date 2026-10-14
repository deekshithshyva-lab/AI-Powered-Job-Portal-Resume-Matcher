"""Add/merge these into config/settings.py."""
import os

INSTALLED_APPS += [
    "rest_framework",
    "portal",
]

# IMPORTANT: set before your very first `migrate` (swapping later is painful).
AUTH_USER_MODEL = "portal.User"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "jobportal"),
        "USER": os.environ.get("POSTGRES_USER", "jobportal"),
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# Files. In production use private object storage (S3/GCS via django-storages) and signed URLs;
# resumes contain PII and must NOT be served from a public MEDIA_URL.
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "1000/hour", "resume_upload": "20/hour"},
}

# --- Celery / Redis ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True               # redeliver if a worker dies mid-task
CELERY_WORKER_PREFETCH_MULTIPLIER = 1      # fair dispatch for long NLP jobs
CELERY_TASK_SOFT_TIME_LIMIT = 120
CELERY_TASK_TIME_LIMIT = 150
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}  # must exceed longest task (acks_late + Redis)

# --- NLP ---
SPACY_MODEL = "en_core_web_sm"
# RESUME_SKILLS = ["python", "django", ...]   # optional: override the default skill taxonomy
