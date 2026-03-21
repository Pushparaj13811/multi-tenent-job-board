"""
Tests for Part D — Admin panel enhancements for company verification.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.accounts.models import User
from apps.companies.admin import CompanyAdmin
from apps.companies.models import Company


@pytest.mark.django_db
class TestCompanyAdminActions:
    def _setup(self):
        admin_user = User.objects.create_superuser(
            email="admin@test.com", username="admin", password="pass123!",
        )
        site = AdminSite()
        admin = CompanyAdmin(Company, site)
        factory = RequestFactory()
        request = factory.post("/admin/")
        request.user = admin_user
        # Add message storage for admin actions
        request.session = "session"
        request._messages = FallbackStorage(request)
        return admin, request, admin_user

    def test_approve_verification_action(self):
        admin, request, admin_user = self._setup()
        company = Company.objects.create(
            name="Pending Co", slug="pending-co",
            domain_verified=True, verification_status="pending",
        )
        queryset = Company.objects.filter(pk=company.pk)
        admin.approve_verification(request, queryset)
        company.refresh_from_db()
        assert company.verification_status == "verified"
        assert company.verified_at is not None
        assert company.verified_by == admin_user

    def test_reject_verification_action(self):
        admin, request, _ = self._setup()
        company = Company.objects.create(
            name="Pending Co", slug="pending-co",
            domain_verified=True, verification_status="pending",
        )
        queryset = Company.objects.filter(pk=company.pk)
        admin.reject_verification(request, queryset)
        company.refresh_from_db()
        assert company.verification_status == "rejected"

    def test_approve_only_affects_pending(self):
        admin, request, _ = self._setup()
        unverified = Company.objects.create(
            name="Unverified Co", slug="unverified-co",
            verification_status="unverified",
        )
        queryset = Company.objects.filter(pk=unverified.pk)
        admin.approve_verification(request, queryset)
        unverified.refresh_from_db()
        assert unverified.verification_status == "unverified"

    def test_admin_list_display_fields(self):
        admin, _, _ = self._setup()
        assert "domain" in admin.list_display
        assert "domain_verified" in admin.list_display
        assert "verification_status" in admin.list_display

    def test_admin_list_filter_fields(self):
        admin, _, _ = self._setup()
        assert "domain_verified" in admin.list_filter
        assert "verification_status" in admin.list_filter
