"""
Tests for auth endpoints: register, login, token refresh, email verification.
"""

import pytest
from django.core import mail

from apps.accounts.models import User
from apps.accounts.tokens import make_email_verification_token

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
REFRESH_URL = "/api/auth/token/refresh/"
VERIFY_EMAIL_URL = "/api/auth/verify-email/"


@pytest.mark.django_db
class TestRegisterView:
    def _register_payload(self, **overrides):
        data = {
            "email": "newuser@example.com",
            "username": "newuser",
            "first_name": "New",
            "last_name": "User",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "role": "candidate",
        }
        data.update(overrides)
        return data

    def test_register_returns_201(self, api_client):
        """Successful registration returns 201."""
        response = api_client.post(REGISTER_URL, self._register_payload())
        assert response.status_code == 201

    def test_register_creates_user_in_db(self, api_client):
        """User is actually persisted in the database."""
        api_client.post(REGISTER_URL, self._register_payload())
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_duplicate_email_returns_400(self, api_client):
        """Registering with an existing email returns 400."""
        api_client.post(REGISTER_URL, self._register_payload())
        response = api_client.post(REGISTER_URL, self._register_payload())
        assert response.status_code == 400

    def test_password_mismatch_returns_400(self, api_client):
        """Mismatched passwords return 400."""
        payload = self._register_payload(password_confirm="DifferentPass123!")
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 400

    def test_weak_password_returns_400(self, api_client):
        """Weak passwords are rejected by Django validators."""
        payload = self._register_payload(password="123", password_confirm="123")
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 400

    def test_default_role_is_candidate(self, api_client):
        """When no role is specified, default is candidate."""
        payload = self._register_payload()
        del payload["role"]
        api_client.post(REGISTER_URL, payload)
        user = User.objects.get(email="newuser@example.com")
        assert user.role == "candidate"

    def test_register_as_recruiter(self, api_client):
        """User can register as a recruiter."""
        payload = self._register_payload(role="recruiter")
        response = api_client.post(REGISTER_URL, payload)
        assert response.status_code == 201
        user = User.objects.get(email="newuser@example.com")
        assert user.role == "recruiter"

    def test_response_does_not_contain_password(self, api_client):
        """Password should never be in the response."""
        response = api_client.post(REGISTER_URL, self._register_payload())
        data = response.json()
        assert "password" not in data
        assert "password_confirm" not in data

    def test_register_sends_verification_email(self, api_client):
        """Registration triggers a verification email."""
        api_client.post(REGISTER_URL, self._register_payload())
        assert len(mail.outbox) == 1
        assert "newuser@example.com" in mail.outbox[0].to


@pytest.mark.django_db
class TestLoginView:
    @pytest.fixture(autouse=True)
    def _create_user(self):
        self.user = User.objects.create_user(
            email="login@example.com",
            username="loginuser",
            password="SecurePass123!",
            is_email_verified=True,
        )

    def test_returns_access_and_refresh_tokens(self, api_client):
        """Successful login returns access and refresh JWT tokens."""
        response = api_client.post(
            LOGIN_URL, {"email": "login@example.com", "password": "SecurePass123!"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access" in data
        assert "refresh" in data

    def test_returns_user_data(self, api_client):
        """Login response includes user details."""
        response = api_client.post(
            LOGIN_URL, {"email": "login@example.com", "password": "SecurePass123!"}
        )
        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == "login@example.com"
        assert data["user"]["role"] == "candidate"

    def test_wrong_password_returns_401(self, api_client):
        """Wrong password returns 401."""
        response = api_client.post(
            LOGIN_URL, {"email": "login@example.com", "password": "WrongPass!"}
        )
        assert response.status_code == 401

    def test_nonexistent_email_returns_401(self, api_client):
        """Non-existent email returns 401."""
        response = api_client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": "SecurePass123!"}
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestTokenRefreshView:
    def test_refresh_returns_new_access_token(self, api_client):
        """Refreshing with a valid refresh token returns a new access token."""
        User.objects.create_user(
            email="refresh@example.com",
            username="refreshuser",
            password="SecurePass123!",
        )
        login_response = api_client.post(
            LOGIN_URL, {"email": "refresh@example.com", "password": "SecurePass123!"}
        )
        refresh_token = login_response.json()["refresh"]

        response = api_client.post(REFRESH_URL, {"refresh": refresh_token})
        assert response.status_code == 200
        assert "access" in response.json()


@pytest.mark.django_db
class TestVerifyEmailView:
    def test_valid_token_sets_is_email_verified(self, api_client):
        """Valid verification token sets is_email_verified to True."""
        user = User.objects.create_user(
            email="verify@example.com",
            username="verifyuser",
            password="SecurePass123!",
            is_email_verified=False,
        )
        token = make_email_verification_token(str(user.id))

        response = api_client.post(VERIFY_EMAIL_URL, {"token": token})
        assert response.status_code == 200

        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_invalid_token_returns_400(self, api_client):
        """Invalid token returns 400."""
        response = api_client.post(VERIFY_EMAIL_URL, {"token": "invalid-token"})
        assert response.status_code == 400
