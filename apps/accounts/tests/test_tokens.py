"""
Tests for email verification token generation and validation.
"""

import pytest
from django.core.signing import BadSignature, SignatureExpired

from apps.accounts.tokens import make_email_verification_token, verify_email_token


class TestEmailVerificationToken:
    def test_make_token_returns_string(self):
        """make_email_verification_token returns a non-empty string."""
        token = make_email_verification_token("some-user-id")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token_returns_user_id(self):
        """verify_email_token returns the original user_id for a valid token."""
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        token = make_email_verification_token(user_id)
        result = verify_email_token(token)
        assert result == user_id

    def test_verify_expired_token_raises(self):
        """Expired tokens raise SignatureExpired."""
        token = make_email_verification_token("some-id")
        with pytest.raises(SignatureExpired):
            verify_email_token(token, max_age_seconds=0)

    def test_verify_tampered_token_raises(self):
        """Tampered tokens raise BadSignature."""
        token = make_email_verification_token("some-id")
        tampered = token + "tampered"
        with pytest.raises(BadSignature):
            verify_email_token(tampered)
