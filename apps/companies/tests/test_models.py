"""
Tests for Company and CompanyMember models.
"""

import pytest
from django.db import IntegrityError

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember


@pytest.mark.django_db
class TestCompanyModel:
    def test_create_company(self):
        """Company can be created with required fields."""
        company = Company.objects.create(name="Acme Corp", slug="acme-corp")
        assert company.name == "Acme Corp"
        assert company.slug == "acme-corp"

    def test_slug_is_unique(self):
        """Duplicate slugs raise IntegrityError."""
        Company.objects.create(name="Company A", slug="same-slug")
        with pytest.raises(IntegrityError):
            Company.objects.create(name="Company B", slug="same-slug")

    def test_str_returns_name(self):
        """String representation returns company name."""
        company = Company.objects.create(name="Test Co", slug="test-co")
        assert str(company) == "Test Co"

    def test_is_verified_defaults_to_false(self):
        """New companies are unverified by default (is_verified is a property)."""
        company = Company.objects.create(name="New Co", slug="new-co")
        assert company.is_verified is False
        assert company.domain_verified is False
        assert company.verification_status == "unverified"


@pytest.mark.django_db
class TestCompanyMemberModel:
    def test_create_member(self):
        """CompanyMember can be created linking user to company."""
        user = User.objects.create_user(
            email="member@test.com", username="member", password="pass123!"
        )
        company = Company.objects.create(name="Co", slug="co")
        member = CompanyMember.objects.create(user=user, company=company, role="owner")
        assert member.user == user
        assert member.company == company
        assert member.role == "owner"

    def test_unique_together_user_company(self):
        """Same user cannot be added to same company twice."""
        user = User.objects.create_user(
            email="dup@test.com", username="dup", password="pass123!"
        )
        company = Company.objects.create(name="Co", slug="co")
        CompanyMember.objects.create(user=user, company=company)
        with pytest.raises(IntegrityError):
            CompanyMember.objects.create(user=user, company=company)

    def test_default_role_is_recruiter(self):
        """Default membership role is recruiter."""
        user = User.objects.create_user(
            email="def@test.com", username="def", password="pass123!"
        )
        company = Company.objects.create(name="Co", slug="co")
        member = CompanyMember.objects.create(user=user, company=company)
        assert member.role == "recruiter"
