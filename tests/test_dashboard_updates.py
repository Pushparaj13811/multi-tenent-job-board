"""
Tests for Part E — Updated dashboard data with verification status and top jobs.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.applications.models import Application
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job

RECRUITER_DASHBOARD_URL = "/api/dashboard/recruiter/"


@pytest.mark.django_db
class TestRecruiterDashboardUpdated:
    def _setup(self):
        recruiter = User.objects.create_user(
            email="rec@acme.com", username="rec", password="pass123!", role="recruiter",
        )
        company = Company.objects.create(
            name="Acme", slug="acme",
            domain_verified=True, verification_status="verified",
        )
        CompanyMember.objects.create(user=recruiter, company=company, role="owner")

        job1 = Job.objects.create(
            title="Job A", slug="job-a", company=company, posted_by=recruiter,
            status="published", description="desc", job_type="full_time",
            experience_level="mid",
        )
        job2 = Job.objects.create(
            title="Job B", slug="job-b", company=company, posted_by=recruiter,
            status="published", description="desc", job_type="full_time",
            experience_level="mid",
        )
        # Create applications for job1 (more apps) and job2 (fewer)
        for i in range(3):
            candidate = User.objects.create_user(
                email=f"c{i}@test.com", username=f"c{i}", password="pass123!", role="candidate",
            )
            Application.objects.create(
                job=job1, applicant=candidate, status="applied",
                cover_letter="Cover letter",
            )
        candidate_extra = User.objects.create_user(
            email="extra@test.com", username="extra", password="pass123!", role="candidate",
        )
        Application.objects.create(
            job=job2, applicant=candidate_extra, status="applied",
            cover_letter="Cover letter",
        )

        client = APIClient()
        client.force_authenticate(user=recruiter)
        return client, company

    def test_dashboard_includes_company_verification_status(self):
        client, company = self._setup()
        response = client.get(RECRUITER_DASHBOARD_URL)
        assert response.status_code == 200
        data = response.json()
        assert "companies" in data
        company_data = data["companies"]
        assert len(company_data) > 0
        assert company_data[0]["verification_status"] == "verified"

    def test_dashboard_includes_top_jobs(self):
        client, company = self._setup()
        response = client.get(RECRUITER_DASHBOARD_URL)
        data = response.json()
        assert "top_jobs" in data
        assert len(data["top_jobs"]) > 0

    def test_top_jobs_ordered_by_application_count(self):
        client, company = self._setup()
        response = client.get(RECRUITER_DASHBOARD_URL)
        data = response.json()
        top_jobs = data["top_jobs"]
        # Job A has 3 applications, Job B has 1
        assert top_jobs[0]["title"] == "Job A"
        assert top_jobs[0]["application_count"] == 3

    def test_dashboard_still_has_original_fields(self):
        client, _ = self._setup()
        response = client.get(RECRUITER_DASHBOARD_URL)
        data = response.json()
        assert "total_jobs" in data
        assert "jobs_by_status" in data
        assert "total_applications" in data
        assert "applications_by_status" in data
        assert "recent_applications" in data
