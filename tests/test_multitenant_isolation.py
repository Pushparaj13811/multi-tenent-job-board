"""
Multi-tenancy boundary audit — every cross-tenant data-leak scenario.

Convention: Company A / Recruiter A vs Company B / Recruiter B.
Every test asserts that Tenant A cannot read, write, or infer the
existence of Tenant B's resources.
"""

import pytest
from django.contrib.postgres.search import SearchVector
from rest_framework import status
from rest_framework.test import APIClient

from apps.jobs.models import Job
from apps.notifications.models import Notification
from tests.factories import (
    ApplicationFactory,
    CompanyFactory,
    CompanyMemberFactory,
    JobFactory,
    NotificationFactory,
    UserFactory,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tenant_a(db):
    """Company A with an owner-recruiter."""
    membership = CompanyMemberFactory(role="owner")
    client = APIClient()
    client.force_authenticate(user=membership.user)
    return membership.company, membership.user, client


@pytest.fixture
def tenant_b(db):
    """Company B with an owner-recruiter."""
    membership = CompanyMemberFactory(role="owner")
    client = APIClient()
    client.force_authenticate(user=membership.user)
    return membership.company, membership.user, client


@pytest.fixture
def candidate_a(db):
    """A candidate with an authenticated client."""
    user = UserFactory(role="candidate")
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@pytest.fixture
def candidate_b(db):
    """A second candidate with an authenticated client."""
    user = UserFactory(role="candidate")
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1.1 — COMPANY ISOLATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestCompanyIsolation:
    def test_recruiter_a_cannot_update_company_b(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        resp = client_a.patch(
            f"/api/companies/{company_b.slug}/",
            {"name": "Hacked"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_a_cannot_delete_company_b(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        resp = client_a.delete(f"/api/companies/{company_b.slug}/")
        assert resp.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_recruiter_a_cannot_invite_into_company_b(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        new_recruiter = UserFactory(role="recruiter")
        resp = client_a.post(
            f"/api/companies/{company_b.slug}/members/",
            {"email": new_recruiter.email},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unverified_company_excluded_from_list(self, tenant_a):
        CompanyFactory(domain_verified=False, verification_status="unverified")
        _, _, client_a = tenant_a
        resp = client_a.get("/api/companies/")
        slugs = [c["slug"] for c in resp.data["results"]]
        from apps.companies.models import Company
        unverified = Company.objects.filter(domain_verified=False)
        for c in unverified:
            assert c.slug not in slugs

    def test_owner_a_cannot_do_owner_actions_on_company_b(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        resp = client_a.put(
            f"/api/companies/{company_b.slug}/",
            {
                "name": "Overwritten",
                "slug": company_b.slug,
                "description": "x",
                "industry": "x",
                "location": "x",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1.2 — JOB ISOLATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestJobIsolation:
    def test_recruiter_a_cannot_create_job_under_company_b(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        resp = client_a.post(
            "/api/jobs/",
            {
                "company": str(company_b.id),
                "title": "Sneaky Job",
                "slug": "sneaky-job",
                "description": "x",
                "requirements": "x",
                "job_type": "full_time",
                "experience_level": "mid",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_a_cannot_publish_company_b_job(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_b = JobFactory(company=company_b, posted_by=user_b, status="draft")
        resp = client_a.post(f"/api/jobs/{job_b.slug}/publish/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_a_cannot_close_company_b_job(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_b = JobFactory(company=company_b, posted_by=user_b, status="published")
        resp = client_a.post(f"/api/jobs/{job_b.slug}/close/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_a_cannot_update_company_b_job(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_b = JobFactory(company=company_b, posted_by=user_b, status="draft")
        resp = client_a.patch(
            f"/api/jobs/{job_b.slug}/",
            {"title": "Hacked Title"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_a_cannot_delete_company_b_job(self, tenant_a, tenant_b):
        _, _, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_b = JobFactory(company=company_b, posted_by=user_b, status="draft")
        resp = client_a.delete(f"/api/jobs/{job_b.slug}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_draft_jobs_invisible_in_public_list(self, tenant_a):
        company_a, user_a, client_a = tenant_a
        JobFactory(company=company_a, posted_by=user_a, status="draft")
        anon = APIClient()
        resp = anon.get("/api/jobs/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 0

    def test_search_never_leaks_draft_jobs(self, tenant_a):
        company_a, user_a, _ = tenant_a
        job = JobFactory(
            company=company_a,
            posted_by=user_a,
            status="draft",
            title="SecretProject",
        )
        # Manually set search vector
        Job.objects.filter(pk=job.pk).update(
            search_vector=SearchVector("title", weight="A")
        )
        anon = APIClient()
        resp = anon.get("/api/jobs/search/", {"q": "SecretProject"})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1.3 — APPLICATION ISOLATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestApplicationIsolation:
    def test_recruiter_a_only_sees_own_company_applications(
        self, tenant_a, tenant_b
    ):
        company_a, user_a, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_a = JobFactory(company=company_a, posted_by=user_a, status="published")
        job_b = JobFactory(company=company_b, posted_by=user_b, status="published")
        ApplicationFactory(job=job_a)
        ApplicationFactory(job=job_b)
        resp = client_a.get("/api/applications/")
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 1

    def test_recruiter_a_cannot_advance_company_b_application(
        self, tenant_a, tenant_b
    ):
        _, _, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_b = JobFactory(company=company_b, posted_by=user_b, status="published")
        app_b = ApplicationFactory(job=job_b, status="applied")
        resp = client_a.patch(
            f"/api/applications/{app_b.id}/status/",
            {"status": "reviewing"},
            format="json",
        )
        # Returns 404 (IDOR-safe: scoped queryset hides existence)
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_candidate_a_cannot_see_candidate_b_application(
        self, candidate_a, candidate_b
    ):
        user_a, client_a = candidate_a
        user_b, _ = candidate_b
        ApplicationFactory(applicant=user_a)
        ApplicationFactory(applicant=user_b)
        resp = client_a.get("/api/applications/")
        assert len(resp.data["results"]) == 1
        # Must be candidate A's own
        app_data = resp.data["results"][0]
        assert "recruiter_notes" not in app_data

    def test_candidate_b_cannot_retrieve_candidate_a_application(
        self, candidate_a, candidate_b
    ):
        user_a, _ = candidate_a
        _, client_b = candidate_b
        app_a = ApplicationFactory(applicant=user_a)
        resp = client_b.get(f"/api/applications/{app_a.id}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_recruiter_notes_absent_from_candidate_detail(self, candidate_a):
        user_a, client_a = candidate_a
        ApplicationFactory(
            applicant=user_a, recruiter_notes="Internal confidential note"
        )
        resp = client_a.get("/api/applications/")
        for app_data in resp.data["results"]:
            assert "recruiter_notes" not in app_data

    def test_recruiter_notes_absent_from_candidate_retrieve(self, candidate_a):
        user_a, client_a = candidate_a
        app = ApplicationFactory(
            applicant=user_a, recruiter_notes="Secret"
        )
        resp = client_a.get(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert "recruiter_notes" not in resp.data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1.4 — NOTIFICATION ISOLATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestNotificationIsolation:
    def test_user_a_cannot_mark_user_b_notification_read(self):
        user_a = UserFactory()
        user_b = UserFactory()
        notif_b = NotificationFactory(user=user_b, is_read=False)
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.patch(f"/api/notifications/{notif_b.id}/read/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        notif_b.refresh_from_db()
        assert notif_b.is_read is False

    def test_user_a_list_never_contains_user_b_records(self):
        user_a = UserFactory()
        user_b = UserFactory()
        NotificationFactory(user=user_a)
        NotificationFactory(user=user_b)
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.get("/api/notifications/")
        assert len(resp.data["results"]) == 1

    def test_mark_all_read_only_affects_requesting_user(self):
        user_a = UserFactory()
        user_b = UserFactory()
        NotificationFactory(user=user_a, is_read=False)
        NotificationFactory(user=user_b, is_read=False)
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post("/api/notifications/mark-all-read/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["marked_read"] == 1
        # User B's notification untouched
        assert Notification.objects.filter(user=user_b, is_read=False).count() == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1.5 — DASHBOARD ISOLATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestDashboardIsolation:
    def test_recruiter_dashboard_scoped_to_own_companies(
        self, tenant_a, tenant_b
    ):
        company_a, user_a, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        JobFactory(company=company_a, posted_by=user_a, status="published")
        JobFactory(company=company_b, posted_by=user_b, status="published")
        resp = client_a.get("/api/dashboard/recruiter/")
        assert resp.data["total_jobs"] == 1

    def test_second_company_does_not_inflate_first_recruiter_counts(
        self, tenant_a, tenant_b
    ):
        company_a, user_a, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_a = JobFactory(company=company_a, posted_by=user_a, status="published")
        job_b = JobFactory(company=company_b, posted_by=user_b, status="published")
        ApplicationFactory(job=job_a)
        ApplicationFactory(job=job_b)
        ApplicationFactory(job=job_b)
        resp = client_a.get("/api/dashboard/recruiter/")
        assert resp.data["total_applications"] == 1

    def test_candidate_dashboard_only_own_applications(
        self, candidate_a, candidate_b
    ):
        user_a, client_a = candidate_a
        user_b, _ = candidate_b
        ApplicationFactory(applicant=user_a)
        ApplicationFactory(applicant=user_b)
        ApplicationFactory(applicant=user_b)
        resp = client_a.get("/api/dashboard/candidate/")
        assert resp.data["total_applications"] == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1.6 — IDOR SURFACE COVERAGE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestIDORSurface:
    """
    For scoped resources, accessing another tenant's resource by UUID
    must return 404 (not 403) so object existence is not leaked.
    """

    def test_application_by_uuid_returns_404_not_403(self, candidate_a, candidate_b):
        user_a, _ = candidate_a
        _, client_b = candidate_b
        app_a = ApplicationFactory(applicant=user_a)
        resp = client_b.get(f"/api/applications/{app_a.id}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_notification_by_uuid_returns_404_not_403(self):
        user_a = UserFactory()
        user_b = UserFactory()
        notif_a = NotificationFactory(user=user_a)
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        resp = client_b.patch(f"/api/notifications/{notif_a.id}/read/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_recruiter_application_by_uuid_returns_404_for_other_company(
        self, tenant_a, tenant_b
    ):
        """Recruiter A accessing app belonging to Company B's job via UUID."""
        company_b, user_b, _ = tenant_b
        _, _, client_a = tenant_a
        job_b = JobFactory(company=company_b, posted_by=user_b, status="published")
        app_b = ApplicationFactory(job=job_b)
        resp = client_a.get(f"/api/applications/{app_b.id}/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_status_update_for_other_company_app_returns_404_not_403(
        self, tenant_a, tenant_b
    ):
        """
        ApplicationStatusUpdateView should return 404 (not 403) for
        applications belonging to another company, so object existence
        is not leaked.
        """
        _, _, client_a = tenant_a
        company_b, user_b, _ = tenant_b
        job_b = JobFactory(company=company_b, posted_by=user_b, status="published")
        app_b = ApplicationFactory(job=job_b, status="applied")
        resp = client_a.patch(
            f"/api/applications/{app_b.id}/status/",
            {"status": "reviewing"},
            format="json",
        )
        # IDOR protection: must not leak existence
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SECTION 1 — GAP TESTS (added by QA audit)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.django_db
class TestCompanyMemberListIsolation:
    """Recruiter A must not be able to list Company B's members."""

    def test_recruiter_a_cannot_list_company_b_members(self, tenant_a, tenant_b):
        """GET /api/companies/{slug}/members/ for a company you don't belong to → 403."""
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        resp = client_a.get(f"/api/companies/{company_b.slug}/members/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_recruiter_a_cannot_remove_company_b_member(self, tenant_a, tenant_b):
        """DELETE /api/companies/{slug}/members/{id}/ cross-tenant → 403."""
        _, _, client_a = tenant_a
        company_b, _, _ = tenant_b
        from apps.companies.models import CompanyMember

        member_b = CompanyMember.objects.filter(company=company_b).first()
        resp = client_a.delete(
            f"/api/companies/{company_b.slug}/members/{member_b.id}/"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCrossCompanyJobVisibilityInSearch:
    """Search must not expose closed/draft jobs from any company."""

    def test_closed_job_excluded_from_search(self, tenant_a):
        """Closed jobs must never appear in search results."""
        company_a, user_a, _ = tenant_a
        job = JobFactory(
            company=company_a,
            posted_by=user_a,
            status="closed",
            title="ClosedSearchTarget",
        )
        Job.objects.filter(pk=job.pk).update(
            search_vector=SearchVector("title", weight="A")
        )
        anon = APIClient()
        resp = anon.get("/api/jobs/search/", {"q": "ClosedSearchTarget"})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 0


@pytest.mark.django_db
class TestWithdrawIsolation:
    """Only the applicant can withdraw their own application."""

    def test_recruiter_cannot_withdraw_candidate_application(self, tenant_a):
        """Recruiter sees the app but gets 403 when trying to DELETE (withdraw)."""
        company_a, user_a, client_a = tenant_a
        job_a = JobFactory(company=company_a, posted_by=user_a, status="published")
        app = ApplicationFactory(job=job_a, status="applied")
        resp = client_a.delete(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        app.refresh_from_db()
        assert app.status == "applied"  # unchanged

    def test_other_candidate_cannot_withdraw(self, candidate_a, candidate_b):
        """Candidate B cannot withdraw Candidate A's application."""
        user_a, _ = candidate_a
        _, client_b = candidate_b
        app = ApplicationFactory(applicant=user_a, status="applied")
        resp = client_b.delete(f"/api/applications/{app.id}/")
        # Scoped queryset → 404 (app not visible to candidate B)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        app.refresh_from_db()
        assert app.status == "applied"
