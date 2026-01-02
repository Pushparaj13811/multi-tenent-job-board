# HireFlow — Testing Strategy

> Comprehensive testing guide for the HireFlow multi-tenant job board API.
>
> Stack: pytest + pytest-django + factory_boy + unittest.mock

---

## Table of Contents

1. [Testing Philosophy](#1-testing-philosophy)
2. [Test Structure](#2-test-structure)
3. [Unit Tests](#3-unit-tests)
4. [Integration Tests](#4-integration-tests)
5. [Signal Tests](#5-signal-tests)
6. [Celery Task Tests](#6-celery-task-tests)
7. [Factory Setup](#7-factory-setup)
8. [Test Database and Fixtures](#8-test-database-and-fixtures)
9. [Coverage Targets](#9-coverage-targets)
10. [CI Integration](#10-ci-integration)

---

## 1. Testing Philosophy

### What We Test and Why

HireFlow is a Django REST API. Every incoming HTTP request passes through a predictable
stack: **middleware → authentication → permissions → serializer validation → view logic →
ORM → database**. Our test strategy mirrors this stack, testing each layer at the
appropriate level of isolation.

### The Testing Pyramid for Django/DRF

```
                    ╱╲
                   ╱  ╲
                  ╱ E2E╲          ← We don't write these. The frontend team
                 ╱______╲           or QA owns E2E tests against a staging env.
                ╱        ╲
               ╱Integration╲      ← API tests via DRF's APIClient. Test the full
              ╱______________╲       request-response cycle: auth, permissions,
             ╱                ╲      serialization, DB writes, signals firing.
            ╱    Unit Tests    ╲   ← Isolated tests for managers, validators,
           ╱____________________╲    permissions, Pydantic schemas, and Celery
                                     tasks. No HTTP layer involved.
```

### Where the Boundaries Are

| Layer | Test Type | DB Required? | What It Proves |
|-------|-----------|-------------|----------------|
| Custom ORM managers | Unit | Yes (PostgreSQL for FTS) | Query logic returns the correct rows |
| Validators (`validate_resume`) | Unit | No | Validation rules accept/reject the right inputs |
| Pydantic schemas | Unit | No | Celery task payloads are validated before DB access |
| Permission classes | Unit | Yes (needs User + Company rows) | Access control logic is correct |
| Serializers | Unit | Yes (FK validation) | Request payloads are validated and transformed correctly |
| API endpoints | Integration | Yes | Full stack: auth → permission → validation → DB → signal → response |
| Signals | Integration | Yes (signal fires on DB write) | Side effects (Celery task dispatch) happen at the right time |
| Celery tasks | Unit | Yes (task loads from DB) | Email is sent, retries work, failures are handled |

### What We Do NOT Test

- **Django internals**: `auto_now_add` works, `CharField(max_length=255)` enforces
  length, `UNIQUE` constraints raise `IntegrityError`. Django has its own test suite.
- **Third-party packages**: SimpleJWT token encoding, `django-filter` query generation,
  `drf-spectacular` schema rendering. These are tested by their maintainers.
- **Database engine behavior**: PostgreSQL foreign key cascades, GIN index performance.
  Trust the database.

### Key Principle

> Test **your** code. If you wrote custom logic — a manager method, a permission class,
> a signal handler, a serializer validation rule — test it. If Django or DRF wrote it,
> don't.

---

## 2. Test Structure

### Directory Layout

```
hireflow/
├── apps/
│   ├── accounts/
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_models.py          # User model properties (is_recruiter, is_candidate)
│   │       └── test_views.py           # Register, login, verify-email endpoints
│   │
│   ├── companies/
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_models.py          # Company/CompanyMember str representations
│   │       └── test_views.py           # CRUD + member invite endpoints
│   │
│   ├── jobs/
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_managers.py        # JobManager: published(), search(), with_application_count()
│   │       ├── test_views.py           # CRUD + publish/close + search endpoints
│   │       ├── test_filters.py         # JobFilter behavior
│   │       └── test_tasks.py           # close_expired_jobs task
│   │
│   ├── applications/
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_views.py           # Apply, list, status update, withdraw
│   │       ├── test_signals.py         # on_application_created, on_status_change
│   │       └── test_models.py          # unique_together constraint
│   │
│   └── notifications/
│       └── tests/
│           ├── __init__.py
│           ├── test_tasks.py           # Email tasks + retry behavior
│           ├── test_schemas.py         # Pydantic payload validation
│           └── test_views.py           # Notification list, mark-read
│
├── common/
│   └── tests/
│       ├── __init__.py
│       ├── test_validators.py          # validate_resume
│       └── test_permissions.py         # IsRecruiter, IsCompanyMember, IsOwnerOrReadOnly
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Root conftest — shared fixtures, API client helpers
│   └── factories.py                    # All factory_boy factories in one place
│
├── pytest.ini                          # (or pyproject.toml [tool.pytest.ini_options])
└── setup.cfg                           # Coverage config
```

### Naming Conventions

| Convention | Example | Why |
|------------|---------|-----|
| Test files start with `test_` | `test_managers.py` | pytest auto-discovery |
| Test classes: `Test<Thing>` | `TestJobManager` | Groups related tests in output |
| Test methods: `test_<action>_<condition>_<expectation>` | `test_published_excludes_expired_jobs` | Reads like a sentence when it fails |
| Factories: `<Model>Factory` | `JobFactory` | Matches the model name |
| Fixtures: lowercase, descriptive | `published_job`, `recruiter_user` | Self-documenting in test signatures |

---

## 3. Unit Tests

### 3.1 JobManager — Custom Query Methods

```python
# apps/jobs/tests/test_managers.py
"""
Tests for JobManager custom methods.
These require a real PostgreSQL database because they use:
- Full-text search (SearchVector, SearchQuery, SearchRank)
- Date comparisons (timezone.now())
- Annotations (Count)
"""
import pytest
from datetime import timedelta
from django.utils import timezone

from apps.jobs.models import Job
from tests.factories import JobFactory, ApplicationFactory, CompanyFactory


@pytest.mark.django_db
class TestJobManagerPublished:
    """Job.objects.published() — returns only published, non-expired jobs."""

    def test_returns_published_jobs(self):
        published = JobFactory(status=Job.Status.PUBLISHED)
        JobFactory(status=Job.Status.DRAFT)
        JobFactory(status=Job.Status.CLOSED)

        result = Job.objects.published()

        assert list(result) == [published]

    def test_excludes_jobs_with_past_deadline(self):
        yesterday = timezone.now().date() - timedelta(days=1)
        JobFactory(status=Job.Status.PUBLISHED, deadline=yesterday)

        result = Job.objects.published()

        assert result.count() == 0

    def test_includes_jobs_with_future_deadline(self):
        tomorrow = timezone.now().date() + timedelta(days=1)
        job = JobFactory(status=Job.Status.PUBLISHED, deadline=tomorrow)

        result = Job.objects.published()

        assert list(result) == [job]

    def test_includes_jobs_with_no_deadline(self):
        """Jobs without a deadline never expire — always included if published."""
        job = JobFactory(status=Job.Status.PUBLISHED, deadline=None)

        result = Job.objects.published()

        assert list(result) == [job]

    def test_includes_jobs_with_today_as_deadline(self):
        """Deadline is inclusive — a job expiring today is still visible."""
        today = timezone.now().date()
        job = JobFactory(status=Job.Status.PUBLISHED, deadline=today)

        result = Job.objects.published()

        assert list(result) == [job]


@pytest.mark.django_db
class TestJobManagerSearch:
    """Job.objects.search(query) — full-text search with ranking."""

    @pytest.fixture(autouse=True)
    def _populate_search_vectors(self):
        """
        Force search_vector population after factory creates.
        In production this happens via post_save signal, but in tests we
        call the raw SQL update to avoid signal-ordering issues.
        """
        yield
        # Cleanup handled by pytest-django's transaction rollback

    @staticmethod
    def _create_and_index(**kwargs):
        """Create a job and manually populate its search_vector."""
        from django.contrib.postgres.search import SearchVector

        job = JobFactory(status=Job.Status.PUBLISHED, **kwargs)
        Job.objects.filter(pk=job.pk).update(
            search_vector=(
                SearchVector("title", weight="A")
                + SearchVector("description", weight="B")
            )
        )
        job.refresh_from_db()
        return job

    def test_search_matches_title(self):
        job = self._create_and_index(
            title="Senior Django Developer",
            description="Work on a large-scale API.",
        )
        self._create_and_index(
            title="Senior React Developer",
            description="Build interactive UIs.",
        )

        results = Job.objects.search("Django")

        assert job in results
        assert results.count() == 1

    def test_search_matches_description(self):
        job = self._create_and_index(
            title="Backend Engineer",
            description="Build REST APIs with Django and PostgreSQL.",
        )

        results = Job.objects.search("PostgreSQL")

        assert job in results

    def test_title_match_ranks_higher_than_description_match(self):
        """Title has weight 'A', description has weight 'B'."""
        title_match = self._create_and_index(
            title="Django Developer",
            description="General backend work.",
        )
        desc_match = self._create_and_index(
            title="Backend Engineer",
            description="Experience with Django required.",
        )

        results = list(Job.objects.search("Django"))

        assert results[0] == title_match
        assert results[1] == desc_match

    def test_search_excludes_draft_jobs(self):
        """search() calls published() internally — drafts are excluded."""
        from django.contrib.postgres.search import SearchVector

        draft = JobFactory(status=Job.Status.DRAFT, title="Django Developer")
        Job.objects.filter(pk=draft.pk).update(
            search_vector=SearchVector("title", weight="A")
        )

        results = Job.objects.search("Django")

        assert results.count() == 0

    def test_search_returns_empty_for_no_match(self):
        self._create_and_index(
            title="Python Developer",
            description="Build APIs.",
        )

        results = Job.objects.search("Kubernetes")

        assert results.count() == 0

    def test_minimum_rank_threshold(self):
        """Results below rank 0.1 are excluded."""
        self._create_and_index(
            title="Office Manager",
            description="Manage the office, order supplies, and handle logistics.",
        )

        # "python" doesn't appear anywhere — rank should be 0 or below threshold
        results = Job.objects.search("python")

        assert results.count() == 0


@pytest.mark.django_db
class TestJobManagerWithApplicationCount:
    """Job.objects.with_application_count() — annotates published jobs."""

    def test_annotates_application_count(self):
        job = JobFactory(status=Job.Status.PUBLISHED)
        ApplicationFactory.create_batch(3, job=job)

        result = Job.objects.with_application_count().get(pk=job.pk)

        assert result.application_count == 3

    def test_zero_applications(self):
        job = JobFactory(status=Job.Status.PUBLISHED)

        result = Job.objects.with_application_count().get(pk=job.pk)

        assert result.application_count == 0

    def test_excludes_draft_jobs(self):
        draft = JobFactory(status=Job.Status.DRAFT)
        ApplicationFactory(job=draft)

        result = Job.objects.with_application_count()

        assert not result.filter(pk=draft.pk).exists()
```

---

### 3.2 validate_resume Validator

```python
# common/tests/test_validators.py
"""
Tests for the resume file validator.
These are pure unit tests — no database required.
"""
import pytest
from io import BytesIO
from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from common.validators import validate_resume


class TestValidateResume:
    """Tests for validate_resume() — checks extension, size, and MIME type."""

    @pytest.mark.parametrize(
        "filename,content_type",
        [
            ("resume.pdf", "application/pdf"),
            ("resume.doc", "application/msword"),
            (
                "resume.docx",
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
            ),
        ],
        ids=["pdf", "doc", "docx"],
    )
    def test_valid_file_passes(self, filename, content_type):
        """Valid resume files (PDF, DOC, DOCX under 5MB) should not raise."""
        file = SimpleUploadedFile(
            name=filename,
            content=b"%PDF-1.4 fake content",
            content_type=content_type,
        )

        # Should not raise
        validate_resume(file)

    @pytest.mark.parametrize(
        "filename",
        ["resume.exe", "resume.py", "resume.jpg", "resume.txt", "resume.zip"],
        ids=["exe", "py", "jpg", "txt", "zip"],
    )
    def test_wrong_extension_raises(self, filename):
        file = SimpleUploadedFile(
            name=filename,
            content=b"some content",
            content_type="application/octet-stream",
        )

        with pytest.raises(ValidationError, match="not allowed"):
            validate_resume(file)

    def test_file_too_large_raises(self):
        """Files over 5MB should be rejected."""
        # Create a file just over 5MB
        content = b"x" * (5 * 1024 * 1024 + 1)
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=content,
            content_type="application/pdf",
        )

        with pytest.raises(ValidationError, match="5MB"):
            validate_resume(file)

    def test_file_exactly_at_limit_passes(self):
        """A file that is exactly 5MB should pass."""
        content = b"x" * (5 * 1024 * 1024)
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=content,
            content_type="application/pdf",
        )

        # Should not raise
        validate_resume(file)

    def test_wrong_mime_type_raises(self):
        """A .pdf file with a wrong Content-Type header should be rejected."""
        file = SimpleUploadedFile(
            name="resume.pdf",
            content=b"fake content",
            content_type="image/jpeg",
        )

        with pytest.raises(ValidationError, match="MIME type"):
            validate_resume(file)

    def test_missing_content_type_does_not_crash(self):
        """If the file object has no content_type attribute, skip MIME check."""
        file = MagicMock()
        file.name = "resume.pdf"
        file.size = 1024
        # Remove content_type attribute entirely
        del file.content_type

        # Should not raise — MIME check is skipped
        validate_resume(file)
```

---

### 3.3 StatusUpdateEmailPayload — Pydantic Model

```python
# apps/notifications/tests/test_schemas.py
"""
Tests for Pydantic models that validate Celery task payloads.
Pure unit tests — no database, no Django ORM.
"""
import uuid

import pytest
from pydantic import ValidationError

from apps.notifications.schemas import (
    ApplicationEmailPayload,
    StatusUpdateEmailPayload,
    VALID_STATUSES,
)


class TestApplicationEmailPayload:

    def test_valid_uuid_passes(self):
        valid_id = str(uuid.uuid4())
        payload = ApplicationEmailPayload(application_id=valid_id)

        assert payload.application_id == valid_id

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ApplicationEmailPayload(application_id="not-a-valid-uuid-at-all!!!!!")

        errors = exc_info.value.errors()
        assert any("UUID" in str(e) or "length" in str(e) for e in errors)

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            ApplicationEmailPayload(application_id="")

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            ApplicationEmailPayload()

        errors = exc_info.value.errors()
        assert errors[0]["type"] == "missing"


class TestStatusUpdateEmailPayload:

    def test_valid_input_passes(self):
        payload = StatusUpdateEmailPayload(
            application_id=str(uuid.uuid4()),
            old_status="applied",
            new_status="reviewing",
        )

        assert payload.old_status == "applied"
        assert payload.new_status == "reviewing"

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationError):
            StatusUpdateEmailPayload(
                application_id="garbage",
                old_status="applied",
                new_status="reviewing",
            )

    @pytest.mark.parametrize(
        "old_status,new_status",
        [
            ("applied", "nonexistent_status"),
            ("fake", "reviewing"),
            ("", "reviewing"),
        ],
        ids=["invalid-new", "invalid-old", "empty-old"],
    )
    def test_invalid_status_raises(self, old_status, new_status):
        with pytest.raises(ValidationError, match="not a valid application status"):
            StatusUpdateEmailPayload(
                application_id=str(uuid.uuid4()),
                old_status=old_status,
                new_status=new_status,
            )

    @pytest.mark.parametrize("status", sorted(VALID_STATUSES))
    def test_all_valid_statuses_accepted(self, status):
        """Every status in VALID_STATUSES should be accepted for both fields."""
        payload = StatusUpdateEmailPayload(
            application_id=str(uuid.uuid4()),
            old_status=status,
            new_status=status,
        )

        assert payload.old_status == status

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError) as exc_info:
            StatusUpdateEmailPayload()

        error_fields = {e["loc"][0] for e in exc_info.value.errors()}
        assert error_fields == {"application_id", "old_status", "new_status"}
```

---

### 3.4 IsCompanyMember Permission Class

```python
# common/tests/test_permissions.py
"""
Tests for custom DRF permission classes.
These need the database to create User/Company/CompanyMember rows,
but do NOT use the HTTP layer — we call the permission class directly.
"""
import pytest
from unittest.mock import MagicMock

from common.permissions import IsCompanyMember, IsRecruiter, IsOwnerOrReadOnly
from tests.factories import (
    UserFactory,
    CompanyFactory,
    CompanyMemberFactory,
    JobFactory,
)


@pytest.mark.django_db
class TestIsCompanyMember:
    """
    IsCompanyMember.has_object_permission(request, view, obj)
    obj must have a .company attribute with a .members M2M.
    """

    def setup_method(self):
        self.permission = IsCompanyMember()
        self.view = MagicMock()

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_member_has_permission(self):
        """A user who is a member of the job's company is allowed."""
        recruiter = UserFactory(role="recruiter")
        company = CompanyFactory()
        CompanyMemberFactory(user=recruiter, company=company)
        job = JobFactory(company=company)

        request = self._make_request(recruiter)

        assert self.permission.has_object_permission(request, self.view, job) is True

    def test_non_member_denied(self):
        """A recruiter who is NOT a member of the job's company is denied."""
        outsider = UserFactory(role="recruiter")
        company = CompanyFactory()
        # outsider is not added to company
        job = JobFactory(company=company)

        request = self._make_request(outsider)

        assert self.permission.has_object_permission(request, self.view, job) is False

    def test_candidate_denied(self):
        """A candidate is never a company member — always denied."""
        candidate = UserFactory(role="candidate")
        company = CompanyFactory()
        job = JobFactory(company=company)

        request = self._make_request(candidate)

        assert self.permission.has_object_permission(request, self.view, job) is False

    def test_member_of_different_company_denied(self):
        """Membership in company A does not grant access to company B's jobs."""
        recruiter = UserFactory(role="recruiter")
        company_a = CompanyFactory()
        company_b = CompanyFactory()
        CompanyMemberFactory(user=recruiter, company=company_a)
        job = JobFactory(company=company_b)

        request = self._make_request(recruiter)

        assert self.permission.has_object_permission(request, self.view, job) is False


@pytest.mark.django_db
class TestIsRecruiter:

    def setup_method(self):
        self.permission = IsRecruiter()

    def _make_request(self, user):
        request = MagicMock()
        request.user = user
        return request

    def test_recruiter_allowed(self):
        recruiter = UserFactory(role="recruiter")
        request = self._make_request(recruiter)

        assert self.permission.has_permission(request, MagicMock()) is True

    def test_candidate_denied(self):
        candidate = UserFactory(role="candidate")
        request = self._make_request(candidate)

        assert self.permission.has_permission(request, MagicMock()) is False

    def test_anonymous_denied(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request(AnonymousUser())

        assert self.permission.has_permission(request, MagicMock()) is False


@pytest.mark.django_db
class TestIsOwnerOrReadOnly:

    def setup_method(self):
        self.permission = IsOwnerOrReadOnly()

    def _make_request(self, user, method="GET"):
        request = MagicMock()
        request.user = user
        request.method = method
        return request

    def test_get_request_always_allowed(self):
        user = UserFactory()
        other_user = UserFactory()
        request = self._make_request(user, method="GET")

        # obj is another user — GET should still pass
        assert self.permission.has_object_permission(request, MagicMock(), other_user) is True

    @pytest.mark.parametrize("method", ["HEAD", "OPTIONS"])
    def test_safe_methods_allowed(self, method):
        user = UserFactory()
        request = self._make_request(user, method=method)

        assert self.permission.has_object_permission(request, MagicMock(), UserFactory()) is True

    def test_owner_can_modify(self):
        user = UserFactory()
        request = self._make_request(user, method="PATCH")

        assert self.permission.has_object_permission(request, MagicMock(), user) is True

    def test_non_owner_cannot_modify(self):
        user = UserFactory()
        other_user = UserFactory()
        request = self._make_request(user, method="DELETE")

        assert self.permission.has_object_permission(request, MagicMock(), other_user) is False

    def test_applicant_can_modify_own_application(self):
        """IsOwnerOrReadOnly also checks getattr(obj, 'applicant', None)."""
        user = UserFactory(role="candidate")
        application = MagicMock()
        application.applicant = user
        request = self._make_request(user, method="DELETE")

        assert self.permission.has_object_permission(request, MagicMock(), application) is True
```

---

## 4. Integration Tests

Integration tests exercise the full request-response cycle through DRF's `APIClient`.
They hit a real PostgreSQL database, real serializer validation, real permission checks,
and real signals. The only things we mock are **external side effects** (Celery tasks,
SMTP) to keep tests fast and deterministic.

### 4.1 POST /api/applications/ — Full Application Flow

```python
# apps/applications/tests/test_views.py
"""
Integration tests for the applications API.
Tests the full lifecycle: auth → permission → validation → DB write → signal → response.
"""
import pytest
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.applications.models import Application
from apps.jobs.models import Job
from tests.factories import (
    UserFactory,
    CompanyFactory,
    CompanyMemberFactory,
    JobFactory,
    ApplicationFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def candidate(db):
    return UserFactory(role="candidate")


@pytest.fixture
def recruiter(db):
    return UserFactory(role="recruiter")


@pytest.fixture
def published_job(db):
    company = CompanyFactory()
    return JobFactory(status=Job.Status.PUBLISHED, company=company)


@pytest.fixture
def pdf_resume():
    return SimpleUploadedFile(
        name="resume.pdf",
        content=b"%PDF-1.4 fake resume content for testing",
        content_type="application/pdf",
    )


@pytest.mark.django_db
class TestCreateApplication:
    """POST /api/applications/"""

    URL = "/api/applications/"

    def test_candidate_can_apply_successfully(
        self, api_client, candidate, published_job, pdf_resume
    ):
        """
        Full happy path:
        1. Authenticated candidate sends valid data
        2. Application is created in DB with status="applied"
        3. Response is 201 with application data
        """
        api_client.force_authenticate(user=candidate)

        response = api_client.post(
            self.URL,
            data={
                "job": str(published_job.id),
                "resume": pdf_resume,
                "cover_letter": "I am excited to apply for this role.",
                "expected_salary": 150000,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "applied"
        assert Application.objects.filter(
            job=published_job, applicant=candidate
        ).exists()

    @patch("apps.notifications.tasks.send_application_received_email.delay")
    def test_signal_fires_celery_task_on_create(
        self, mock_email_task, api_client, candidate, published_job, pdf_resume
    ):
        """
        After a successful application, the post_save signal should call
        send_application_received_email.delay() with the application's UUID.
        """
        api_client.force_authenticate(user=candidate)

        response = api_client.post(
            self.URL,
            data={
                "job": str(published_job.id),
                "resume": pdf_resume,
            },
            format="multipart",
        )

        assert response.status_code == status.HTTP_201_CREATED
        mock_email_task.assert_called_once()
        # The argument should be the string UUID of the created application
        call_args = mock_email_task.call_args[0]
        assert call_args[0] == response.data["id"]

    def test_unauthenticated_user_gets_401(self, api_client, published_job, pdf_resume):
        response = api_client.post(
            self.URL,
            data={"job": str(published_job.id), "resume": pdf_resume},
            format="multipart",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_recruiter_cannot_apply(
        self, api_client, recruiter, published_job, pdf_resume
    ):
        """Only candidates can submit applications."""
        api_client.force_authenticate(user=recruiter)

        response = api_client.post(
            self.URL,
            data={"job": str(published_job.id), "resume": pdf_resume},
            format="multipart",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_application_rejected(
        self, api_client, candidate, published_job, pdf_resume
    ):
        """A candidate cannot apply to the same job twice."""
        ApplicationFactory(job=published_job, applicant=candidate)
        api_client.force_authenticate(user=candidate)

        response = api_client.post(
            self.URL,
            data={"job": str(published_job.id), "resume": pdf_resume},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_apply_to_draft_job(self, api_client, candidate, pdf_resume):
        draft_job = JobFactory(status=Job.Status.DRAFT)
        api_client.force_authenticate(user=candidate)

        response = api_client.post(
            self.URL,
            data={"job": str(draft_job.id), "resume": pdf_resume},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_apply_to_expired_job(self, api_client, candidate, pdf_resume):
        from datetime import timedelta
        from django.utils import timezone

        expired_job = JobFactory(
            status=Job.Status.PUBLISHED,
            deadline=timezone.now().date() - timedelta(days=1),
        )
        api_client.force_authenticate(user=candidate)

        response = api_client.post(
            self.URL,
            data={"job": str(expired_job.id), "resume": pdf_resume},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_resume_type_rejected(self, api_client, candidate, published_job):
        exe_file = SimpleUploadedFile(
            name="malware.exe",
            content=b"MZ\x90\x00",
            content_type="application/x-msdownload",
        )
        api_client.force_authenticate(user=candidate)

        response = api_client.post(
            self.URL,
            data={"job": str(published_job.id), "resume": exe_file},
            format="multipart",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUpdateApplicationStatus:
    """PATCH /api/applications/{id}/status/"""

    def _url(self, application_id):
        return f"/api/applications/{application_id}/status/"

    @pytest.fixture
    def company_with_recruiter(self):
        recruiter = UserFactory(role="recruiter")
        company = CompanyFactory()
        CompanyMemberFactory(user=recruiter, company=company, role="recruiter")
        return company, recruiter

    @pytest.fixture
    def application(self, company_with_recruiter):
        company, _ = company_with_recruiter
        job = JobFactory(status=Job.Status.PUBLISHED, company=company)
        return ApplicationFactory(job=job, status="applied")

    def test_valid_transition_applied_to_reviewing(
        self, api_client, company_with_recruiter, application
    ):
        _, recruiter = company_with_recruiter
        api_client.force_authenticate(user=recruiter)

        response = api_client.patch(
            self._url(application.id),
            data={"status": "reviewing"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "reviewing"
        application.refresh_from_db()
        assert application.status == "reviewing"

    def test_invalid_transition_applied_to_offered(
        self, api_client, company_with_recruiter, application
    ):
        """Cannot skip from 'applied' directly to 'offered'."""
        _, recruiter = company_with_recruiter
        api_client.force_authenticate(user=recruiter)

        response = api_client.patch(
            self._url(application.id),
            data={"status": "offered"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid_status_transition" in str(response.data)

    def test_non_member_recruiter_denied(self, api_client, application):
        """A recruiter from a different company cannot update the status."""
        outsider = UserFactory(role="recruiter")
        other_company = CompanyFactory()
        CompanyMemberFactory(user=outsider, company=other_company)
        api_client.force_authenticate(user=outsider)

        response = api_client.patch(
            self._url(application.id),
            data={"status": "reviewing"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_candidate_cannot_update_status(self, api_client, application, candidate):
        """Only recruiters (company members) can change application status."""
        api_client.force_authenticate(user=candidate)

        response = api_client.patch(
            self._url(application.id),
            data={"status": "reviewing"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.notifications.tasks.send_status_update_email.delay")
    def test_status_change_triggers_email_task(
        self, mock_email_task, api_client, company_with_recruiter, application
    ):
        _, recruiter = company_with_recruiter
        api_client.force_authenticate(user=recruiter)

        api_client.patch(
            self._url(application.id),
            data={"status": "reviewing"},
            format="json",
        )

        mock_email_task.assert_called_once_with(
            str(application.id), "applied", "reviewing"
        )


@pytest.mark.django_db
class TestJobSearch:
    """GET /api/jobs/search/?q=<query>"""

    URL = "/api/jobs/search/"

    @staticmethod
    def _create_and_index(**kwargs):
        from django.contrib.postgres.search import SearchVector

        job = JobFactory(status=Job.Status.PUBLISHED, **kwargs)
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
            title="Django Developer",
            description="Build REST APIs.",
        )
        self._create_and_index(
            title="React Developer",
            description="Build UIs with React.",
        )

        response = api_client.get(self.URL, {"q": "Django"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["title"] == "Django Developer"

    def test_results_ordered_by_rank(self, api_client):
        """Title matches (weight A) should appear before description matches (weight B)."""
        title_match = self._create_and_index(
            title="Django Developer",
            description="General backend work.",
        )
        desc_match = self._create_and_index(
            title="Backend Engineer",
            description="Experience with Django required.",
        )

        response = api_client.get(self.URL, {"q": "Django"})

        results = response.data["results"]
        assert len(results) == 2
        assert results[0]["id"] == str(title_match.id)
        assert results[1]["id"] == str(desc_match.id)

    def test_missing_q_param_returns_400(self, api_client):
        response = api_client.get(self.URL)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_results_returns_empty_list(self, api_client):
        self._create_and_index(
            title="Python Developer",
            description="Build CLI tools.",
        )

        response = api_client.get(self.URL, {"q": "Haskell"})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 0
```

---

## 5. Signal Tests

Signals are side effects triggered by model saves. The goal is to verify that the
correct Celery task is dispatched with the correct arguments — without running Celery
or sending real emails.

**Strategy:** Mock the `.delay()` method on the task function, then perform the action
that triggers the signal (saving a model instance), and assert the mock was called.

```python
# apps/applications/tests/test_signals.py
"""
Tests for application signals.
Mock Celery tasks at the point they are called (.delay()),
not at the signal level — this verifies the signal actually fires.
"""
import pytest
from unittest.mock import patch

from apps.applications.models import Application
from tests.factories import ApplicationFactory, JobFactory
from apps.jobs.models import Job


@pytest.mark.django_db
class TestOnApplicationCreated:
    """post_save signal: on_application_created"""

    @patch("apps.notifications.tasks.send_application_received_email.delay")
    def test_fires_on_new_application(self, mock_delay):
        """Creating a new Application should trigger the email task."""
        application = ApplicationFactory()

        mock_delay.assert_called_once_with(str(application.id))

    @patch("apps.notifications.tasks.send_application_received_email.delay")
    def test_does_not_fire_on_update(self, mock_delay):
        """Updating an existing application should NOT re-trigger the task."""
        application = ApplicationFactory()
        mock_delay.reset_mock()

        # Update the application (not a create)
        application.cover_letter = "Updated cover letter."
        application.save()

        mock_delay.assert_not_called()


@pytest.mark.django_db
class TestOnStatusChange:
    """pre_save signal: on_status_change"""

    @patch("apps.notifications.tasks.send_status_update_email.delay")
    def test_fires_when_status_changes(self, mock_delay):
        """Changing status from 'applied' to 'reviewing' should trigger email."""
        application = ApplicationFactory(status="applied")
        mock_delay.reset_mock()  # Clear the call from on_application_created

        application.status = "reviewing"
        application.save()

        mock_delay.assert_called_once_with(
            str(application.id), "applied", "reviewing"
        )

    @patch("apps.notifications.tasks.send_status_update_email.delay")
    def test_does_not_fire_when_status_unchanged(self, mock_delay):
        """Saving without changing status should NOT trigger the task."""
        application = ApplicationFactory(status="applied")
        mock_delay.reset_mock()

        application.cover_letter = "Updated text."
        application.save()

        mock_delay.assert_not_called()

    @patch("apps.notifications.tasks.send_status_update_email.delay")
    def test_does_not_fire_on_new_application(self, mock_delay):
        """
        The pre_save signal has an early return for new instances (no pk yet).
        on_application_created handles the initial notification instead.
        """
        # The factory creates a new instance — pre_save should detect instance.pk is None
        # and return early. Only post_save (on_application_created) should fire.
        ApplicationFactory(status="applied")

        # send_status_update_email should not be called (only send_application_received_email)
        mock_delay.assert_not_called()
```

---

## 6. Celery Task Tests

### Strategy: Synchronous Execution with `CELERY_TASK_ALWAYS_EAGER`

In tests, we don't want tasks to go through Redis. Setting `CELERY_TASK_ALWAYS_EAGER=True`
makes tasks execute synchronously in the same process, while still going through the
full task machinery (serialization, retry logic, etc.).

```python
# In conftest.py or pytest settings override
@pytest.fixture(autouse=True)
def celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
```

### Task Tests

```python
# apps/notifications/tests/test_tasks.py
"""
Tests for Celery tasks — email sending and retry behavior.
Tasks are executed synchronously via CELERY_TASK_ALWAYS_EAGER.
"""
import uuid
import smtplib

import pytest
from unittest.mock import patch, MagicMock
from celery.exceptions import Retry

from apps.notifications.tasks import (
    send_application_received_email,
    send_status_update_email,
)
from tests.factories import ApplicationFactory


@pytest.mark.django_db
class TestSendApplicationReceivedEmail:

    @patch("apps.notifications.tasks.send_mail")
    def test_sends_email_to_applicant(self, mock_send_mail):
        application = ApplicationFactory()

        send_application_received_email(str(application.id))

        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args
        # Verify recipient is the applicant's email
        assert application.applicant.email in call_kwargs[1]["recipient_list"] \
            or application.applicant.email in call_kwargs[0][3]

    @patch("apps.notifications.tasks.send_mail")
    def test_email_subject_contains_job_title(self, mock_send_mail):
        application = ApplicationFactory()

        send_application_received_email(str(application.id))

        call_args = mock_send_mail.call_args
        subject = call_args[1].get("subject") or call_args[0][0]
        assert application.job.title in subject

    @patch("apps.notifications.tasks.send_mail")
    def test_nonexistent_application_does_not_crash(self, mock_send_mail):
        """If the application was deleted between enqueue and execution, log and return."""
        fake_id = str(uuid.uuid4())

        # Should not raise — the task handles DoesNotExist gracefully
        send_application_received_email(fake_id)

        mock_send_mail.assert_not_called()

    def test_invalid_uuid_does_not_retry(self):
        """A malformed UUID should be logged and skipped, not retried."""
        # This should return without error — Pydantic validation catches it
        result = send_application_received_email("not-a-uuid")
        # No exception raised — task exits cleanly

    @patch("apps.notifications.tasks.send_mail")
    def test_retry_on_smtp_failure(self, mock_send_mail):
        """SMTP failure should trigger a retry (up to 3 times)."""
        mock_send_mail.side_effect = smtplib.SMTPException("Connection refused")
        application = ApplicationFactory()

        with pytest.raises(Retry):
            send_application_received_email(str(application.id))


@pytest.mark.django_db
class TestSendStatusUpdateEmail:

    @patch("apps.notifications.tasks.send_mail")
    def test_sends_email_with_status_change(self, mock_send_mail):
        application = ApplicationFactory(status="reviewing")

        send_status_update_email(
            str(application.id), "applied", "reviewing"
        )

        mock_send_mail.assert_called_once()
        call_args = mock_send_mail.call_args
        message = call_args[1].get("message") or call_args[0][1]
        assert "applied" in message
        assert "reviewing" in message

    @patch("apps.notifications.tasks.send_mail")
    def test_retry_on_smtp_failure(self, mock_send_mail):
        mock_send_mail.side_effect = smtplib.SMTPException("Timeout")
        application = ApplicationFactory(status="reviewing")

        with pytest.raises(Retry):
            send_status_update_email(
                str(application.id), "applied", "reviewing"
            )

    def test_invalid_status_does_not_retry(self):
        """Invalid status should be caught by Pydantic and not retried."""
        result = send_status_update_email(
            str(uuid.uuid4()), "applied", "nonexistent"
        )
        # Returns None — task exits cleanly without retry


@pytest.mark.django_db
class TestCloseExpiredJobs:

    def test_closes_expired_published_jobs(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.jobs.tasks import close_expired_jobs
        from apps.jobs.models import Job

        yesterday = timezone.now().date() - timedelta(days=1)
        expired_job = JobFactory(status=Job.Status.PUBLISHED, deadline=yesterday)
        active_job = JobFactory(
            status=Job.Status.PUBLISHED,
            deadline=timezone.now().date() + timedelta(days=30),
        )

        result = close_expired_jobs()

        expired_job.refresh_from_db()
        active_job.refresh_from_db()
        assert expired_job.status == Job.Status.CLOSED
        assert active_job.status == Job.Status.PUBLISHED
        assert "Closed 1 expired jobs" in result

    def test_does_not_close_drafts(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.jobs.tasks import close_expired_jobs
        from apps.jobs.models import Job

        yesterday = timezone.now().date() - timedelta(days=1)
        draft = JobFactory(status=Job.Status.DRAFT, deadline=yesterday)

        close_expired_jobs()

        draft.refresh_from_db()
        assert draft.status == Job.Status.DRAFT

    def test_idempotent_on_rerun(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.jobs.tasks import close_expired_jobs

        yesterday = timezone.now().date() - timedelta(days=1)
        JobFactory(status="published", deadline=yesterday)

        close_expired_jobs()
        result = close_expired_jobs()

        assert "Closed 0 expired jobs" in result
```

---

## 7. Factory Setup

All factories live in a single file for easy import across all test modules.

```python
# tests/factories.py
"""
factory_boy factories for all HireFlow models.
Produces realistic fake data using Faker.

Usage:
    from tests.factories import UserFactory, JobFactory
    user = UserFactory()                       # Default candidate
    recruiter = UserFactory(role="recruiter")   # Override any field
    jobs = JobFactory.create_batch(5)          # Batch creation
"""
import factory
from factory.django import DjangoModelFactory
from django.utils.text import slugify


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "accounts.User"
        django_get_or_create = ("email",)

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.LazyAttribute(
        lambda obj: f"{obj.first_name.lower()}.{obj.last_name.lower()}"
        f"@{factory.Faker('free_email_domain').evaluate(None, None, {'locale': None})}"
    )
    username = factory.LazyAttribute(
        lambda obj: f"{obj.first_name.lower()}_{obj.last_name.lower()}"
        f"_{factory.Faker('random_int', min=100, max=999).evaluate(None, None, {'locale': None})}"
    )
    role = "candidate"
    phone = factory.Faker("phone_number")
    is_email_verified = True
    is_active = True
    password = factory.PostGenerationMethodCall("set_password", "testpass123!")


class CompanyFactory(DjangoModelFactory):
    class Meta:
        model = "companies.Company"
        django_get_or_create = ("slug",)

    name = factory.Faker("company")
    slug = factory.LazyAttribute(lambda obj: slugify(obj.name))
    description = factory.Faker("catch_phrase")
    website = factory.Faker("url")
    size = factory.Iterator(["1-10", "11-50", "51-200", "201-500", "500+"])
    industry = factory.Faker(
        "random_element",
        elements=["Technology", "Finance", "Healthcare", "Education", "Retail"],
    )
    location = factory.Faker("city")
    is_verified = True


class CompanyMemberFactory(DjangoModelFactory):
    class Meta:
        model = "companies.CompanyMember"
        django_get_or_create = ("user", "company")

    user = factory.SubFactory(UserFactory, role="recruiter")
    company = factory.SubFactory(CompanyFactory)
    role = "recruiter"


class JobFactory(DjangoModelFactory):
    class Meta:
        model = "jobs.Job"
        django_get_or_create = ("slug",)

    company = factory.SubFactory(CompanyFactory)
    posted_by = factory.SubFactory(UserFactory, role="recruiter")
    title = factory.Faker(
        "random_element",
        elements=[
            "Senior Django Developer",
            "Backend Python Engineer",
            "Full Stack Developer",
            "DevOps Engineer",
            "Data Engineer",
            "ML Engineer",
            "Frontend React Developer",
            "iOS Developer",
        ],
    )
    slug = factory.LazyAttribute(
        lambda obj: slugify(f"{obj.title}-{factory.Faker('random_int', min=1000, max=9999).evaluate(None, None, {'locale': None})}")
    )
    description = factory.Faker("paragraph", nb_sentences=5)
    requirements = factory.Faker("paragraph", nb_sentences=3)
    responsibilities = factory.Faker("paragraph", nb_sentences=3)
    skills = factory.LazyFunction(
        lambda: ["Python", "Django", "PostgreSQL"]
    )
    job_type = factory.Iterator(["full_time", "part_time", "contract", "remote"])
    experience_level = factory.Iterator(["junior", "mid", "senior", "lead"])
    location = factory.Faker("city")
    is_remote = factory.Faker("boolean", chance_of_getting_true=40)
    salary_min = factory.Faker("random_int", min=50000, max=100000, step=5000)
    salary_max = factory.LazyAttribute(lambda obj: obj.salary_min + 50000)
    currency = "USD"
    status = "draft"
    deadline = factory.Faker("future_date", end_date="+90d")


class ApplicationFactory(DjangoModelFactory):
    class Meta:
        model = "applications.Application"

    job = factory.SubFactory(JobFactory, status="published")
    applicant = factory.SubFactory(UserFactory, role="candidate")
    resume = factory.django.FileField(
        filename="resume.pdf",
        data=b"%PDF-1.4 fake resume content",
    )
    cover_letter = factory.Faker("paragraph", nb_sentences=3)
    status = "applied"
    expected_salary = factory.Faker("random_int", min=80000, max=200000, step=5000)
    available_from = factory.Faker("future_date", end_date="+60d")


class NotificationFactory(DjangoModelFactory):
    class Meta:
        model = "notifications.Notification"

    user = factory.SubFactory(UserFactory)
    type = factory.Iterator([
        "application_received",
        "status_changed",
        "job_expiring",
    ])
    title = factory.Faker("sentence", nb_words=6)
    message = factory.Faker("paragraph", nb_sentences=2)
    is_read = False
    metadata = factory.LazyFunction(lambda: {})
```

---

## 8. Test Database and Fixtures

### 8.1 pytest Configuration

```ini
# pytest.ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.test
python_files = tests.py test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --strict-markers
    --tb=short
    --no-header
    -q
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
```

### 8.2 Test Settings

```python
# config/settings/test.py
"""
Test-specific settings.
Inherits from base, overrides for speed and isolation.
"""
from .base import *  # noqa: F401, F403

# ── Speed optimizations ──────────────────────────────────────
# Use MD5 instead of PBKDF2 for password hashing — 100x faster in tests
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use in-memory email backend — no SMTP calls
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Disable throttling in tests — don't want rate limits causing false failures
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

# ── Celery ────────────────────────────────────────────────────
# Execute tasks synchronously — no Redis required for tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ── Database ──────────────────────────────────────────────────
# Use the same PostgreSQL engine (required for FTS, GIN indexes, JSONField).
# pytest-django creates a test database automatically.
DATABASES["default"]["TEST"] = {  # noqa: F405
    "NAME": "test_hireflow",
}

# ── Media files ───────────────────────────────────────────────
# Store uploaded files in a temp directory during tests
import tempfile
MEDIA_ROOT = tempfile.mkdtemp()

# ── Caching ───────────────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── Logging ───────────────────────────────────────────────────
# Suppress noisy log output during test runs
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "CRITICAL"},
}
```

### 8.3 Root conftest.py — Shared Fixtures

```python
# tests/conftest.py
"""
Root conftest — fixtures available to ALL test modules.
pytest discovers conftest.py files automatically by directory hierarchy.
"""
import pytest
from rest_framework.test import APIClient
from django.contrib.postgres.search import SearchVector

from tests.factories import (
    UserFactory,
    CompanyFactory,
    CompanyMemberFactory,
    JobFactory,
    ApplicationFactory,
)
from apps.jobs.models import Job


# ─── API Client ───────────────────────────────────────────────

@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def candidate_client(db):
    """APIClient pre-authenticated as a candidate user."""
    user = UserFactory(role="candidate")
    client = APIClient()
    client.force_authenticate(user=user)
    client.user = user  # Attach for assertions
    return client


@pytest.fixture
def recruiter_client(db):
    """APIClient pre-authenticated as a recruiter who owns a company."""
    user = UserFactory(role="recruiter")
    company = CompanyFactory()
    CompanyMemberFactory(user=user, company=company, role="owner")
    client = APIClient()
    client.force_authenticate(user=user)
    client.user = user
    client.company = company
    return client


# ─── Common Model Fixtures ────────────────────────────────────

@pytest.fixture
def candidate(db):
    return UserFactory(role="candidate")


@pytest.fixture
def recruiter(db):
    return UserFactory(role="recruiter")


@pytest.fixture
def company(db):
    return CompanyFactory()


@pytest.fixture
def published_job(db):
    """A published job with search_vector populated."""
    job = JobFactory(status=Job.Status.PUBLISHED)
    Job.objects.filter(pk=job.pk).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
        )
    )
    job.refresh_from_db()
    return job


# ─── Search Vector Helper ─────────────────────────────────────

@pytest.fixture
def index_search_vector():
    """
    Fixture that returns a callable to populate search_vector for a job.

    Usage in tests:
        def test_something(index_search_vector):
            job = JobFactory(status="published", title="Django Developer")
            index_search_vector(job)
            results = Job.objects.search("Django")
    """
    def _index(job):
        Job.objects.filter(pk=job.pk).update(
            search_vector=(
                SearchVector("title", weight="A")
                + SearchVector("description", weight="B")
            )
        )
        job.refresh_from_db()
        return job

    return _index


# ─── Celery ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def celery_eager(settings):
    """Force all Celery tasks to run synchronously in every test."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
```

### 8.4 Handling search_vector in Test Data

PostgreSQL's `SearchVectorField` is not populated automatically by Django when you
create a model instance via the ORM — it requires either:

1. The `post_save` signal in `apps/jobs/signals.py` (which calls `.update()` with
   `SearchVector`)
2. A raw SQL trigger

In tests, the signal may or may not fire depending on how the object is created. To
ensure consistency:

**Option A: Use the `index_search_vector` fixture (recommended)**

```python
def test_search_returns_results(index_search_vector):
    job = JobFactory(status="published", title="Django Developer")
    index_search_vector(job)

    results = Job.objects.search("Django")
    assert job in results
```

**Option B: Let the signal fire naturally**

If `apps.jobs.signals` is registered in `JobsConfig.ready()`, the signal fires on
`JobFactory()` automatically. But the `search_vector` update uses `.update()` (which
doesn't refresh the in-memory instance), so always call `job.refresh_from_db()`.

**Option C: `@pytest.fixture(autouse=True)` for bulk indexing**

```python
@pytest.fixture(autouse=True)
def _reindex_all_jobs():
    yield
    # After each test, the DB is rolled back — no cleanup needed
```

We recommend **Option A** for explicit control in search-related tests, and letting the
signal handle it naturally in integration tests that don't assert on search results.

---

## 9. Coverage Targets

### Target Percentages

| Layer | Target | Rationale |
|-------|--------|-----------|
| **Overall project** | **90%** | Industry standard for a well-tested API |
| Custom managers | 100% | These contain critical business logic (which jobs are visible) |
| Validators | 100% | Security boundary — resume validation must be airtight |
| Permission classes | 100% | Access control bugs are security vulnerabilities |
| Pydantic schemas | 100% | Input validation for async tasks |
| Celery tasks | 95% | Including retry paths and error handling |
| Views / API endpoints | 85% | Cover happy path + major error paths per endpoint |
| Serializers | 85% | Custom validation logic, not auto-generated field declarations |
| Models | 70% | Properties and `__str__` methods; skip auto-generated fields |
| Signals | 100% | These trigger side effects — must be tested |

### What NOT to Cover

- **Django auto-generated code**: Migrations, admin.py boilerplate, `AppConfig` classes
  without custom `ready()` logic.
- **Third-party integrations**: `drf-spectacular` schema generation, `django-filter`
  internals, SimpleJWT token encoding.
- **Configuration files**: `settings/*.py`, `celery.py`, `wsgi.py`, `urls.py`
  (routing is tested implicitly by integration tests).
- **`__init__.py` files**: Empty or import-only.

### Running Coverage Reports

```bash
# Install
pip install pytest-cov

# Run tests with coverage
pytest --cov=apps --cov=common --cov-report=term-missing --cov-report=html

# Terminal output shows missing lines:
# Name                                    Stmts   Miss  Cover   Missing
# ---------------------------------------------------------------------
# apps/jobs/managers.py                      28      0   100%
# apps/notifications/tasks.py                42      2    95%   38, 64
# common/validators.py                       18      0   100%

# HTML report: open htmlcov/index.html in browser
```

### Coverage Configuration

```ini
# setup.cfg
[tool:pytest]
addopts = --cov=apps --cov=common --cov-config=setup.cfg

[coverage:run]
source = apps, common
omit =
    */migrations/*
    */tests/*
    */admin.py
    manage.py
    config/*

[coverage:report]
fail_under = 90
show_missing = true
exclude_lines =
    pragma: no cover
    def __repr__
    if TYPE_CHECKING:
    raise NotImplementedError
```

---

## 10. CI Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

env:
  DJANGO_SETTINGS_MODULE: config.settings.test
  SECRET_KEY: "test-secret-key-that-is-at-least-fifty-characters-long-for-validation"
  DATABASE_URL: "postgres://postgres:postgres@localhost:5432/test_hireflow"
  REDIS_URL: "redis://localhost:6379/0"
  CELERY_BROKER_URL: "redis://localhost:6379/0"

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_hireflow
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd="pg_isready -U postgres"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd="redis-cli ping"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/base.txt
          pip install -r requirements/development.txt
          pip install pytest pytest-django pytest-cov factory-boy

      - name: Run migrations
        run: python manage.py migrate --verbosity=0

      - name: Run tests with coverage
        run: |
          pytest \
            --cov=apps \
            --cov=common \
            --cov-report=term-missing \
            --cov-report=xml:coverage.xml \
            --cov-fail-under=90 \
            --tb=short \
            -q

      - name: Upload coverage to Codecov
        if: always()
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          fail_ci_if_error: false
          token: ${{ secrets.CODECOV_TOKEN }}

      - name: Comment coverage on PR
        if: github.event_name == 'pull_request'
        uses: orgoro/coverage@v3.2
        with:
          coverageFile: coverage.xml
          token: ${{ secrets.GITHUB_TOKEN }}
          thresholdAll: 0.90
          thresholdNew: 0.95
```

### What the CI Pipeline Enforces

| Check | Threshold | Behavior on Failure |
|-------|-----------|---------------------|
| All tests pass | 0 failures | **Blocks merge** — red status check |
| Overall coverage | ≥ 90% | **Blocks merge** — `--cov-fail-under=90` exits non-zero |
| New code coverage | ≥ 95% | **PR comment warning** — via `orgoro/coverage` action |
| PostgreSQL available | Service healthy | Tests won't run without it (FTS requires real PostgreSQL) |
| Redis available | Service healthy | Required if any test touches cache; optional with eager Celery |

### Running Tests Locally (Quick Reference)

```bash
# All tests
pytest

# Specific app
pytest apps/jobs/tests/

# Specific test class
pytest apps/jobs/tests/test_managers.py::TestJobManagerSearch

# Specific test
pytest apps/jobs/tests/test_managers.py::TestJobManagerSearch::test_search_matches_title

# With coverage
pytest --cov=apps --cov=common --cov-report=html

# Skip slow tests
pytest -m "not slow"

# Verbose output (see each test name)
pytest -v

# Stop on first failure
pytest -x

# Run last-failed tests only
pytest --lf

# Parallel execution (install pytest-xdist)
pytest -n auto
```

---

## Appendix: Test Dependencies

Add these to `requirements/development.txt`:

```
pytest==8.1
pytest-django==4.8
pytest-cov==5.0
factory-boy==3.3
pytest-xdist==3.5          # Parallel test execution (optional)
```
