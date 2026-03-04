"""Tests for Notification model."""

import pytest

from apps.notifications.models import Notification
from tests.factories import NotificationFactory


@pytest.mark.django_db
class TestNotificationModel:
    def test_create_notification(self):
        notif = NotificationFactory()
        assert Notification.objects.filter(id=notif.id).exists()

    def test_default_is_read_false(self):
        notif = NotificationFactory()
        assert notif.is_read is False

    def test_metadata_default_empty_dict(self):
        notif = NotificationFactory()
        assert notif.metadata == {}

    def test_type_choices(self):
        choices = {c[0] for c in Notification.Type.choices}
        assert "application_received" in choices
        assert "status_changed" in choices
        assert "job_expiring" in choices
