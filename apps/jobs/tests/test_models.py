"""Tests for the Job model."""

import pytest
from django.db import IntegrityError

from apps.jobs.models import Job
from tests.factories import CompanyFactory, JobFactory, UserFactory


@pytest.mark.django_db
class TestJobModel:
    def test_create_job(self):
        job = JobFactory()
        assert Job.objects.filter(pk=job.pk).exists()

    def test_slug_is_unique(self):
        JobFactory(slug="unique-job")
        with pytest.raises(IntegrityError):
            JobFactory(slug="unique-job")

    def test_default_status_is_draft(self):
        job = JobFactory()
        assert job.status == "draft"

    def test_str_returns_title(self):
        job = JobFactory(title="Senior Django Developer")
        assert str(job) == "Senior Django Developer"

    def test_skills_default_empty_list(self):
        job = JobFactory(skills=[])
        assert job.skills == []

    def test_views_count_default_zero(self):
        job = JobFactory()
        assert job.views_count == 0

    def test_status_choices(self):
        choices = {c[0] for c in Job.Status.choices}
        assert choices == {"draft", "published", "closed"}

    def test_posted_by_set_null_on_delete(self):
        user = UserFactory(role="recruiter")
        job = JobFactory(posted_by=user)
        user.delete()
        job.refresh_from_db()
        assert job.posted_by is None

    def test_company_cascade_on_delete(self):
        company = CompanyFactory()
        job = JobFactory(company=company)
        job_pk = job.pk
        company.delete()
        assert not Job.objects.filter(pk=job_pk).exists()
