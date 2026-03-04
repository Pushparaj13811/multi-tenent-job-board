"""Tests for Notification API endpoints."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.notifications.models import Notification
from tests.factories import NotificationFactory, UserFactory


def _notifications_url():
    return "/api/notifications/"


def _mark_read_url(notif_id):
    return f"/api/notifications/{notif_id}/read/"


def _mark_all_read_url():
    return "/api/notifications/mark-all-read/"


@pytest.mark.django_db
class TestListNotifications:
    def test_user_sees_own(self):
        user = UserFactory()
        NotificationFactory(user=user)
        NotificationFactory()  # other user
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(_notifications_url())
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_filter_by_is_read(self):
        user = UserFactory()
        NotificationFactory(user=user, is_read=True)
        NotificationFactory(user=user, is_read=False)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(_notifications_url(), {"is_read": "false"})
        assert len(response.data["results"]) == 1

    def test_includes_unread_count(self):
        user = UserFactory()
        NotificationFactory(user=user, is_read=False)
        NotificationFactory(user=user, is_read=False)
        NotificationFactory(user=user, is_read=True)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(_notifications_url())
        assert response.data["unread_count"] == 2

    def test_unauthenticated_gets_401(self):
        client = APIClient()
        response = client.get(_notifications_url())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestMarkRead:
    def test_mark_single_read(self):
        user = UserFactory()
        notif = NotificationFactory(user=user, is_read=False)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.patch(_mark_read_url(notif.id))
        assert response.status_code == status.HTTP_200_OK
        notif.refresh_from_db()
        assert notif.is_read is True

    def test_cannot_mark_other_users(self):
        notif = NotificationFactory(is_read=False)
        other = UserFactory()
        client = APIClient()
        client.force_authenticate(user=other)
        response = client.patch(_mark_read_url(notif.id))
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestMarkAllRead:
    def test_marks_all_and_returns_count(self):
        user = UserFactory()
        NotificationFactory(user=user, is_read=False)
        NotificationFactory(user=user, is_read=False)
        NotificationFactory(user=user, is_read=True)
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(_mark_all_read_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.data["marked_read"] == 2
        assert Notification.objects.filter(user=user, is_read=False).count() == 0
