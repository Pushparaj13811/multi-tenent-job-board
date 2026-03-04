"""
Section 4 — Celery Task & Email Reliability.

4.1  Pydantic validation gates (bad payloads return early, no retry)
4.2  Happy path (correct email + Notification record)
4.3  close_expired_jobs (idempotent, only closes published+expired)
"""

import datetime

import pytest
from django.conf import settings
from django.core import mail

from apps.jobs.models import Job
from apps.notifications.models import Notification
from apps.notifications.tasks import (
    send_application_received_email,
    send_status_update_email,
)
from tests.factories import ApplicationFactory, JobFactory

# ═══════════════════════════════════════════════════════════════════════════
# 4.1  Pydantic validation gates
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPydanticValidationGates:
    """Bad payloads must cause early return, not a retry loop."""

    def test_received_email_with_non_uuid_string_returns_early(self):
        """Non-UUID application_id → task returns without sending email or retrying."""
        mail.outbox.clear()
        result = send_application_received_email("not-a-uuid")
        # Should return None (early exit), not raise
        assert result is None
        assert len(mail.outbox) == 0

    def test_received_email_with_nonexistent_uuid_returns_early(self):
        """Valid UUID format but no matching Application row → returns early."""
        import uuid

        mail.outbox.clear()
        result = send_application_received_email(str(uuid.uuid4()))
        assert result is None
        assert len(mail.outbox) == 0

    def test_status_update_email_with_invalid_status_returns_early(self):
        """Invalid status string → Pydantic rejects, task returns early."""
        import uuid

        mail.outbox.clear()
        result = send_status_update_email(
            str(uuid.uuid4()), "applied", "INVALID_STATUS"
        )
        assert result is None
        assert len(mail.outbox) == 0

    def test_status_update_email_with_non_uuid_returns_early(self):
        """Non-UUID application_id → task returns early."""
        mail.outbox.clear()
        result = send_status_update_email("bad-id", "applied", "reviewing")
        assert result is None
        assert len(mail.outbox) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 4.2  Happy path
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTaskHappyPath:
    """Both tasks deliver correct email and create correct Notification."""

    def test_application_received_sends_one_email_to_applicant(self):
        """send_application_received_email delivers exactly one email to the applicant."""
        app = ApplicationFactory()
        mail.outbox.clear()
        send_application_received_email(str(app.id))
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [app.applicant.email]
        assert app.job.title in mail.outbox[0].subject

    def test_application_received_creates_notification(self):
        """send_application_received_email creates one Notification record."""
        app = ApplicationFactory()
        before = Notification.objects.filter(user=app.applicant).count()
        send_application_received_email(str(app.id))
        after = Notification.objects.filter(user=app.applicant).count()
        assert after == before + 1
        notif = Notification.objects.filter(user=app.applicant).latest("created_at")
        assert notif.type == Notification.Type.APPLICATION_RECEIVED
        assert app.job.title in notif.title
        assert notif.metadata["application_id"] == str(app.id)

    def test_status_update_sends_one_email_to_applicant(self):
        """send_status_update_email delivers exactly one email to the applicant."""
        app = ApplicationFactory()
        mail.outbox.clear()
        send_status_update_email(str(app.id), "applied", "reviewing")
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [app.applicant.email]
        assert "status has been updated" in mail.outbox[0].subject

    def test_status_update_creates_notification(self):
        """send_status_update_email creates one Notification with correct metadata."""
        app = ApplicationFactory()
        before = Notification.objects.filter(user=app.applicant).count()
        send_status_update_email(str(app.id), "applied", "reviewing")
        after = Notification.objects.filter(user=app.applicant).count()
        assert after == before + 1
        notif = Notification.objects.filter(user=app.applicant).latest("created_at")
        assert notif.type == Notification.Type.STATUS_CHANGED
        assert notif.metadata["old_status"] == "applied"
        assert notif.metadata["new_status"] == "reviewing"

    def test_duplicate_call_creates_second_notification(self):
        """Re-running same task creates a duplicate Notification (caller's responsibility).

        Note: ApplicationFactory triggers the post_save signal which eagerly
        calls send_application_received_email, creating 1 notification already.
        Two explicit calls add 2 more, for a total of 3.
        """
        app = ApplicationFactory()
        before = Notification.objects.filter(
            user=app.applicant,
            type=Notification.Type.APPLICATION_RECEIVED,
        ).count()
        send_application_received_email(str(app.id))
        send_application_received_email(str(app.id))
        after = Notification.objects.filter(
            user=app.applicant,
            type=Notification.Type.APPLICATION_RECEIVED,
        ).count()
        assert after == before + 2, "Each call should create one more Notification."


# ═══════════════════════════════════════════════════════════════════════════
# 4.3  close_expired_jobs
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCloseExpiredJobs:
    """Periodic task closes only published+expired jobs; idempotent."""

    def test_closes_published_expired_jobs(self):
        """Published job past deadline gets closed."""
        from apps.jobs.tasks import close_expired_jobs

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        job = JobFactory(status="published", deadline=yesterday)
        close_expired_jobs()
        job.refresh_from_db()
        assert job.status == Job.Status.CLOSED

    def test_does_not_close_draft_expired(self):
        """Draft jobs past deadline are NOT closed (only published)."""
        from apps.jobs.tasks import close_expired_jobs

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        job = JobFactory(status="draft", deadline=yesterday)
        close_expired_jobs()
        job.refresh_from_db()
        assert job.status == Job.Status.DRAFT

    def test_does_not_close_already_closed(self):
        """Already-closed jobs remain closed."""
        from apps.jobs.tasks import close_expired_jobs

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        job = JobFactory(status="closed", deadline=yesterday)
        close_expired_jobs()
        job.refresh_from_db()
        assert job.status == Job.Status.CLOSED

    def test_does_not_close_published_future_deadline(self):
        """Published job with future deadline stays published."""
        from apps.jobs.tasks import close_expired_jobs

        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        job = JobFactory(status="published", deadline=tomorrow)
        close_expired_jobs()
        job.refresh_from_db()
        assert job.status == Job.Status.PUBLISHED

    def test_does_not_close_published_no_deadline(self):
        """Published job with no deadline stays published."""
        from apps.jobs.tasks import close_expired_jobs

        job = JobFactory(status="published", deadline=None)
        close_expired_jobs()
        job.refresh_from_db()
        assert job.status == Job.Status.PUBLISHED

    def test_idempotent_on_second_run(self):
        """Running twice produces no further changes after first pass."""
        from apps.jobs.tasks import close_expired_jobs

        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        job = JobFactory(status="published", deadline=yesterday)
        close_expired_jobs()
        result2 = close_expired_jobs()
        assert "0" in result2, "Second run should close 0 jobs."
        job.refresh_from_db()
        assert job.status == Job.Status.CLOSED

    def test_beat_schedule_contains_close_expired_jobs(self):
        """CELERY_BEAT_SCHEDULE has the 'close-expired-jobs' entry."""
        assert "close-expired-jobs" in settings.CELERY_BEAT_SCHEDULE
        entry = settings.CELERY_BEAT_SCHEDULE["close-expired-jobs"]
        assert entry["task"] == "apps.jobs.tasks.close_expired_jobs"


# ═══════════════════════════════════════════════════════════════════════════
# Gap tests — Pydantic schema edge cases & email content
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPydanticSchemaEdgeCases:
    """Additional Pydantic validation coverage."""

    def test_empty_string_application_id_returns_early(self):
        """Empty string application_id → Pydantic rejects, task returns early."""
        mail.outbox.clear()
        result = send_application_received_email("")
        assert result is None
        assert len(mail.outbox) == 0

    @pytest.mark.parametrize(
        "valid_status",
        ["applied", "reviewing", "shortlisted", "interview", "offered", "rejected", "withdrawn"],
    )
    def test_all_valid_statuses_accepted_by_pydantic(self, valid_status):
        """Every valid Application.Status value is accepted by StatusUpdateEmailPayload."""
        import uuid

        from apps.notifications.schemas import StatusUpdateEmailPayload

        payload = StatusUpdateEmailPayload(
            application_id=str(uuid.uuid4()),
            old_status="applied",
            new_status=valid_status,
        )
        assert payload.new_status == valid_status

    def test_integer_application_id_returns_early(self):
        """Integer application_id → Pydantic rejects, no email sent."""
        mail.outbox.clear()
        result = send_application_received_email(12345)
        assert result is None
        assert len(mail.outbox) == 0


@pytest.mark.django_db
class TestEmailContent:
    """Verify email content details beyond just delivery."""

    def test_received_email_from_address_is_default(self):
        """Application received email comes from DEFAULT_FROM_EMAIL."""
        app = ApplicationFactory()
        mail.outbox.clear()
        send_application_received_email(str(app.id))
        assert len(mail.outbox) == 1
        assert mail.outbox[0].from_email == settings.DEFAULT_FROM_EMAIL

    def test_status_update_email_contains_old_and_new_status(self):
        """Status update email body mentions the transition."""
        app = ApplicationFactory()
        mail.outbox.clear()
        send_status_update_email(str(app.id), "applied", "reviewing")
        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "applied" in body
        assert "reviewing" in body

    def test_received_email_body_contains_company_name(self):
        """Application received email body contains the company name."""
        app = ApplicationFactory()
        mail.outbox.clear()
        send_application_received_email(str(app.id))
        assert len(mail.outbox) == 1
        assert app.job.company.name in mail.outbox[0].body
