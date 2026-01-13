from django.core.signing import TimestampSigner

signer = TimestampSigner(salt="email-verification")


def make_email_verification_token(user_id: str) -> str:
    """Create a signed, timestamped token encoding the user ID."""
    return signer.sign(str(user_id))


def verify_email_token(token: str, max_age_seconds: int = 86400) -> str:
    """
    Verify the token and return the user_id.
    Raises BadSignature or SignatureExpired on failure.
    max_age_seconds: 86400 = 24 hours.
    """
    return signer.unsign(token, max_age=max_age_seconds)
