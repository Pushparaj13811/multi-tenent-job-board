"""
Notification Celery tasks with Pydantic payload validation.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from pydantic import ValidationError

from celery import shared_task

from .schemas import ApplicationEmailPayload, StatusUpdateEmailPayload

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_application_received_email(self, application_id):
    """Notify candidate their application was received."""
    try:
        payload = ApplicationEmailPayload(application_id=application_id)
    except ValidationError:
        logger.error("Invalid payload for send_application_received_email: %s", application_id)
        return

    from apps.applications.models import Application
    from apps.notifications.models import Notification

    try:
        application = Application.objects.select_related(
            "applicant", "job__company"
        ).get(id=payload.application_id)
    except Application.DoesNotExist:
        logger.warning("Application %s not found, skipping email.", payload.application_id)
        return

    try:
        send_mail(
            subject=f"Application received — {application.job.title}",
            message=(
                f"Hi {application.applicant.first_name}, your application to "
                f"{application.job.company.name} for {application.job.title} "
                f"has been received."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.applicant.email],
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc

    Notification.objects.create(
        user=application.applicant,
        type=Notification.Type.APPLICATION_RECEIVED,
        title=f"Application received — {application.job.title}",
        message=(
            f"Your application to {application.job.company.name} "
            f"for {application.job.title} has been received."
        ),
        metadata={"application_id": str(application.id)},
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_status_update_email(self, application_id, old_status, new_status):
    """Notify candidate when their application status changes."""
    try:
        payload = StatusUpdateEmailPayload(
            application_id=application_id,
            old_status=old_status,
            new_status=new_status,
        )
    except ValidationError:
        logger.error(
            "Invalid payload for send_status_update_email: %s, %s, %s",
            application_id, old_status, new_status,
        )
        return

    from apps.applications.models import Application
    from apps.notifications.models import Notification

    try:
        application = Application.objects.select_related(
            "applicant", "job__company"
        ).get(id=payload.application_id)
    except Application.DoesNotExist:
        logger.warning("Application %s not found, skipping email.", payload.application_id)
        return

    try:
        send_mail(
            subject=f"Your application status has been updated — {application.job.title}",
            message=(
                f"Hi {application.applicant.first_name}, your application status "
                f"changed from {payload.old_status} to {payload.new_status}."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.applicant.email],
        )
    except Exception as exc:
        raise self.retry(exc=exc) from exc

    Notification.objects.create(
        user=application.applicant,
        type=Notification.Type.STATUS_CHANGED,
        title=f"Status updated — {application.job.title}",
        message=(
            f"Your application status changed from "
            f"{payload.old_status} to {payload.new_status}."
        ),
        metadata={
            "application_id": str(application.id),
            "old_status": payload.old_status,
            "new_status": payload.new_status,
        },
    )
