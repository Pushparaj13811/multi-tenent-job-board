"""
Tests for the custom User model.
"""

import uuid

import pytest

from apps.accounts.models import User


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_with_email(self):
        """User can be created with email as the primary identifier."""
        user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123!",
        )
        assert user.email == "test@example.com"
        assert user.check_password("testpass123!")

    def test_email_is_username_field(self):
        """email is the USERNAME_FIELD for authentication."""
        assert User.USERNAME_FIELD == "email"

    def test_default_role_is_candidate(self):
        """Default role should be candidate."""
        user = User.objects.create_user(
            email="candidate@example.com",
            username="candidate1",
            password="testpass123!",
        )
        assert user.role == "candidate"

    def test_uuid_primary_key(self):
        """Primary key should be a UUID4."""
        user = User.objects.create_user(
            email="uuid@example.com",
            username="uuiduser",
            password="testpass123!",
        )
        assert isinstance(user.pk, uuid.UUID)
        assert user.pk.version == 4

    def test_is_email_verified_default_false(self):
        """is_email_verified should default to False."""
        user = User.objects.create_user(
            email="unverified@example.com",
            username="unverified",
            password="testpass123!",
        )
        assert user.is_email_verified is False

    def test_str_returns_email(self):
        """String representation should return the email."""
        user = User.objects.create_user(
            email="str@example.com",
            username="struser",
            password="testpass123!",
        )
        assert str(user) == "str@example.com"

    def test_role_choices_are_candidate_recruiter_admin(self):
        """Role field should have exactly three choices."""
        choices = {choice[0] for choice in User.Role.choices}
        assert choices == {"candidate", "recruiter", "admin"}
