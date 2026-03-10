"""Tests for Dashboard aggregation endpoints."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    ApplicationFactory,
    CompanyMemberFactory,
    JobFactory,
    UserFactory,
)


def _recruiter_url():
    return "/api/dashboard/recruiter/"


def _candidate_url():
    return "/api/dashboard/candidate/"


@pytest.mark.django_db
class TestRecruiterDashboard:
    def test_returns_total_jobs(self):
        membership = CompanyMemberFactory(role="owner")
        JobFactory(company=membership.company, status="published")
        JobFactory(company=membership.company, status="draft")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_recruiter_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_jobs"] == 2

    def test_returns_jobs_by_status(self):
        membership = CompanyMemberFactory(role="owner")
        JobFactory(company=membership.company, status="published")
        JobFactory(company=membership.company, status="published")
        JobFactory(company=membership.company, status="draft")
        JobFactory(company=membership.company, status="closed")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_recruiter_url())
        assert response.data["jobs_by_status"]["published"] == 2
        assert response.data["jobs_by_status"]["draft"] == 1
        assert response.data["jobs_by_status"]["closed"] == 1

    def test_returns_total_applications(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(company=membership.company, status="published")
        ApplicationFactory(job=job)
        ApplicationFactory(job=job)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_recruiter_url())
        assert response.data["total_applications"] == 2

    def test_returns_applications_by_status(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(company=membership.company, status="published")
        ApplicationFactory(job=job, status="applied")
        ApplicationFactory(job=job, status="reviewing")
        ApplicationFactory(job=job, status="reviewing")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_recruiter_url())
        assert response.data["applications_by_status"]["applied"] == 1
        assert response.data["applications_by_status"]["reviewing"] == 2

    def test_returns_recent_applications(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(company=membership.company, status="published")
        ApplicationFactory(job=job)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_recruiter_url())
        assert len(response.data["recent_applications"]) == 1
        assert "id" in response.data["recent_applications"][0]
        assert "status" in response.data["recent_applications"][0]

    def test_only_recruiter_can_access(self):
        membership = CompanyMemberFactory(role="owner")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_recruiter_url())
        assert response.status_code == status.HTTP_200_OK

    def test_candidate_gets_403(self):
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_recruiter_url())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_scoped_to_recruiters_companies(self):
        # Company A recruiter
        membership_a = CompanyMemberFactory(role="owner")
        JobFactory(company=membership_a.company, status="published")
        # Company B (different recruiter)
        membership_b = CompanyMemberFactory(role="owner")
        JobFactory(company=membership_b.company, status="published")
        # Recruiter A should only see Company A's jobs
        client = APIClient()
        client.force_authenticate(user=membership_a.user)
        response = client.get(_recruiter_url())
        assert response.data["total_jobs"] == 1


@pytest.mark.django_db
class TestCandidateDashboard:
    def test_returns_total_applications(self):
        candidate = UserFactory(role="candidate")
        ApplicationFactory(applicant=candidate)
        ApplicationFactory(applicant=candidate)
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_candidate_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_applications"] == 2

    def test_returns_applications_by_status(self):
        candidate = UserFactory(role="candidate")
        ApplicationFactory(applicant=candidate, status="applied")
        ApplicationFactory(applicant=candidate, status="interview")
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_candidate_url())
        assert response.data["applications_by_status"]["applied"] == 1
        assert response.data["applications_by_status"]["interview"] == 1

    def test_returns_recent_applications(self):
        candidate = UserFactory(role="candidate")
        ApplicationFactory(applicant=candidate)
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_candidate_url())
        assert len(response.data["recent_applications"]) == 1
        assert "job" in response.data["recent_applications"][0]

    def test_only_candidate_can_access(self):
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_candidate_url())
        assert response.status_code == status.HTTP_200_OK

    def test_recruiter_gets_403(self):
        recruiter = UserFactory(role="recruiter")
        client = APIClient()
        client.force_authenticate(user=recruiter)
        response = client.get(_candidate_url())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_401(self):
        client = APIClient()
        response = client.get(_candidate_url())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_scoped_to_own_applications(self):
        candidate = UserFactory(role="candidate")
        ApplicationFactory(applicant=candidate)
        ApplicationFactory()  # other candidate's application
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_candidate_url())
        assert response.data["total_applications"] == 1

    def test_recent_limit_is_five(self):
        candidate = UserFactory(role="candidate")
        for _ in range(7):
            ApplicationFactory(applicant=candidate)
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_candidate_url())
        assert len(response.data["recent_applications"]) == 5
