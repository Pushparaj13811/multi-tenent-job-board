from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Application


@receiver(post_save, sender=Application)
def on_application_created(sender, instance, created, **kwargs):
    """Fire Celery task when a new application is created."""
    if created:
        from apps.notifications.tasks import send_application_received_email

        send_application_received_email.delay(str(instance.id))


@receiver(pre_save, sender=Application)
def on_status_change(sender, instance, **kwargs):
    """Fire Celery task when application status changes."""
    if instance.pk is None:
        return

    try:
        old = Application.objects.get(pk=instance.pk)
    except Application.DoesNotExist:
        return

    if old.status != instance.status:
        from apps.notifications.tasks import send_status_update_email

        send_status_update_email.delay(
            str(instance.id), old.status, instance.status
        )
