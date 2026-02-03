"""
Domain verification token generation and validation.
"""

import secrets

from django.conf import settings
from django.utils import timezone


def generate_domain_verification_token():
    """Generate a cryptographically secure domain verification token."""
    return secrets.token_urlsafe(32)


def is_domain_token_expired(token_generated_at):
    """Check if a domain verification token has expired."""
    if token_generated_at is None:
        return True
    expiry_hours = getattr(settings, "COMPANY_DOMAIN_TOKEN_EXPIRY_HOURS", 48)
    expiry_time = token_generated_at + timezone.timedelta(hours=expiry_hours)
    return timezone.now() > expiry_time


def is_resend_on_cooldown(token_generated_at):
    """Check if domain verification token resend is on cooldown."""
    if token_generated_at is None:
        return False
    cooldown_minutes = getattr(settings, "COMPANY_DOMAIN_RESEND_COOLDOWN_MINUTES", 5)
    cooldown_time = token_generated_at + timezone.timedelta(minutes=cooldown_minutes)
    return timezone.now() < cooldown_time
