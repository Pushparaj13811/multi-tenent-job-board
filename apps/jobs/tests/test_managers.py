"""Tests for the Job custom manager methods."""

import datetime

import pytest
from django.contrib.postgres.search import SearchVector
from django.utils import timezone

from apps.jobs.models import Job
from tests.factories import CompanyFactory, JobFactory


def _index_search_vector(job):
    """Manually populate search_vector for a job."""
    Job.objects.filter(pk=job.pk).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
        )
    )
    job.refresh_from_db()
    return job


@pytest.mark.django_db
class TestJobManagerPublished:
    def test_returns_published_jobs(self):
        published = JobFactory(status="published")
        JobFactory(status="draft")
        qs = Job.objects.published()
        assert published in qs
        assert qs.count() == 1

    def test_excludes_jobs_with_past_deadline(self):
        yesterday = timezone.now().date() - datetime.timedelta(days=1)
        JobFactory(status="published", deadline=yesterday)
        assert Job.objects.published().count() == 0

    def test_includes_jobs_with_future_deadline(self):
        tomorrow = timezone.now().date() + datetime.timedelta(days=1)
        job = JobFactory(status="published", deadline=tomorrow)
        qs = Job.objects.published()
        assert job in qs

    def test_includes_jobs_with_no_deadline(self):
        job = JobFactory(status="published", deadline=None)
        qs = Job.objects.published()
        assert job in qs

    def test_includes_jobs_with_today_as_deadline(self):
        today = timezone.now().date()
        job = JobFactory(status="published", deadline=today)
        qs = Job.objects.published()
        assert job in qs


@pytest.mark.django_db
class TestJobManagerSearch:
    def test_search_matches_title(self):
        job = JobFactory(
            status="published", title="Django Developer Position", description="A great role."
        )
        _index_search_vector(job)
        results = Job.objects.search("Django")
        assert job in results

    def test_search_matches_description(self):
        job = JobFactory(
            status="published",
            title="Software Role",
            description="We need an expert in PostgreSQL databases.",
        )
        _index_search_vector(job)
        results = Job.objects.search("PostgreSQL")
        assert job in results

    def test_title_ranks_higher_than_description(self):
        company = CompanyFactory()
        job_title = JobFactory(
            status="published",
            title="Python Engineer",
            description="A generic role.",
            company=company,
        )
        job_desc = JobFactory(
            status="published",
            title="Generic Role",
            description="We need a Python engineer.",
            company=company,
        )
        _index_search_vector(job_title)
        _index_search_vector(job_desc)
        results = list(Job.objects.search("Python"))
        assert len(results) == 2
        assert results[0] == job_title

    def test_search_excludes_draft_jobs(self):
        job = JobFactory(status="draft", title="Django Developer")
        _index_search_vector(job)
        results = Job.objects.search("Django")
        assert job not in results

    def test_empty_for_no_match(self):
        job = JobFactory(status="published", title="Python Developer")
        _index_search_vector(job)
        results = Job.objects.search("xyznonexistent")
        assert results.count() == 0


@pytest.mark.django_db
class TestJobManagerWithApplicationCount:
    def test_annotates_count(self):
        job = JobFactory(status="published")
        qs = Job.objects.with_application_count()
        assert job in qs
        assert qs.get(pk=job.pk).application_count == 0

    def test_zero_applications(self):
        job = JobFactory(status="published")
        result = Job.objects.with_application_count().get(pk=job.pk)
        assert result.application_count == 0

    def test_excludes_drafts(self):
        JobFactory(status="draft")
        qs = Job.objects.with_application_count()
        assert qs.count() == 0
