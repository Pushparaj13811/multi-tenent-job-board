"""Tests for Application signals — no mocking, uses real Celery eager + locmem email."""

import pytest
from django.core import mail

from tests.factories import ApplicationFactory


@pytest.mark.django_db
class TestOnApplicationCreated:
    def test_fires_on_new_application(self):
        """Creating a new application sends a 'received' email via signal → task."""
        mail.outbox.clear()
        ApplicationFactory()
        assert len(mail.outbox) == 1
        assert "Application received" in mail.outbox[0].subject

    def test_does_not_fire_on_update(self):
        """Updating an existing application does NOT re-send the 'received' email."""
        app = ApplicationFactory()
        mail.outbox.clear()
        app.cover_letter = "Updated cover letter"
        app.save()
        # No new "received" email — only the status change signal could fire,
        # but status didn't change, so no emails at all.
        received_emails = [e for e in mail.outbox if "Application received" in e.subject]
        assert len(received_emails) == 0


@pytest.mark.django_db
class TestOnStatusChange:
    def test_fires_when_status_changes(self):
        """Changing status sends a 'status updated' email via signal → task."""
        app = ApplicationFactory()
        mail.outbox.clear()
        app.status = "reviewing"
        app.save()
        status_emails = [e for e in mail.outbox if "status has been updated" in e.subject]
        assert len(status_emails) == 1

    def test_does_not_fire_when_status_unchanged(self):
        """Saving without changing status does NOT send a status update email."""
        app = ApplicationFactory()
        mail.outbox.clear()
        app.cover_letter = "Updated"
        app.save()
        status_emails = [e for e in mail.outbox if "status has been updated" in e.subject]
        assert len(status_emails) == 0

    def test_does_not_fire_on_new_application(self):
        """Creating a new application does NOT trigger the status-change signal."""
        mail.outbox.clear()
        ApplicationFactory()
        status_emails = [e for e in mail.outbox if "status has been updated" in e.subject]
        assert len(status_emails) == 0
