"""Tests for notification Celery tasks — real Celery eager + locmem email."""

import uuid

import pytest
from django.core import mail

from apps.notifications.models import Notification
from apps.notifications.tasks import (
    send_application_received_email,
    send_status_update_email,
)
from tests.factories import ApplicationFactory


@pytest.mark.django_db
class TestSendApplicationReceivedEmail:
    def test_sends_email_to_applicant(self):
        app = ApplicationFactory()
        mail.outbox.clear()
        send_application_received_email(str(app.id))
        assert len(mail.outbox) == 1
        assert app.applicant.email in mail.outbox[0].to

    def test_subject_contains_job_title(self):
        app = ApplicationFactory()
        mail.outbox.clear()
        send_application_received_email(str(app.id))
        assert app.job.title in mail.outbox[0].subject

    def test_creates_notification_record(self):
        app = ApplicationFactory()
        send_application_received_email(str(app.id))
        assert Notification.objects.filter(
            user=app.applicant,
            type=Notification.Type.APPLICATION_RECEIVED,
        ).exists()

    def test_nonexistent_app_does_not_crash(self):
        fake_id = str(uuid.uuid4())
        mail.outbox.clear()
        send_application_received_email(fake_id)
        assert len(mail.outbox) == 0

    def test_invalid_uuid_does_not_retry(self):
        mail.outbox.clear()
        send_application_received_email("not-a-uuid")
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestSendStatusUpdateEmail:
    def test_sends_email_with_status_change(self):
        app = ApplicationFactory()
        mail.outbox.clear()
        send_status_update_email(str(app.id), "applied", "reviewing")
        assert len(mail.outbox) == 1
        assert "status has been updated" in mail.outbox[0].subject

    def test_creates_notification_record(self):
        app = ApplicationFactory()
        send_status_update_email(str(app.id), "applied", "reviewing")
        notif = Notification.objects.filter(
            user=app.applicant,
            type=Notification.Type.STATUS_CHANGED,
        ).first()
        assert notif is not None
        assert notif.metadata["old_status"] == "applied"
        assert notif.metadata["new_status"] == "reviewing"

    def test_invalid_status_does_not_retry(self):
        app = ApplicationFactory()
        mail.outbox.clear()
        send_status_update_email(str(app.id), "applied", "bogus_status")
        assert len(mail.outbox) == 0
