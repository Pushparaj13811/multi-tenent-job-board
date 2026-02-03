"""
Tests for company CRUD and member invitation endpoints.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember

COMPANIES_URL = "/api/companies/"


def _company_url(slug):
    return f"{COMPANIES_URL}{slug}/"


def _members_url(slug):
    return f"{COMPANIES_URL}{slug}/members/"


def _create_owner_client(email="owner@test.com"):
    """Create a recruiter user who owns a company, return (client, user, company)."""
    user = User.objects.create_user(
        email=email, username=email.split("@")[0], password="pass123!", role="recruiter"
    )
    company = Company.objects.create(name="Owner Co", slug="owner-co", domain_verified=True, verification_status="verified")
    CompanyMember.objects.create(user=user, company=company, role="owner")
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user, company


@pytest.mark.django_db
class TestListCompanies:
    def test_returns_only_verified_companies(self, api_client):
        """Public listing returns only verified companies."""
        Company.objects.create(name="Verified", slug="verified", domain_verified=True, verification_status="verified")
        Company.objects.create(name="Unverified", slug="unverified", domain_verified=False, verification_status="unverified")
        response = api_client.get(COMPANIES_URL)
        slugs = [c["slug"] for c in response.json()["results"]]
        assert "verified" in slugs
        assert "unverified" not in slugs

    def test_publicly_accessible(self, api_client):
        """No authentication required for listing."""
        response = api_client.get(COMPANIES_URL)
        assert response.status_code == 200

    def test_pagination_returns_cursor(self, api_client):
        """Response includes cursor pagination fields."""
        Company.objects.create(name="Co", slug="co", domain_verified=True, verification_status="verified")
        response = api_client.get(COMPANIES_URL)
        data = response.json()
        assert "results" in data
        assert "next" in data
        assert "previous" in data


@pytest.mark.django_db
class TestCreateCompany:
    def _payload(self, **overrides):
        data = {"name": "New Corp", "slug": "new-corp", "industry": "Tech"}
        data.update(overrides)
        return data

    def test_recruiter_can_create(self):
        """Recruiter can create a company, returns 201."""
        user = User.objects.create_user(
            email="rec@test.com", username="rec", password="pass123!", role="recruiter"
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(COMPANIES_URL, self._payload())
        assert response.status_code == 201
        assert Company.objects.filter(slug="new-corp").exists()

    def test_creator_becomes_owner(self):
        """Creating user is automatically a CompanyMember with role=owner."""
        user = User.objects.create_user(
            email="rec@test.com", username="rec", password="pass123!", role="recruiter"
        )
        client = APIClient()
        client.force_authenticate(user=user)
        client.post(COMPANIES_URL, self._payload())
        company = Company.objects.get(slug="new-corp")
        member = CompanyMember.objects.get(user=user, company=company)
        assert member.role == "owner"

    def test_candidate_cannot_create(self, candidate_client):
        """Candidates are forbidden from creating companies."""
        response = candidate_client.post(COMPANIES_URL, self._payload())
        assert response.status_code == 403

    def test_unauthenticated_gets_401(self, api_client):
        """Unauthenticated request returns 401."""
        response = api_client.post(COMPANIES_URL, self._payload())
        assert response.status_code == 401

    def test_duplicate_slug_returns_400(self):
        """Duplicate slug returns 400."""
        Company.objects.create(name="Existing", slug="new-corp")
        user = User.objects.create_user(
            email="rec@test.com", username="rec", password="pass123!", role="recruiter"
        )
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.post(COMPANIES_URL, self._payload())
        assert response.status_code == 400


@pytest.mark.django_db
class TestCompanyDetail:
    def test_retrieve_by_slug(self, api_client):
        """Company can be retrieved by slug."""
        Company.objects.create(name="Detail Co", slug="detail-co", domain_verified=True, verification_status="verified")
        response = api_client.get(_company_url("detail-co"))
        assert response.status_code == 200
        assert response.json()["name"] == "Detail Co"


@pytest.mark.django_db
class TestUpdateCompany:
    def test_owner_can_update(self):
        """Company owner can update company details."""
        client, user, company = _create_owner_client()
        response = client.patch(_company_url(company.slug), {"name": "Updated Name"})
        assert response.status_code == 200
        company.refresh_from_db()
        assert company.name == "Updated Name"

    def test_non_owner_member_cannot_update(self):
        """A recruiter member (not owner) cannot update."""
        owner = User.objects.create_user(
            email="owner@test.com", username="owner", password="pass123!", role="recruiter"
        )
        company = Company.objects.create(name="Co", slug="co", domain_verified=True, verification_status="verified")
        CompanyMember.objects.create(user=owner, company=company, role="owner")

        member = User.objects.create_user(
            email="member@test.com", username="member", password="pass123!", role="recruiter"
        )
        CompanyMember.objects.create(user=member, company=company, role="recruiter")

        client = APIClient()
        client.force_authenticate(user=member)
        response = client.patch(_company_url("co"), {"name": "Hacked"})
        assert response.status_code == 403


@pytest.mark.django_db
class TestInviteMember:
    def test_owner_can_invite_recruiter(self):
        """Owner can invite a recruiter to the company."""
        client, owner, company = _create_owner_client()
        invitee = User.objects.create_user(
            email="invitee@test.com", username="invitee", password="pass123!", role="recruiter"
        )
        response = client.post(_members_url(company.slug), {"email": invitee.email})
        assert response.status_code == 201
        assert CompanyMember.objects.filter(user=invitee, company=company).exists()

    def test_already_member_returns_400(self):
        """Inviting an existing member returns 400."""
        client, owner, company = _create_owner_client()
        invitee = User.objects.create_user(
            email="invitee@test.com", username="invitee", password="pass123!", role="recruiter"
        )
        CompanyMember.objects.create(user=invitee, company=company, role="recruiter")
        response = client.post(_members_url(company.slug), {"email": invitee.email})
        assert response.status_code == 400
