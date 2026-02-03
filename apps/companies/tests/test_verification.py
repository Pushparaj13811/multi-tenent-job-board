"""
Tests for the company verification system:
- Free email blocklist validators
- Domain verification tokens
- Model verification fields and properties
- Verification endpoints (domain verify, resend, submit docs)
- Recruiter registration email gate
"""

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.companies.tokens import (
    generate_domain_verification_token,
    is_domain_token_expired,
    is_resend_on_cooldown,
)
from apps.companies.validators import (
    FREE_EMAIL_DOMAINS,
    extract_email_domain,
    is_free_email,
)

COMPANIES_URL = "/api/companies/"
REGISTER_URL = "/api/auth/register/"


# ──────────────────────────────────────────────────────────────
# A2 — Free Email Blocklist Validators
# ──────────────────────────────────────────────────────────────


class TestExtractEmailDomain:
    def test_basic_extraction(self):
        assert extract_email_domain("user@example.com") == "example.com"

    def test_uppercase_normalized(self):
        assert extract_email_domain("User@EXAMPLE.COM") == "example.com"

    def test_whitespace_stripped(self):
        assert extract_email_domain("  user@example.com  ") == "example.com"


class TestIsFreeEmail:
    @pytest.mark.parametrize("domain", ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"])
    def test_free_domains_detected(self, domain):
        assert is_free_email(f"user@{domain}") is True

    @pytest.mark.parametrize("domain", ["acme.com", "company.io", "startupxyz.com"])
    def test_business_domains_allowed(self, domain):
        assert is_free_email(f"user@{domain}") is False

    def test_blocklist_is_frozen_set(self):
        assert isinstance(FREE_EMAIL_DOMAINS, frozenset)

    def test_blocklist_has_minimum_entries(self):
        assert len(FREE_EMAIL_DOMAINS) >= 15


# ──────────────────────────────────────────────────────────────
# A3 — Domain Verification Tokens
# ──────────────────────────────────────────────────────────────


class TestGenerateDomainVerificationToken:
    def test_returns_string(self):
        token = generate_domain_verification_token()
        assert isinstance(token, str)

    def test_tokens_are_unique(self):
        tokens = {generate_domain_verification_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_token_length_sufficient(self):
        token = generate_domain_verification_token()
        assert len(token) >= 20


class TestIsDomainTokenExpired:
    def test_none_is_expired(self):
        assert is_domain_token_expired(None) is True

    @override_settings(COMPANY_DOMAIN_TOKEN_EXPIRY_HOURS=48)
    def test_recent_token_not_expired(self):
        generated_at = timezone.now() - timezone.timedelta(hours=1)
        assert is_domain_token_expired(generated_at) is False

    @override_settings(COMPANY_DOMAIN_TOKEN_EXPIRY_HOURS=48)
    def test_old_token_expired(self):
        generated_at = timezone.now() - timezone.timedelta(hours=49)
        assert is_domain_token_expired(generated_at) is True


class TestIsResendOnCooldown:
    def test_none_not_on_cooldown(self):
        assert is_resend_on_cooldown(None) is False

    @override_settings(COMPANY_DOMAIN_RESEND_COOLDOWN_MINUTES=5)
    def test_recent_resend_on_cooldown(self):
        generated_at = timezone.now() - timezone.timedelta(minutes=1)
        assert is_resend_on_cooldown(generated_at) is True

    @override_settings(COMPANY_DOMAIN_RESEND_COOLDOWN_MINUTES=5)
    def test_old_resend_not_on_cooldown(self):
        generated_at = timezone.now() - timezone.timedelta(minutes=10)
        assert is_resend_on_cooldown(generated_at) is False


# ──────────────────────────────────────────────────────────────
# A1 — Model Verification Fields & Properties
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCompanyVerificationModel:
    def test_domain_field_exists(self):
        company = Company.objects.create(name="Co", slug="co", domain="acme.com")
        assert company.domain == "acme.com"

    def test_domain_defaults_to_blank(self):
        company = Company.objects.create(name="Co", slug="co")
        assert company.domain == ""

    def test_domain_verified_defaults_false(self):
        company = Company.objects.create(name="Co", slug="co")
        assert company.domain_verified is False

    def test_verification_status_default_unverified(self):
        company = Company.objects.create(name="Co", slug="co")
        assert company.verification_status == "unverified"

    def test_verification_status_choices(self):
        valid_statuses = {"unverified", "pending", "verified", "rejected"}
        model_choices = {c[0] for c in Company.VerificationStatus.choices}
        assert model_choices == valid_statuses

    def test_is_verified_property_both_required(self):
        """is_verified is True only when domain_verified AND verification_status='verified'."""
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verified=True,
            verification_status="verified",
        )
        assert company.is_verified is True

    def test_is_verified_false_without_domain(self):
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verified=False,
            verification_status="verified",
        )
        assert company.is_verified is False

    def test_is_verified_false_without_doc_verification(self):
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verified=True,
            verification_status="pending",
        )
        assert company.is_verified is False

    def test_verification_badge_verified(self):
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verified=True,
            verification_status="verified",
        )
        assert company.verification_badge == "verified"

    def test_verification_badge_domain_only(self):
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verified=True,
            verification_status="pending",
        )
        assert company.verification_badge == "domain_verified"

    def test_verification_badge_unverified(self):
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verified=False,
            verification_status="unverified",
        )
        assert company.verification_badge == "unverified"

    def test_domain_verification_token_field(self):
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verification_token="test-token",
        )
        assert company.domain_verification_token == "test-token"

    def test_domain_verification_token_generated_at(self):
        now = timezone.now()
        company = Company.objects.create(
            name="Co", slug="co",
            domain_verification_token_generated_at=now,
        )
        assert company.domain_verification_token_generated_at == now

    def test_registration_document_field(self):
        company = Company.objects.create(name="Co", slug="co")
        assert not company.registration_document

    def test_registration_number_field(self):
        company = Company.objects.create(
            name="Co", slug="co",
            registration_number="REG-123",
        )
        assert company.registration_number == "REG-123"

    def test_verified_at_field(self):
        now = timezone.now()
        company = Company.objects.create(
            name="Co", slug="co",
            verified_at=now,
        )
        assert company.verified_at == now

    def test_verified_by_field(self):
        admin = User.objects.create_user(
            email="admin@test.com", username="admin", password="pass123!", role="admin"
        )
        company = Company.objects.create(
            name="Co", slug="co",
            verified_by=admin,
        )
        assert company.verified_by == admin


# ──────────────────────────────────────────────────────────────
# A4 — Company Creation with Domain Extraction
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCompanyCreationWithVerification:
    def _create_recruiter_client(self, email="recruiter@acme.com"):
        user = User.objects.create_user(
            email=email, username=email.split("@")[0],
            password="pass123!", role="recruiter",
        )
        client = APIClient()
        client.force_authenticate(user=user)
        return client, user

    def test_company_domain_extracted_from_creator_email(self):
        """Creating company auto-extracts domain from recruiter's email."""
        client, user = self._create_recruiter_client("recruiter@acme.com")
        response = client.post(COMPANIES_URL, {
            "name": "Acme Corp", "slug": "acme-corp",
        })
        assert response.status_code == 201
        company = Company.objects.get(slug="acme-corp")
        assert company.domain == "acme.com"

    def test_domain_verification_token_generated_on_create(self):
        """A domain verification token is generated on company creation."""
        client, user = self._create_recruiter_client("recruiter@acme.com")
        client.post(COMPANIES_URL, {"name": "Acme Corp", "slug": "acme-corp"})
        company = Company.objects.get(slug="acme-corp")
        assert company.domain_verification_token is not None
        assert len(company.domain_verification_token) > 0

    def test_company_starts_unverified(self):
        """New company starts with verification_status='unverified'."""
        client, user = self._create_recruiter_client("recruiter@acme.com")
        client.post(COMPANIES_URL, {"name": "Acme Corp", "slug": "acme-corp"})
        company = Company.objects.get(slug="acme-corp")
        assert company.verification_status == "unverified"
        assert company.domain_verified is False


# ──────────────────────────────────────────────────────────────
# A5 — Verification Endpoints
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestDomainVerificationEndpoint:
    def _setup_company_with_token(self):
        user = User.objects.create_user(
            email="recruiter@acme.com", username="recruiter",
            password="pass123!", role="recruiter",
        )
        token = generate_domain_verification_token()
        company = Company.objects.create(
            name="Acme Corp", slug="acme-corp",
            domain="acme.com",
            domain_verification_token=token,
            domain_verification_token_generated_at=timezone.now(),
        )
        CompanyMember.objects.create(user=user, company=company, role="owner")
        client = APIClient()
        client.force_authenticate(user=user)
        return client, company, token

    def test_valid_token_verifies_domain(self):
        client, company, token = self._setup_company_with_token()
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/verify-domain/",
            {"token": token},
        )
        assert response.status_code == 200
        company.refresh_from_db()
        assert company.domain_verified is True

    def test_invalid_token_returns_400(self):
        client, company, token = self._setup_company_with_token()
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/verify-domain/",
            {"token": "wrong-token"},
        )
        assert response.status_code == 400

    def test_expired_token_returns_400(self):
        client, company, token = self._setup_company_with_token()
        company.domain_verification_token_generated_at = (
            timezone.now() - timezone.timedelta(hours=49)
        )
        company.save()
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/verify-domain/",
            {"token": token},
        )
        assert response.status_code == 400

    def test_non_member_cannot_verify(self):
        _, company, token = self._setup_company_with_token()
        other_user = User.objects.create_user(
            email="other@test.com", username="other",
            password="pass123!", role="recruiter",
        )
        client = APIClient()
        client.force_authenticate(user=other_user)
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/verify-domain/",
            {"token": token},
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestResendDomainVerification:
    def _setup(self):
        user = User.objects.create_user(
            email="recruiter@acme.com", username="recruiter",
            password="pass123!", role="recruiter",
        )
        company = Company.objects.create(
            name="Acme Corp", slug="acme-corp",
            domain="acme.com",
            domain_verification_token="old-token",
            domain_verification_token_generated_at=timezone.now() - timezone.timedelta(minutes=10),
        )
        CompanyMember.objects.create(user=user, company=company, role="owner")
        client = APIClient()
        client.force_authenticate(user=user)
        return client, company

    def test_resend_generates_new_token(self):
        client, company = self._setup()
        old_token = company.domain_verification_token
        response = client.post(f"{COMPANIES_URL}{company.slug}/resend-domain-verification/")
        assert response.status_code == 200
        company.refresh_from_db()
        assert company.domain_verification_token != old_token

    def test_resend_on_cooldown_returns_429(self):
        client, company = self._setup()
        company.domain_verification_token_generated_at = timezone.now()
        company.save()
        response = client.post(f"{COMPANIES_URL}{company.slug}/resend-domain-verification/")
        assert response.status_code == 429

    def test_already_verified_returns_400(self):
        client, company = self._setup()
        company.domain_verified = True
        company.save()
        response = client.post(f"{COMPANIES_URL}{company.slug}/resend-domain-verification/")
        assert response.status_code == 400


@pytest.mark.django_db
class TestSubmitVerification:
    def _setup(self):
        user = User.objects.create_user(
            email="recruiter@acme.com", username="recruiter",
            password="pass123!", role="recruiter",
        )
        company = Company.objects.create(
            name="Acme Corp", slug="acme-corp",
            domain="acme.com",
            domain_verified=True,
        )
        CompanyMember.objects.create(user=user, company=company, role="owner")
        client = APIClient()
        client.force_authenticate(user=user)
        return client, company

    def test_submit_with_registration_number(self):
        client, company = self._setup()
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/submit-verification/",
            {"registration_number": "REG-12345"},
        )
        assert response.status_code == 200
        company.refresh_from_db()
        assert company.verification_status == "pending"
        assert company.registration_number == "REG-12345"

    def test_submit_without_domain_verification_returns_400(self):
        client, company = self._setup()
        company.domain_verified = False
        company.save()
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/submit-verification/",
            {"registration_number": "REG-12345"},
        )
        assert response.status_code == 400

    def test_submit_already_verified_returns_400(self):
        client, company = self._setup()
        company.verification_status = "verified"
        company.save()
        response = client.post(
            f"{COMPANIES_URL}{company.slug}/submit-verification/",
            {"registration_number": "REG-12345"},
        )
        assert response.status_code == 400


# ──────────────────────────────────────────────────────────────
# A6 — Recruiter Registration Email Gate
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRecruiterRegistrationEmailGate:
    def _payload(self, **overrides):
        data = {
            "email": "recruiter@acme.com",
            "username": "recruiter",
            "first_name": "Test",
            "last_name": "Recruiter",
            "password": "TestPass123!",
            "password_confirm": "TestPass123!",
            "role": "recruiter",
        }
        data.update(overrides)
        return data

    def test_recruiter_with_business_email_can_register(self):
        client = APIClient()
        response = client.post(REGISTER_URL, self._payload())
        assert response.status_code == 201

    def test_recruiter_with_free_email_rejected(self):
        client = APIClient()
        response = client.post(REGISTER_URL, self._payload(
            email="recruiter@gmail.com",
            username="recruiter_gmail",
        ))
        assert response.status_code == 400
        assert "email" in response.json().get("details", response.json())

    def test_candidate_with_free_email_allowed(self):
        client = APIClient()
        response = client.post(REGISTER_URL, self._payload(
            email="candidate@gmail.com",
            username="candidate_gmail",
            role="candidate",
        ))
        assert response.status_code == 201


# ──────────────────────────────────────────────────────────────
# Listing — Verified companies filter with new model
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCompanyListingWithVerification:
    def test_only_fully_verified_companies_in_public_list(self, api_client):
        """Public list only shows companies with is_verified=True (both domain + doc verified)."""
        Company.objects.create(
            name="Fully Verified", slug="full",
            domain_verified=True, verification_status="verified",
        )
        Company.objects.create(
            name="Domain Only", slug="domain-only",
            domain_verified=True, verification_status="pending",
        )
        Company.objects.create(
            name="Unverified", slug="unverified",
            domain_verified=False, verification_status="unverified",
        )
        response = api_client.get(COMPANIES_URL)
        slugs = [c["slug"] for c in response.json()["results"]]
        assert "full" in slugs
        assert "domain-only" not in slugs
        assert "unverified" not in slugs

    def test_is_verified_in_response(self, api_client):
        """Response includes is_verified field."""
        Company.objects.create(
            name="Co", slug="co",
            domain_verified=True, verification_status="verified",
        )
        response = api_client.get(COMPANIES_URL)
        assert response.json()["results"][0]["is_verified"] is True

    def test_verification_badge_in_response(self, api_client):
        """Response includes verification_badge field."""
        Company.objects.create(
            name="Co", slug="co",
            domain_verified=True, verification_status="verified",
        )
        response = api_client.get(COMPANIES_URL)
        assert response.json()["results"][0]["verification_badge"] == "verified"
