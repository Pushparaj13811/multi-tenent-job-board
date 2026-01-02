"""
Development settings — DEBUG=True, console email backend.
"""

from .base import *  # noqa: F401, F403

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
