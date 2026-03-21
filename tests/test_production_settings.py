"""
Section 9 — Production Settings Sanity.

Import production settings with fake env vars and assert
security-critical values are set correctly.
"""


import pytest


@pytest.fixture(autouse=True)
def _production_env(monkeypatch):
    """Set minimal env vars required to import production settings."""
    monkeypatch.setenv(
        "SECRET_KEY",
        "a" * 60,  # must be >= 50 chars per HireFlowSettings
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/hireflow",
    )
    monkeypatch.setenv("ALLOWED_HOSTS", '["hireflow.io", "api.hireflow.io"]')
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")


class TestProductionSettings:
    """Verify production security hardening flags."""

    def _load_settings(self):
        """Re-import production settings with mocked env."""
        # Force re-import to pick up monkeypatched env vars
        import importlib

        import config.env
        importlib.reload(config.env)

        import config.settings.base
        importlib.reload(config.settings.base)

        import config.settings.production as prod
        importlib.reload(prod)
        return prod

    def test_debug_is_false(self):
        """DEBUG must be False in production."""
        prod = self._load_settings()
        assert prod.DEBUG is False

    def test_secure_ssl_redirect(self):
        """SECURE_SSL_REDIRECT must be True."""
        prod = self._load_settings()
        assert prod.SECURE_SSL_REDIRECT is True

    def test_session_cookie_secure(self):
        """SESSION_COOKIE_SECURE must be True."""
        prod = self._load_settings()
        assert prod.SESSION_COOKIE_SECURE is True

    def test_csrf_cookie_secure(self):
        """CSRF_COOKIE_SECURE must be True."""
        prod = self._load_settings()
        assert prod.CSRF_COOKIE_SECURE is True

    def test_hsts_seconds_at_least_one_year(self):
        """SECURE_HSTS_SECONDS must be >= 31536000 (1 year)."""
        prod = self._load_settings()
        assert prod.SECURE_HSTS_SECONDS >= 31536000

    def test_allowed_hosts_not_empty(self):
        """ALLOWED_HOSTS must not be empty in production."""
        prod = self._load_settings()
        assert len(prod.ALLOWED_HOSTS) > 0

    def test_celery_beat_schedule_contains_close_expired_jobs(self):
        """CELERY_BEAT_SCHEDULE contains 'close-expired-jobs'."""
        prod = self._load_settings()
        assert "close-expired-jobs" in prod.CELERY_BEAT_SCHEDULE

    def test_hsts_include_subdomains(self):
        """SECURE_HSTS_INCLUDE_SUBDOMAINS must be True."""
        prod = self._load_settings()
        assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True

    def test_hsts_preload(self):
        """SECURE_HSTS_PRELOAD must be True."""
        prod = self._load_settings()
        assert prod.SECURE_HSTS_PRELOAD is True

    def test_content_type_nosniff(self):
        """SECURE_CONTENT_TYPE_NOSNIFF must be True."""
        prod = self._load_settings()
        assert prod.SECURE_CONTENT_TYPE_NOSNIFF is True

    def test_x_frame_options_deny(self):
        """X_FRAME_OPTIONS must be 'DENY'."""
        prod = self._load_settings()
        assert prod.X_FRAME_OPTIONS == "DENY"

    def test_production_logging_configured(self):
        """Production settings include LOGGING configuration."""
        prod = self._load_settings()
        assert hasattr(prod, "LOGGING")
        assert prod.LOGGING["version"] == 1
