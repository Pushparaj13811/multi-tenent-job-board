from django.conf import settings
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from .tokens import make_email_verification_token


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def send_verification_email_on_register(sender, instance, created, **kwargs):
    """Send a verification email when a new user registers."""
    if created and not instance.is_email_verified:
        token = make_email_verification_token(str(instance.id))
        send_mail(
            subject="HireFlow — Verify your email",
            message=f"Use this token to verify your email: {token}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[instance.email],
            fail_silently=False,
        )
