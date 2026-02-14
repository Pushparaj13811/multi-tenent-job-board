"""Tests for Job API endpoints."""


import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.jobs.models import Job
from tests.factories import CompanyFactory, CompanyMemberFactory, JobFactory, UserFactory


def _jobs_url():
    return "/api/jobs/"


def _job_detail_url(slug):
    return f"/api/jobs/{slug}/"


def _publish_url(slug):
    return f"/api/jobs/{slug}/publish/"


def _close_url(slug):
    return f"/api/jobs/{slug}/close/"


def _search_url():
    return "/api/jobs/search/"


@pytest.fixture
def company_with_recruiter(db):
    """Returns (company, recruiter_user, authenticated_client)."""
    membership = CompanyMemberFactory(role="owner")
    client = APIClient()
    client.force_authenticate(user=membership.user)
    return membership.company, membership.user, client


@pytest.mark.django_db
class TestListJobs:
    def test_returns_only_published(self, api_client):
        JobFactory(status="published")
        JobFactory(status="draft")
        response = api_client.get(_jobs_url())
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_publicly_accessible(self, api_client):
        response = api_client.get(_jobs_url())
        assert response.status_code == status.HTTP_200_OK

    def test_pagination_returns_cursor(self, api_client):
        for i in range(25):
            JobFactory(status="published", slug=f"job-list-{i}")
        response = api_client.get(_jobs_url())
        assert response.status_code == status.HTTP_200_OK
        assert response.data["next"] is not None


@pytest.mark.django_db
class TestCreateJob:
    def test_member_can_create(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        data = {
            "company": str(company.id),
            "title": "Django Developer",
            "slug": "django-dev",
            "description": "Build APIs.",
            "requirements": "3 years Python.",
            "job_type": "full_time",
            "experience_level": "mid",
        }
        response = client.post(_jobs_url(), data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "draft"

    def test_default_status_draft(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        data = {
            "company": str(company.id),
            "title": "Another Job",
            "slug": "another-job",
            "description": "Description.",
            "requirements": "Requirements.",
            "job_type": "full_time",
            "experience_level": "junior",
        }
        response = client.post(_jobs_url(), data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Job.objects.get(slug="another-job").status == "draft"

    def test_non_member_denied(self):
        company = CompanyFactory()
        outsider = UserFactory(role="recruiter")
        client = APIClient()
        client.force_authenticate(user=outsider)
        data = {
            "company": str(company.id),
            "title": "Job",
            "slug": "outsider-job",
            "description": "Desc.",
            "requirements": "Req.",
            "job_type": "contract",
            "experience_level": "senior",
        }
        response = client.post(_jobs_url(), data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_salary_max_less_than_min_returns_400(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        data = {
            "company": str(company.id),
            "title": "Bad Salary Job",
            "slug": "bad-salary",
            "description": "Desc.",
            "requirements": "Req.",
            "job_type": "full_time",
            "experience_level": "mid",
            "salary_min": 100000,
            "salary_max": 50000,
        }
        response = client.post(_jobs_url(), data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestJobDetail:
    def test_retrieve_by_slug(self, api_client):
        job = JobFactory(status="published", slug="my-job")
        response = api_client.get(_job_detail_url("my-job"))
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == job.title

    def test_increments_views_count(self, api_client):
        job = JobFactory(status="published", slug="view-test")
        assert job.views_count == 0
        api_client.get(_job_detail_url("view-test"))
        api_client.get(_job_detail_url("view-test"))
        job.refresh_from_db()
        assert job.views_count == 2


@pytest.mark.django_db
class TestPublishJob:
    def test_publish_draft(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        job = JobFactory(status="draft", company=company, posted_by=user)
        response = client.post(_publish_url(job.slug))
        assert response.status_code == status.HTTP_200_OK
        job.refresh_from_db()
        assert job.status == "published"

    def test_already_published_returns_400(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        job = JobFactory(status="published", company=company, posted_by=user)
        response = client.post(_publish_url(job.slug))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_member_denied(self):
        job = JobFactory(status="draft")
        outsider = UserFactory(role="recruiter")
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.post(_publish_url(job.slug))
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestCloseJob:
    def test_close_published(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        job = JobFactory(status="published", company=company, posted_by=user)
        response = client.post(_close_url(job.slug))
        assert response.status_code == status.HTTP_200_OK
        job.refresh_from_db()
        assert job.status == "closed"

    def test_draft_returns_400(self, company_with_recruiter):
        company, user, client = company_with_recruiter
        job = JobFactory(status="draft", company=company, posted_by=user)
        response = client.post(_close_url(job.slug))
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestJobSearch:
    def _create_and_index(self, **kwargs):
        from django.contrib.postgres.search import SearchVector

        job = JobFactory(**kwargs)
        Job.objects.filter(pk=job.pk).update(
            search_vector=(
                SearchVector("title", weight="A")
                + SearchVector("description", weight="B")
            )
        )
        job.refresh_from_db()
        return job

    def test_search_returns_matching_results(self, api_client):
        self._create_and_index(
            status="published", title="Django REST Framework Expert", description="Build APIs."
        )
        response = api_client.get(_search_url(), {"q": "Django"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1

    def test_search_ordered_by_rank(self, api_client):
        company = CompanyFactory()
        self._create_and_index(
            status="published",
            title="Python Developer",
            description="A generic role.",
            company=company,
            slug="search-rank-1",
        )
        self._create_and_index(
            status="published",
            title="Generic Role",
            description="Needs Python skills.",
            company=company,
            slug="search-rank-2",
        )
        response = api_client.get(_search_url(), {"q": "Python"})
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) >= 1
        # Title match should rank first
        assert results[0]["title"] == "Python Developer"

    def test_missing_q_returns_400(self, api_client):
        response = api_client.get(_search_url())
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_results_empty(self, api_client):
        self._create_and_index(status="published", title="Java Developer")
        response = api_client.get(_search_url(), {"q": "xyznonexistent"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0
