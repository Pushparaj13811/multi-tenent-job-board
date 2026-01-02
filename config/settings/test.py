"""
Test settings — fast password hashing, eager Celery, in-memory email.
Real PostgreSQL and Redis are used (no mocking).
"""

import tempfile

from .base import *  # noqa: F401, F403

DEBUG = True

# Fast password hashing for tests (100x faster than PBKDF2)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# In-memory email backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Celery runs tasks synchronously in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable throttling in tests
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405

# Use temp directory for media files in tests
MEDIA_ROOT = tempfile.mkdtemp()

# Suppress log output during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["null"],
        "level": "CRITICAL",
    },
}
