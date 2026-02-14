"""Tests for Job filters."""

import pytest

from tests.factories import CompanyFactory, JobFactory


def _jobs_url():
    return "/api/jobs/"


@pytest.mark.django_db
class TestJobFilter:
    def test_filter_by_job_type(self, api_client):
        JobFactory(status="published", job_type="full_time", slug="ft-job")
        JobFactory(status="published", job_type="contract", slug="ct-job")
        response = api_client.get(_jobs_url(), {"job_type": "full_time"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["job_type"] == "full_time"

    def test_filter_by_experience_level(self, api_client):
        JobFactory(status="published", experience_level="senior", slug="sr-job")
        JobFactory(status="published", experience_level="junior", slug="jr-job")
        response = api_client.get(_jobs_url(), {"experience_level": "senior"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_is_remote(self, api_client):
        JobFactory(status="published", is_remote=True, slug="remote-job")
        JobFactory(status="published", is_remote=False, slug="onsite-job")
        response = api_client.get(_jobs_url(), {"is_remote": "true"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["is_remote"] is True

    def test_filter_by_salary_range(self, api_client):
        JobFactory(status="published", salary_min=80000, salary_max=120000, slug="high-pay")
        JobFactory(status="published", salary_min=30000, salary_max=50000, slug="low-pay")
        response = api_client.get(_jobs_url(), {"salary_min": 70000})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_location(self, api_client):
        JobFactory(status="published", location="New York", slug="ny-job")
        JobFactory(status="published", location="London", slug="ldn-job")
        response = api_client.get(_jobs_url(), {"location": "New York"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_company(self, api_client):
        company = CompanyFactory()
        JobFactory(status="published", company=company, slug="c1-job")
        JobFactory(status="published", slug="c2-job")
        response = api_client.get(_jobs_url(), {"company": str(company.id)})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_multi_value_job_type(self, api_client):
        JobFactory(status="published", job_type="full_time", slug="ft-multi")
        JobFactory(status="published", job_type="contract", slug="ct-multi")
        JobFactory(status="published", job_type="internship", slug="int-multi")
        response = api_client.get(
            _jobs_url(), {"job_type": ["full_time", "contract"]}
        )
        assert response.status_code == 200
        assert len(response.data["results"]) == 2
