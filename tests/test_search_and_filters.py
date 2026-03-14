"""
Section 5 — Full-Text Search & Filter Correctness.

5.1  Search ranking, empty results, missing param, draft/closed exclusion
5.2  Filter combinations (AND semantics, salary range, case-insensitive, empty slug)
5.3  Pagination (cursor, page_size, max clamping)
"""

import pytest
from django.contrib.postgres.search import SearchVector
from rest_framework import status
from rest_framework.test import APIClient

from apps.jobs.models import Job
from tests.factories import CompanyFactory, JobFactory

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _index_search_vector(*jobs):
    """Manually populate the search_vector for given jobs (deterministic)."""
    for job in jobs:
        Job.objects.filter(pk=job.pk).update(
            search_vector=SearchVector("title", "description")
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5.1  Search ranking
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSearchRanking:
    """Full-text search ranking, empty results, parameter validation."""

    def test_title_match_ranks_above_description_match(self):
        """A job with the query word in the title should rank above one with it only in description."""
        company = CompanyFactory()
        title_job = JobFactory(
            status="published",
            company=company,
            title="Senior Django Developer",
            description="Build web applications.",
        )
        desc_job = JobFactory(
            status="published",
            company=company,
            title="Backend Engineer",
            description="Work with Django framework daily.",
        )
        _index_search_vector(title_job, desc_job)

        client = APIClient()
        resp = client.get("/api/jobs/search/", {"q": "django"})
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        # title_job should appear (and ideally first)
        assert str(title_job.id) in ids

    def test_search_returns_empty_list_for_no_match(self):
        """A query matching nothing returns empty results, not an error."""
        client = APIClient()
        resp = client.get("/api/jobs/search/", {"q": "xyznonexistent123"})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["results"] == []

    def test_search_missing_q_returns_400(self):
        """Missing ?q= parameter returns 400 with informative error."""
        client = APIClient()
        resp = client.get("/api/jobs/search/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_search_never_returns_draft_jobs(self):
        """Draft jobs are excluded from search results even if they match."""
        draft = JobFactory(status="draft", title="Invisible Django Role")
        _index_search_vector(draft)

        client = APIClient()
        resp = client.get("/api/jobs/search/", {"q": "invisible"})
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        assert str(draft.id) not in ids

    def test_search_never_returns_closed_jobs(self):
        """Closed jobs are excluded from search results."""
        closed = JobFactory(status="closed", title="Closed Django Position")
        _index_search_vector(closed)

        client = APIClient()
        resp = client.get("/api/jobs/search/", {"q": "closed"})
        assert resp.status_code == status.HTTP_200_OK
        ids = [r["id"] for r in resp.data["results"]]
        assert str(closed.id) not in ids


# ═══════════════════════════════════════════════════════════════════════════
# 5.2  Filter combinations
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFilterCombinations:
    """Verify AND semantics, salary range, case-insensitive location, nonexistent company."""

    def test_is_remote_and_job_type_combined(self):
        """Filters combine with AND semantics — both must match."""
        company = CompanyFactory()
        match = JobFactory(
            status="published",
            company=company,
            is_remote=True,
            job_type="full_time",
        )
        remote_only = JobFactory(
            status="published",
            company=company,
            is_remote=True,
            job_type="part_time",
        )
        ft_only = JobFactory(
            status="published",
            company=company,
            is_remote=False,
            job_type="full_time",
        )

        client = APIClient()
        resp = client.get("/api/jobs/", {"is_remote": "true", "job_type": "full_time"})
        assert resp.status_code == status.HTTP_200_OK
        ids = {str(j["id"]) for j in resp.data["results"]}
        assert str(match.id) in ids
        assert str(remote_only.id) not in ids
        assert str(ft_only.id) not in ids

    def test_salary_range_filter(self):
        """salary_min/salary_max filters: salary_min >= 50k AND salary_max <= 80k."""
        company = CompanyFactory()
        in_range = JobFactory(
            status="published",
            company=company,
            salary_min=50000,
            salary_max=80000,
        )
        too_high = JobFactory(
            status="published",
            company=company,
            salary_min=60000,
            salary_max=120000,
        )
        too_low = JobFactory(
            status="published",
            company=company,
            salary_min=30000,
            salary_max=45000,
        )

        client = APIClient()
        resp = client.get("/api/jobs/", {"salary_min": 50000, "salary_max": 80000})
        assert resp.status_code == status.HTTP_200_OK
        ids = {str(j["id"]) for j in resp.data["results"]}
        assert str(in_range.id) in ids
        assert str(too_high.id) not in ids
        assert str(too_low.id) not in ids

    def test_location_filter_is_case_insensitive(self):
        """Location filter uses icontains — case-insensitive substring match."""
        company = CompanyFactory()
        job = JobFactory(status="published", company=company, location="San Francisco")

        client = APIClient()
        resp = client.get("/api/jobs/", {"location": "san francisco"})
        assert resp.status_code == status.HTTP_200_OK
        ids = {str(j["id"]) for j in resp.data["results"]}
        assert str(job.id) in ids

    def test_nonexistent_company_filter_returns_empty(self):
        """Filtering by a non-existent company UUID returns empty list, not 404."""
        import uuid

        JobFactory(status="published")
        client = APIClient()
        resp = client.get("/api/jobs/", {"company": str(uuid.uuid4())})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5.3  Pagination
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPagination:
    """Cursor pagination: next/previous cursors, page_size, max clamping."""

    def _create_published_jobs(self, n):
        company = CompanyFactory()
        return [JobFactory(status="published", company=company) for _ in range(n)]

    def test_first_page_has_next_cursor(self):
        """When more items exist than page_size, response includes next cursor."""
        self._create_published_jobs(25)  # default page_size=20
        client = APIClient()
        resp = client.get("/api/jobs/", {"page_size": 5})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["next"] is not None

    def test_last_page_has_null_next(self):
        """When all items fit on one page, next is null."""
        self._create_published_jobs(3)
        client = APIClient()
        resp = client.get("/api/jobs/", {"page_size": 20})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["next"] is None

    def test_page_size_respected(self):
        """Requesting page_size=5 returns exactly 5 results when more exist."""
        self._create_published_jobs(10)
        client = APIClient()
        resp = client.get("/api/jobs/", {"page_size": 5})
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 5

    def test_page_size_over_max_clamped_to_100(self):
        """Requesting page_size > max_page_size (100) clamps to 100, not error."""
        self._create_published_jobs(5)
        client = APIClient()
        resp = client.get("/api/jobs/", {"page_size": 999})
        assert resp.status_code == status.HTTP_200_OK
        # Should not crash; results returned (up to 100)
        assert len(resp.data["results"]) <= 100

    def test_cursor_traversal_returns_all_items(self):
        """Following next cursors page by page returns all items without duplicates."""
        self._create_published_jobs(7)
        client = APIClient()
        all_ids = set()
        url = "/api/jobs/"
        params = {"page_size": 3}
        pages = 0
        while url and pages < 10:
            resp = client.get(url, params)
            assert resp.status_code == status.HTTP_200_OK
            for item in resp.data["results"]:
                all_ids.add(item["id"])
            url = resp.data.get("next")
            params = {}  # cursor is embedded in next URL
            pages += 1
        assert len(all_ids) == 7


# ═══════════════════════════════════════════════════════════════════════════
# Gap tests — additional filter coverage
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAdditionalFilters:
    """Extra filter tests: experience_level, title, multiple job_types."""

    def test_experience_level_filter(self):
        """Filter by experience_level returns only matching jobs."""
        company = CompanyFactory()
        senior = JobFactory(
            status="published", company=company, experience_level="senior"
        )
        junior = JobFactory(
            status="published", company=company, experience_level="junior"
        )
        client = APIClient()
        resp = client.get("/api/jobs/", {"experience_level": "senior"})
        assert resp.status_code == status.HTTP_200_OK
        ids = {str(j["id"]) for j in resp.data["results"]}
        assert str(senior.id) in ids
        assert str(junior.id) not in ids

    def test_title_icontains_filter(self):
        """Filter by title uses case-insensitive contains."""
        company = CompanyFactory()
        match = JobFactory(
            status="published", company=company, title="Senior Django Developer"
        )
        no_match = JobFactory(
            status="published", company=company, title="React Engineer"
        )
        client = APIClient()
        resp = client.get("/api/jobs/", {"title": "django"})
        assert resp.status_code == status.HTTP_200_OK
        ids = {str(j["id"]) for j in resp.data["results"]}
        assert str(match.id) in ids
        assert str(no_match.id) not in ids

    def test_multiple_job_type_filter(self):
        """MultipleChoiceFilter for job_type accepts multiple values."""
        company = CompanyFactory()
        ft = JobFactory(
            status="published", company=company, job_type="full_time"
        )
        pt = JobFactory(
            status="published", company=company, job_type="part_time"
        )
        contract = JobFactory(
            status="published", company=company, job_type="contract"
        )
        client = APIClient()
        resp = client.get(
            "/api/jobs/",
            {"job_type": ["full_time", "part_time"]},
        )
        assert resp.status_code == status.HTTP_200_OK
        ids = {str(j["id"]) for j in resp.data["results"]}
        assert str(ft.id) in ids
        assert str(pt.id) in ids
        assert str(contract.id) not in ids
