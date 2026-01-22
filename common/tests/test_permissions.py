"""
Tests for custom permission classes.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from common.permissions import IsCandidate, IsCompanyMember, IsOwnerOrReadOnly, IsRecruiter


@pytest.mark.django_db
class TestIsRecruiter:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.factory = RequestFactory()
        self.permission = IsRecruiter()
        self.view = APIView()

    def test_recruiter_allowed(self):
        """Recruiter users are granted permission."""
        user = User.objects.create_user(
            email="recruiter@test.com", username="rec", password="pass123!", role="recruiter"
        )
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_permission(request, self.view) is True

    def test_candidate_denied(self):
        """Candidate users are denied."""
        user = User.objects.create_user(
            email="candidate@test.com", username="cand", password="pass123!", role="candidate"
        )
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_permission(request, self.view) is False

    def test_anonymous_denied(self):
        """Anonymous (unauthenticated) users are denied."""
        request = self.factory.get("/")
        request.user = AnonymousUser()
        assert self.permission.has_permission(request, self.view) is False


@pytest.mark.django_db
class TestIsCandidate:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.factory = RequestFactory()
        self.permission = IsCandidate()
        self.view = APIView()

    def test_candidate_allowed(self):
        """Candidate users are granted permission."""
        user = User.objects.create_user(
            email="candidate@test.com", username="cand", password="pass123!", role="candidate"
        )
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_permission(request, self.view) is True

    def test_recruiter_denied(self):
        """Recruiter users are denied."""
        user = User.objects.create_user(
            email="recruiter@test.com", username="rec", password="pass123!", role="recruiter"
        )
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_permission(request, self.view) is False

    def test_anonymous_denied(self):
        """Anonymous (unauthenticated) users are denied."""
        request = self.factory.get("/")
        request.user = AnonymousUser()
        assert self.permission.has_permission(request, self.view) is False


@pytest.mark.django_db
class TestIsOwnerOrReadOnly:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.factory = RequestFactory()
        self.permission = IsOwnerOrReadOnly()
        self.view = APIView()

    def test_get_request_always_allowed(self):
        """Safe methods (GET) are always allowed regardless of ownership."""
        owner = User.objects.create_user(
            email="owner@test.com", username="owner", password="pass123!"
        )
        other = User.objects.create_user(
            email="other@test.com", username="other", password="pass123!"
        )
        request = self.factory.get("/")
        request.user = other
        # obj.applicant is the owner, but GET should still pass
        assert self.permission.has_object_permission(request, self.view, owner) is True

    def test_owner_can_modify(self):
        """Owner (obj matches request.user) can perform write operations."""
        owner = User.objects.create_user(
            email="owner@test.com", username="owner", password="pass123!"
        )
        request = self.factory.patch("/")
        request.user = owner
        assert self.permission.has_object_permission(request, self.view, owner) is True

    def test_non_owner_cannot_modify(self):
        """Non-owner is denied write operations."""
        owner = User.objects.create_user(
            email="owner@test.com", username="owner", password="pass123!"
        )
        other = User.objects.create_user(
            email="other@test.com", username="other", password="pass123!"
        )
        request = self.factory.patch("/")
        request.user = other
        assert self.permission.has_object_permission(request, self.view, owner) is False


@pytest.mark.django_db
class TestIsCompanyMember:
    """Tests with real Company/CompanyMember DB objects (added in Phase 4)."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.factory = RequestFactory()
        self.permission = IsCompanyMember()
        self.view = APIView()
        self.company = Company.objects.create(name="Test Co", slug="test-co")

    def test_member_has_permission(self):
        """A company member is granted object permission."""
        user = User.objects.create_user(
            email="member@test.com", username="member", password="pass123!", role="recruiter"
        )
        CompanyMember.objects.create(user=user, company=self.company, role="recruiter")
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_object_permission(request, self.view, self.company) is True

    def test_non_member_denied(self):
        """A user who is not a member is denied."""
        user = User.objects.create_user(
            email="outsider@test.com", username="outsider", password="pass123!", role="recruiter"
        )
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_object_permission(request, self.view, self.company) is False

    def test_candidate_denied(self):
        """A candidate (not a member) is denied."""
        user = User.objects.create_user(
            email="cand@test.com", username="cand", password="pass123!", role="candidate"
        )
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_object_permission(request, self.view, self.company) is False

    def test_member_of_different_company_denied(self):
        """A member of a different company is denied."""
        other_company = Company.objects.create(name="Other Co", slug="other-co")
        user = User.objects.create_user(
            email="other@test.com", username="other", password="pass123!", role="recruiter"
        )
        CompanyMember.objects.create(user=user, company=other_company, role="recruiter")
        request = self.factory.get("/")
        request.user = user
        assert self.permission.has_object_permission(request, self.view, self.company) is False
