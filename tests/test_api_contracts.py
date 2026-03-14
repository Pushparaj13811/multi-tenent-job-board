"""
Section 7 — API Contract & Response Shape.

For each serializer / endpoint, assert the exact set of keys in the response.
Ensures the frontend can rely on a stable contract.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    ApplicationFactory,
    CompanyFactory,
    CompanyMemberFactory,
    JobFactory,
    NotificationFactory,
    UserFactory,
)

# ═══════════════════════════════════════════════════════════════════════════
# Auth responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAuthResponseContracts:
    """Register and Login response shapes."""

    def test_register_response_excludes_password(self):
        """RegisterView response must NOT contain password or password_confirm."""
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {
                "email": "contract@test.com",
                "username": "contract_user",
                "first_name": "Test",
                "last_name": "User",
                "password": "StrongPass123!",
                "password_confirm": "StrongPass123!",
                "role": "candidate",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        keys = set(resp.data.keys())
        assert "password" not in keys
        assert "password_confirm" not in keys
        expected = {
            "id", "email", "username", "first_name", "last_name",
            "role", "phone", "avatar", "is_email_verified", "created_at",
        }
        assert keys == expected, f"Register response keys mismatch: {keys}"

    def test_login_response_contains_tokens_and_user(self):
        """LoginView response must contain access, refresh, and user sub-object."""
        password = "StrongPass123!"
        user = UserFactory(role="candidate")
        user.set_password(password)
        user.save()
        client = APIClient()
        resp = client.post(
            "/api/auth/login/",
            {"email": user.email, "password": password},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        assert keys == {"access", "refresh", "user"}
        user_keys = set(resp.data["user"].keys())
        expected_user_keys = {
            "id", "email", "username", "first_name", "last_name",
            "role", "phone", "avatar", "is_email_verified", "created_at",
        }
        assert user_keys == expected_user_keys


# ═══════════════════════════════════════════════════════════════════════════
# Application responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestApplicationResponseContracts:
    """Candidate and recruiter views expose different fields."""

    def test_candidate_list_excludes_recruiter_notes(self):
        """ApplicationListSerializer (candidate view) must NOT contain recruiter_notes."""
        app = ApplicationFactory()
        client = APIClient()
        client.force_authenticate(user=app.applicant)
        resp = client.get("/api/applications/")
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data["results"]
        assert len(results) >= 1
        keys = set(results[0].keys())
        assert "recruiter_notes" not in keys
        expected = {
            "id", "job", "status", "resume", "cover_letter",
            "expected_salary", "available_from", "created_at", "updated_at",
        }
        assert keys == expected, f"Candidate application keys mismatch: {keys}"

    def test_recruiter_list_includes_recruiter_notes(self):
        """ApplicationRecruiterSerializer (recruiter view) must contain recruiter_notes."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        ApplicationFactory(job=job)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        resp = client.get("/api/applications/")
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data["results"]
        assert len(results) >= 1
        keys = set(results[0].keys())
        assert "recruiter_notes" in keys
        expected = {
            "id", "job", "applicant", "status", "resume", "cover_letter",
            "expected_salary", "available_from", "recruiter_notes",
            "created_at", "updated_at",
        }
        assert keys == expected, f"Recruiter application keys mismatch: {keys}"


# ═══════════════════════════════════════════════════════════════════════════
# Notification responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNotificationResponseContract:
    """Notification list includes unread_count at the top level."""

    def test_notification_list_contains_unread_count(self):
        """GET /api/notifications/ response includes unread_count key."""
        user = UserFactory(role="candidate")
        NotificationFactory(user=user, is_read=False)
        NotificationFactory(user=user, is_read=True)
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get("/api/notifications/")
        assert resp.status_code == status.HTTP_200_OK
        assert "unread_count" in resp.data
        assert resp.data["unread_count"] == 1

    def test_notification_item_keys(self):
        """Each notification item has the exact expected keys."""
        user = UserFactory(role="candidate")
        NotificationFactory(user=user)
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get("/api/notifications/")
        assert resp.status_code == status.HTTP_200_OK
        item = resp.data["results"][0]
        keys = set(item.keys())
        expected = {"id", "type", "title", "message", "is_read", "metadata", "created_at"}
        assert keys == expected, f"Notification keys mismatch: {keys}"


# ═══════════════════════════════════════════════════════════════════════════
# Dashboard responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDashboardResponseContracts:
    """Dashboard endpoints expose exact aggregation keys the frontend depends on."""

    def test_recruiter_dashboard_keys(self):
        """RecruiterDashboard response contains expected aggregation keys."""
        membership = CompanyMemberFactory(role="owner")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        resp = client.get("/api/dashboard/recruiter/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        expected = {
            "total_jobs", "jobs_by_status", "total_applications",
            "applications_by_status", "recent_applications",
            "companies", "top_jobs",
        }
        assert keys == expected, f"Recruiter dashboard keys mismatch: {keys}"

    def test_candidate_dashboard_keys(self):
        """CandidateDashboard response contains expected aggregation keys."""
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = client.get("/api/dashboard/candidate/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        expected = {
            "total_applications", "applications_by_status", "recent_applications",
        }
        assert keys == expected, f"Candidate dashboard keys mismatch: {keys}"


# ═══════════════════════════════════════════════════════════════════════════
# Company responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCompanyResponseContracts:
    """Company list and detail response shapes."""

    def test_company_list_item_keys(self):
        """Each item in GET /api/companies/ has the list serializer keys."""
        CompanyFactory()
        client = APIClient()
        resp = client.get("/api/companies/")
        assert resp.status_code == status.HTTP_200_OK
        item = resp.data["results"][0]
        keys = set(item.keys())
        expected = {
            "id", "name", "slug", "description", "website", "logo",
            "size", "industry", "location", "is_verified",
            "verification_badge", "created_at",
        }
        assert keys == expected, f"Company list item keys mismatch: {keys}"

    def test_company_detail_keys(self):
        """GET /api/companies/{slug}/ has the detail serializer keys."""
        company = CompanyFactory()
        client = APIClient()
        resp = client.get(f"/api/companies/{company.slug}/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        expected = {
            "id", "name", "slug", "description", "website", "logo",
            "size", "industry", "location", "domain", "domain_verified",
            "verification_status", "is_verified", "verification_badge",
            "created_at",
        }
        assert keys == expected, f"Company detail keys mismatch: {keys}"


# ═══════════════════════════════════════════════════════════════════════════
# Job responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestJobResponseContracts:
    """Job list and detail response shapes."""

    def test_job_list_item_keys(self):
        """Each item in GET /api/jobs/ has the list serializer keys."""
        JobFactory(status="published")
        client = APIClient()
        resp = client.get("/api/jobs/")
        assert resp.status_code == status.HTTP_200_OK
        item = resp.data["results"][0]
        keys = set(item.keys())
        expected = {
            "id", "title", "slug", "company", "company_name", "location",
            "is_remote", "job_type", "experience_level", "salary_min",
            "salary_max", "currency", "status", "deadline", "created_at",
        }
        assert keys == expected, f"Job list item keys mismatch: {keys}"

    def test_job_detail_keys(self):
        """GET /api/jobs/{slug}/ has the detail serializer keys."""
        job = JobFactory(status="published")
        client = APIClient()
        resp = client.get(f"/api/jobs/{job.slug}/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        expected = {
            "id", "title", "slug", "company", "company_name", "posted_by",
            "description", "requirements", "responsibilities", "skills",
            "job_type", "experience_level", "location", "is_remote",
            "salary_min", "salary_max", "currency", "status", "deadline",
            "views_count", "created_at", "updated_at",
        }
        assert keys == expected, f"Job detail keys mismatch: {keys}"


# ═══════════════════════════════════════════════════════════════════════════
# Gap tests — Error response, paginated envelope, action responses
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestErrorResponseShape:
    """All error responses follow {error, code, details} shape."""

    def test_403_error_has_standard_shape(self):
        """403 from non-member job create has error, code, details keys."""
        recruiter = UserFactory(role="recruiter")
        company = CompanyFactory()
        client = APIClient()
        client.force_authenticate(user=recruiter)
        resp = client.post(
            "/api/jobs/",
            {
                "company": str(company.id),
                "title": "Test",
                "slug": "err-shape-test",
                "description": "x",
                "requirements": "x",
                "job_type": "full_time",
                "experience_level": "mid",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert "error" in resp.data
        assert "code" in resp.data

    def test_400_validation_error_shape(self):
        """Validation error returns structured error response."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        app = ApplicationFactory(job=job, status="applied")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        resp = client.patch(
            f"/api/applications/{app.id}/status/",
            {"status": "offered"},  # invalid: applied → offered
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_404_not_found_shape(self):
        """404 from scoped queryset has error, code keys."""
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        import uuid

        resp = client.get(f"/api/applications/{uuid.uuid4()}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestPaginatedEnvelopeShape:
    """All paginated endpoints return {results, next, previous}."""

    def test_job_list_paginated_envelope(self):
        """GET /api/jobs/ response has results, next, previous keys."""
        JobFactory(status="published")
        client = APIClient()
        resp = client.get("/api/jobs/")
        assert resp.status_code == status.HTTP_200_OK
        assert "results" in resp.data
        assert "next" in resp.data
        assert "previous" in resp.data

    def test_company_list_paginated_envelope(self):
        """GET /api/companies/ response has results, next, previous keys."""
        CompanyFactory()
        client = APIClient()
        resp = client.get("/api/companies/")
        assert resp.status_code == status.HTTP_200_OK
        assert "results" in resp.data
        assert "next" in resp.data
        assert "previous" in resp.data

    def test_notification_list_paginated_envelope(self):
        """GET /api/notifications/ response has results, next, previous, and unread_count."""
        user = UserFactory()
        NotificationFactory(user=user)
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.get("/api/notifications/")
        assert resp.status_code == status.HTTP_200_OK
        assert "results" in resp.data
        assert "next" in resp.data
        assert "previous" in resp.data
        assert "unread_count" in resp.data


@pytest.mark.django_db
class TestActionResponseShapes:
    """Publish, close, and status-update action response shapes."""

    def test_publish_response_keys(self):
        """POST /api/jobs/{slug}/publish/ returns id, status, message."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="draft", company=membership.company, posted_by=membership.user)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        resp = client.post(f"/api/jobs/{job.slug}/publish/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        assert keys == {"id", "status", "message"}
        assert resp.data["status"] == "published"

    def test_close_response_keys(self):
        """POST /api/jobs/{slug}/close/ returns id, status, message."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company, posted_by=membership.user)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        resp = client.post(f"/api/jobs/{job.slug}/close/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        assert keys == {"id", "status", "message"}
        assert resp.data["status"] == "closed"

    def test_status_update_response_keys(self):
        """PATCH /api/applications/{id}/status/ returns id, status, recruiter_notes, updated_at."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        app = ApplicationFactory(job=job, status="applied")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        resp = client.patch(
            f"/api/applications/{app.id}/status/",
            {"status": "reviewing"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        assert keys == {"id", "status", "recruiter_notes", "updated_at"}

    def test_withdraw_response_keys(self):
        """DELETE /api/applications/{id}/ (withdraw) returns id, status."""
        candidate = UserFactory(role="candidate")
        app = ApplicationFactory(applicant=candidate, status="applied")
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = client.delete(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_200_OK
        keys = set(resp.data.keys())
        assert keys == {"id", "status"}
        assert resp.data["status"] == "withdrawn"

    def test_search_response_shape(self):
        """GET /api/jobs/search/?q=x returns {results: [...]}."""
        client = APIClient()
        resp = client.get("/api/jobs/search/", {"q": "nonexistent"})
        assert resp.status_code == status.HTTP_200_OK
        assert "results" in resp.data
        assert isinstance(resp.data["results"], list)
