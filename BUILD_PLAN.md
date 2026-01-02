# HireFlow — Phase-by-Phase TDD Build Plan

> Multi-Tenant Job Board API · Django 5.0 + DRF + Celery + Redis + PostgreSQL + Docker
>
> Approach: Strict TDD (RED → GREEN → REFACTOR) · Each phase fully tested before advancing
>
> Source of truth: ARCHITECTURE.md, TESTING.md, CONTRIBUTING.md, DEPLOYMENT.md
>
> Last updated: 2026-03-21

---

## Table of Contents

1. [Context](#context)
2. [Phase Dependency Graph](#phase-dependency-graph)
3. [Phase 1: Project Skeleton, Docker, Settings, and Base Model](#phase-1-project-skeleton-docker-settings-and-base-model)
4. [Phase 2: User Model, Registration, Login, and Email Verification](#phase-2-user-model-registration-login-and-email-verification)
5. [Phase 3: Custom Permissions](#phase-3-custom-permissions)
6. [Phase 4: Company & CompanyMember CRUD](#phase-4-company--companymember-crud)
7. [Phase 5: Job Model, CRUD, Full-Text Search, and Custom Manager](#phase-5-job-model-crud-full-text-search-and-custom-manager)
8. [Phase 6: Application Model, CRUD, Status Workflow, and Signals](#phase-6-application-model-crud-status-workflow-and-signals)
9. [Phase 7: Notification Model, Celery Tasks, and Pydantic Schemas](#phase-7-notification-model-celery-tasks-and-pydantic-schemas)
10. [Phase 8: Dashboard Aggregation Endpoints](#phase-8-dashboard-aggregation-endpoints)
11. [Phase 9: OpenAPI Documentation & Swagger UI](#phase-9-openapi-documentation--swagger-ui)
12. [Phase 10: Production Hardening, Seed Data, and Final Integration](#phase-10-production-hardening-seed-data-and-final-integration)
13. [Summary Table](#summary-table)
14. [Key Design Decisions](#key-design-decisions)

---

## Context

HireFlow exists only as documentation (ARCHITECTURE.md, TESTING.md, CONTRIBUTING.md, DEPLOYMENT.md). Zero application code exists. This plan takes a mid-senior Django developer from an empty directory to a fully tested, production-ready multi-tenant job board API in 10 sequential phases.

Each phase produces a working, tested increment — no phase leaves broken tests.

**TDD discipline for every phase:**

```
1. RED    — Write the test first. Run it. Watch it fail.
2. GREEN  — Write the minimum code to make the test pass.
3. REFACTOR — Clean up. Run tests again to confirm nothing broke.
```

**Reference documents:**
- `ARCHITECTURE.md` — Models, API contracts, Celery tasks, Pydantic schemas, security, ADRs
- `TESTING.md` — Test code examples, factories, fixtures, coverage targets, CI pipeline
- `CONTRIBUTING.md` — Docker setup, env config, linting, git workflow, seed data
- `DEPLOYMENT.md` — Production Docker Compose, Nginx, logging, health checks, monitoring

---

## Phase Dependency Graph

```
Phase 1  (Project Skeleton, Docker, Settings, Base Model)
   │
   ▼
Phase 2  (User Model, Registration, Login, Email Verification)
   │
   ▼
Phase 3  (Custom Permissions)
   │
   ▼
Phase 4  (Company & CompanyMember CRUD)
   │
   ▼
Phase 5  (Job Model, CRUD, Full-Text Search, Custom Manager)
   │
   ▼
Phase 6  (Application Model, CRUD, Status Workflow, Signals)
   │
   ▼
Phase 7  (Notification Model, Celery Tasks, Pydantic Schemas)
   │
   ▼
Phase 8  (Dashboard Aggregation Endpoints)
   │
   ▼
Phase 9  (OpenAPI Documentation & Swagger UI)
   │
   ▼
Phase 10 (Production Hardening, Seed Data, Final Integration)
```

---

## Phase 1: Project Skeleton, Docker, Settings, and Base Model

**Goal:** A Django project that boots inside Docker, connects to PostgreSQL and Redis, passes a smoke test, and defines the `TimeStampedModel` abstract base.

**Dependencies:** None (root phase).

### 1.1 Files to Create

```
hireflow/
├── manage.py
├── config/
│   ├── __init__.py
│   ├── env.py                    # HireFlowSettings (pydantic-settings)
│   ├── celery.py                 # Celery app init
│   ├── wsgi.py
│   ├── urls.py                   # Root URLs (just /api/health/ for now)
│   └── settings/
│       ├── __init__.py
│       ├── base.py               # Core settings using config.env
│       ├── development.py        # DEBUG=True, console email
│       ├── test.py               # MD5 hasher, eager Celery, locmem cache
│       └── production.py         # Placeholder
├── common/
│   ├── __init__.py
│   ├── models.py                 # TimeStampedModel (abstract: UUID PK + timestamps)
│   ├── validators.py             # validate_resume
│   ├── permissions.py            # Stub file (empty classes)
│   ├── exceptions.py             # Custom exception handler
│   ├── pagination.py             # HireFlowCursorPagination
│   └── tests/
│       ├── __init__.py
│       ├── test_models.py
│       ├── test_validators.py
│       ├── test_pagination.py
│       └── test_exceptions.py
├── apps/
│   ├── __init__.py
│   └── health/
│       ├── __init__.py
│       ├── views.py              # Health check (DB + Redis ping)
│       ├── urls.py
│       └── tests/
│           ├── __init__.py
│           └── test_views.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Root conftest with api_client fixture
│   └── factories.py              # Empty, populated incrementally
├── requirements/
│   ├── base.txt                  # All pinned core deps
│   ├── development.txt           # pytest, factory-boy, ruff, etc.
│   └── production.txt            # gunicorn, sentry-sdk, etc.
├── docker-compose.yml            # Dev stack: web, db, redis, celery, beat
├── Dockerfile                    # Dev Dockerfile
├── .env.example
├── pyproject.toml                # Ruff config
├── setup.cfg                     # pytest + coverage config
└── .gitignore
```

### 1.2 RED Phase — Tests to Write First

**`common/tests/test_models.py`** (4 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `TestTimeStampedModel::test_model_is_abstract` | Cannot instantiate directly |
| 2 | `TestTimeStampedModel::test_uuid_pk_is_generated` | Auto-generated UUID4 PK |
| 3 | `TestTimeStampedModel::test_created_at_is_auto_set` | auto_now_add works |
| 4 | `TestTimeStampedModel::test_updated_at_changes_on_save` | auto_now works |

**`common/tests/test_validators.py`** (6 tests — per TESTING.md Section 3):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `TestValidateResume::test_valid_file_passes` | PDF, DOC, DOCX under 5MB accepted (parametrized) |
| 2 | `TestValidateResume::test_wrong_extension_raises` | EXE, PY, JPG, TXT, ZIP rejected (parametrized) |
| 3 | `TestValidateResume::test_file_too_large_raises` | >5MB rejected |
| 4 | `TestValidateResume::test_file_exactly_at_limit_passes` | 5MB boundary passes |
| 5 | `TestValidateResume::test_wrong_mime_type_raises` | MIME mismatch rejected |
| 6 | `TestValidateResume::test_missing_content_type_does_not_crash` | Graceful handling |

**`common/tests/test_pagination.py`** (3 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_default_page_size_is_20` | Pagination defaults correct |
| 2 | `test_max_page_size_is_100` | Upper bound enforced |
| 3 | `test_default_ordering_is_minus_created_at` | Newest first |

**`common/tests/test_exceptions.py`** (3 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_error_format_has_error_code_details_keys` | Standard envelope format |
| 2 | `test_validation_error_formats_details` | DRF validation errors formatted |
| 3 | `test_404_error_format` | Not found follows envelope |

**`apps/health/tests/test_views.py`** (3 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `TestHealthCheck::test_health_check_returns_200` | Endpoint exists and works |
| 2 | `TestHealthCheck::test_contains_database_status` | DB check included |
| 3 | `TestHealthCheck::test_contains_redis_status` | Redis check included |

**Total: 19 tests**

### 1.3 GREEN Phase — Implement

| Step | File | Reference |
|------|------|-----------|
| 1 | `requirements/base.txt` | Pin: Django==5.0, DRF==3.15, SimpleJWT==5.3, psycopg2-binary, django-redis, celery==5.3, django-celery-beat, django-celery-results, pydantic-settings, django-cors-headers, drf-spectacular, django-filter, python-json-logger |
| 2 | `requirements/development.txt` | `-r base.txt` + pytest, pytest-django, pytest-cov, factory-boy, ruff |
| 3 | `Dockerfile` + `docker-compose.yml` | CONTRIBUTING.md Section 3.4-3.5 |
| 4 | `.env.example` | CONTRIBUTING.md Section 3.2 |
| 5 | `config/env.py` | `HireFlowSettings` — ARCHITECTURE.md Section 5.1 |
| 6 | Settings split: base/dev/test/prod | CONTRIBUTING.md Section 4 |
| 7 | `common/models.py` | `TimeStampedModel` — abstract, UUID PK, created_at, updated_at |
| 8 | `common/validators.py` | `validate_resume` — ARCHITECTURE.md Section 6 |
| 9 | `common/pagination.py` | `HireFlowCursorPagination` — page_size=20, max=100 |
| 10 | `common/exceptions.py` | Custom handler returning `{error, code, details}` |
| 11 | `apps/health/views.py` | DB + Redis health check — DEPLOYMENT.md Section 6 |
| 12 | `config/celery.py` | Celery app init — ARCHITECTURE.md Section 4.3 |
| 13 | `pyproject.toml` | Ruff config — CONTRIBUTING.md Section 9.2 |
| 14 | `setup.cfg` | pytest + coverage config — TESTING.md Section 9 |

### 1.4 Verification

```bash
docker compose up -d                                    # All 5 services running
docker compose exec web pytest                          # All 19 tests pass
docker compose exec web ruff check .                    # No lint errors
curl http://localhost:8000/api/health/                   # {"status": "healthy", ...}
docker compose exec web pytest --cov=common --cov=apps  # 100% on validators, pagination
```

---

## Phase 2: User Model, Registration, Login, and Email Verification

**Goal:** Custom User model (email as USERNAME_FIELD), JWT auth endpoints, email verification via TimestampSigner.

**Dependencies:** Phase 1 (project skeleton, base model, settings).

### 2.1 Files to Create

```
apps/accounts/
├── __init__.py
├── apps.py                 # AccountsConfig with ready() for signal import
├── models.py               # User (AbstractUser + TimeStampedModel)
├── serializers.py          # RegisterSerializer, LoginSerializer, UserSerializer
├── views.py                # RegisterView, LoginView, TokenRefreshView, VerifyEmailView
├── urls.py                 # /api/auth/ routes
├── tokens.py               # make_email_verification_token, verify_email_token
├── signals.py              # send_verification_email_on_register
├── admin.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_views.py
    └── test_tokens.py
```

**Also update:** `tests/factories.py` (add UserFactory), `tests/conftest.py` (add candidate/recruiter fixtures), `config/settings/base.py` (AUTH_USER_MODEL)

### 2.2 RED Phase — Tests to Write First

**`apps/accounts/tests/test_models.py`** (7 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_create_user_with_email` | User creation works |
| 2 | `test_email_is_username_field` | EMAIL_FIELD config correct |
| 3 | `test_default_role_is_candidate` | Default role is "candidate" |
| 4 | `test_uuid_primary_key` | UUID PK inherited from TimeStampedModel |
| 5 | `test_is_email_verified_default_false` | New users start unverified |
| 6 | `test_str_returns_email` | String representation is email |
| 7 | `test_role_choices` | candidate, recruiter, admin are valid |

**`apps/accounts/tests/test_tokens.py`** (4 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_make_token_returns_string` | Token generation works |
| 2 | `test_verify_valid_token_returns_user_id` | Round-trip verification |
| 3 | `test_verify_expired_token_raises` | 24h TTL enforced |
| 4 | `test_verify_tampered_token_raises` | HMAC integrity check |

**`apps/accounts/tests/test_views.py`** (14 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `TestRegisterView::test_register_returns_201` | Happy path |
| 2 | `TestRegisterView::test_creates_user_in_db` | DB write confirmed |
| 3 | `TestRegisterView::test_duplicate_email_returns_400` | Unique email enforced |
| 4 | `TestRegisterView::test_password_mismatch_returns_400` | Confirm password works |
| 5 | `TestRegisterView::test_weak_password_returns_400` | Django validators run |
| 6 | `TestRegisterView::test_default_role_is_candidate` | Role default correct |
| 7 | `TestRegisterView::test_register_as_recruiter` | Role selection works |
| 8 | `TestRegisterView::test_response_does_not_contain_password` | Password never exposed |
| 9 | `TestLoginView::test_returns_access_and_refresh_tokens` | JWT issuance |
| 10 | `TestLoginView::test_returns_user_data` | User info in response |
| 11 | `TestLoginView::test_wrong_password_returns_401` | Auth failure |
| 12 | `TestLoginView::test_nonexistent_email_returns_401` | Auth failure |
| 13 | `TestTokenRefreshView::test_refresh_returns_new_access_token` | Token rotation |
| 14 | `TestVerifyEmailView::test_valid_token_sets_is_email_verified` | Verification flow |

**Total: 25 tests**

### 2.3 GREEN Phase — Implement

| Step | File | Reference |
|------|------|-----------|
| 1 | `apps/accounts/models.py` | User model — ARCHITECTURE.md Section 2.2 |
| 2 | `config/settings/base.py` | Set `AUTH_USER_MODEL = "accounts.User"` |
| 3 | Migrations | `python manage.py makemigrations accounts` |
| 4 | `apps/accounts/tokens.py` | TimestampSigner, 24h TTL — ARCHITECTURE.md Section 3.2 |
| 5 | `apps/accounts/serializers.py` | RegisterSerializer (password_confirm, Django validators), LoginSerializer (email-based), UserSerializer |
| 6 | `apps/accounts/views.py` | RegisterView, LoginView, VerifyEmailView |
| 7 | `apps/accounts/signals.py` | `send_verification_email_on_register` — ARCHITECTURE.md |
| 8 | `apps/accounts/apps.py` | Register signals in `ready()` |
| 9 | `apps/accounts/urls.py` | Wire at `/api/auth/` |
| 10 | `tests/factories.py` | Add `UserFactory` — TESTING.md Section 7 |
| 11 | `tests/conftest.py` | Add candidate, recruiter, candidate_client, recruiter_client fixtures |

### 2.4 Verification

```bash
docker compose exec web pytest apps/accounts/ -v     # All 25 tests pass
# Manual verification:
# POST /api/auth/register/ → 201 with user data (no password)
# POST /api/auth/login/ → {access, refresh, user}
# POST /api/auth/verify-email/ → flips is_email_verified
```

---

## Phase 3: Custom Permissions

**Goal:** Implement and fully test all four permission classes that gate every authenticated endpoint.

**Dependencies:** Phase 2 (User model + UserFactory).

### 3.1 Files to Modify

```
common/permissions.py             # Full implementation of all 4 classes
common/tests/test_permissions.py  # Full test suite
```

> **Note:** Company/CompanyMember models don't exist yet. `IsCompanyMember` and `IsOwnerOrReadOnly` tests use `unittest.mock.MagicMock` to simulate model instances. These tests are re-validated with real DB objects in Phase 4.

### 3.2 RED Phase — Tests to Write First

Per TESTING.md Section 3.4:

**`common/tests/test_permissions.py`** (13 tests):

| # | Test | Strategy |
|---|------|----------|
| 1 | `TestIsRecruiter::test_recruiter_allowed` | Real User with role="recruiter" |
| 2 | `TestIsRecruiter::test_candidate_denied` | Real User with role="candidate" |
| 3 | `TestIsRecruiter::test_anonymous_denied` | AnonymousUser |
| 4 | `TestIsCandidate::test_candidate_allowed` | Real User with role="candidate" |
| 5 | `TestIsCandidate::test_recruiter_denied` | Real User with role="recruiter" |
| 6 | `TestIsCandidate::test_anonymous_denied` | AnonymousUser |
| 7 | `TestIsCompanyMember::test_member_has_permission` | MagicMock company with member queryset |
| 8 | `TestIsCompanyMember::test_non_member_denied` | MagicMock company, user not in members |
| 9 | `TestIsCompanyMember::test_candidate_denied` | MagicMock, candidate role |
| 10 | `TestIsCompanyMember::test_different_company_denied` | MagicMock, wrong company |
| 11 | `TestIsOwnerOrReadOnly::test_get_always_allowed` | Safe method |
| 12 | `TestIsOwnerOrReadOnly::test_owner_can_modify` | obj.applicant == request.user |
| 13 | `TestIsOwnerOrReadOnly::test_non_owner_cannot_modify` | obj.applicant != request.user |

**Total: 13 tests**

### 3.3 GREEN Phase — Implement

| Permission | Logic |
|------------|-------|
| `IsRecruiter` | `request.user.is_authenticated and request.user.role == "recruiter"` |
| `IsCandidate` | `request.user.is_authenticated and request.user.role == "candidate"` |
| `IsCompanyMember` | `has_object_permission`: resolve company from obj, check `company.members.filter(user=request.user).exists()` |
| `IsOwnerOrReadOnly` | Safe methods pass; write methods check `obj.applicant == request.user` |

### 3.4 Verification

```bash
docker compose exec web pytest common/tests/test_permissions.py -v  # All 13 pass
docker compose exec web pytest --cov=common/permissions.py          # 100% coverage
```

---

## Phase 4: Company & CompanyMember CRUD

**Goal:** Company and CompanyMember models, CRUD endpoints, member invitation, and multi-tenancy through model.

**Dependencies:** Phase 2 (User model), Phase 3 (IsRecruiter, IsCompanyMember).

### 4.1 Files to Create

```
apps/companies/
├── __init__.py
├── apps.py
├── models.py               # Company, CompanyMember
├── serializers.py          # CompanySerializer, CompanyCreateSerializer, InviteMemberSerializer
├── views.py                # CompanyViewSet, InviteMemberView
├── urls.py
├── admin.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    └── test_views.py
```

**Also update:** `tests/factories.py` (CompanyFactory, CompanyMemberFactory), `tests/conftest.py` (company fixture, update recruiter_client with company)

### 4.2 RED Phase — Tests to Write First

**`apps/companies/tests/test_models.py`** (7 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_create_company` | Company creation works |
| 2 | `test_slug_is_unique` | IntegrityError on duplicate slug |
| 3 | `test_str_returns_name` | String representation |
| 4 | `test_is_verified_defaults_to_false` | New companies unverified |
| 5 | `test_create_member` | CompanyMember creation |
| 6 | `test_unique_together_user_company` | One membership per user per company |
| 7 | `test_default_role_is_recruiter` | Member role default |

**`apps/companies/tests/test_views.py`** (13 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `TestListCompanies::test_returns_only_verified` | Public listing filters |
| 2 | `TestListCompanies::test_publicly_accessible` | No auth required |
| 3 | `TestListCompanies::test_pagination` | Cursor-based pagination works |
| 4 | `TestCreateCompany::test_recruiter_can_create` | Happy path, 201 |
| 5 | `TestCreateCompany::test_creator_becomes_owner` | Auto CompanyMember(role=owner) |
| 6 | `TestCreateCompany::test_candidate_cannot_create` | 403 |
| 7 | `TestCreateCompany::test_unauthenticated_401` | 401 |
| 8 | `TestCreateCompany::test_duplicate_slug_400` | Unique constraint |
| 9 | `TestCompanyDetail::test_retrieve_by_slug` | Slug lookup |
| 10 | `TestUpdateCompany::test_owner_can_update` | Owner permission |
| 11 | `TestUpdateCompany::test_non_owner_member_denied` | Recruiter member ≠ owner |
| 12 | `TestInviteMember::test_owner_can_invite` | Happy path |
| 13 | `TestInviteMember::test_already_member_400` | Duplicate prevention |

**Total: 20 tests**

### 4.3 GREEN Phase — Implement

| Step | File | Reference |
|------|------|-----------|
| 1 | `apps/companies/models.py` | Company + CompanyMember — ARCHITECTURE.md Section 2.2 |
| 2 | Migration | `unique_together = ("user", "company")` on CompanyMember |
| 3 | `apps/companies/serializers.py` | `CompanyCreateSerializer.create()` wraps in `transaction.atomic` — creates Company then CompanyMember(role="owner") |
| 4 | `apps/companies/views.py` | `CompanyViewSet` with `lookup_field="slug"` |
| 5 | `InviteMemberView` | Nested route at `/api/companies/{slug}/members/` |
| 6 | `tests/factories.py` | CompanyFactory + CompanyMemberFactory — TESTING.md Section 7 |
| 7 | **Re-run Phase 3 tests** | Replace MagicMock permission tests with real DB objects |

### 4.4 Verification

```bash
docker compose exec web pytest apps/companies/ -v                  # All 20 pass
docker compose exec web pytest common/tests/test_permissions.py    # Still pass with real objects
```

---

## Phase 5: Job Model, CRUD, Full-Text Search, and Custom Manager

**Goal:** Job model with SearchVectorField + GIN index, custom manager (published/search/with_application_count), CRUD + publish/close actions, FTS search endpoint, filters, close_expired_jobs periodic task.

**Dependencies:** Phase 4 (Company FK), Phase 2 (User FK for posted_by).

### 5.1 Files to Create

```
apps/jobs/
├── __init__.py
├── apps.py                 # JobsConfig with ready() for signal import
├── models.py               # Job with SearchVectorField, GIN index, composite indexes
├── managers.py             # JobManager: published(), search(), with_application_count()
├── serializers.py          # JobListSerializer, JobDetailSerializer, JobCreateSerializer
├── views.py                # JobViewSet (list, create, retrieve, update, destroy, publish, close, search)
├── signals.py              # update_search_vector (post_save)
├── filters.py              # JobFilter (django-filter)
├── tasks.py                # close_expired_jobs
├── urls.py
├── admin.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_managers.py
    ├── test_views.py
    ├── test_filters.py
    └── test_tasks.py
```

**Also update:** `tests/factories.py` (JobFactory), `tests/conftest.py` (published_job, index_search_vector)

### 5.2 RED Phase — Tests to Write First

**`apps/jobs/tests/test_models.py`** (9 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_create_job` | Job creation works |
| 2 | `test_slug_is_unique` | Unique slug constraint |
| 3 | `test_default_status_is_draft` | Correct default |
| 4 | `test_str_returns_title` | String representation |
| 5 | `test_skills_default_empty_list` | JSONB default |
| 6 | `test_views_count_default_zero` | Counter starts at 0 |
| 7 | `test_status_choices` | draft, published, closed |
| 8 | `test_posted_by_set_null_on_delete` | SET_NULL FK behavior |
| 9 | `test_company_cascade_on_delete` | CASCADE FK behavior |

**`apps/jobs/tests/test_managers.py`** (13 tests — per TESTING.md Section 3.1-3.3):

| # | Test Class | Test | What It Proves |
|---|------------|------|----------------|
| 1 | `TestJobManagerPublished` | `test_returns_published_jobs` | Base filter works |
| 2 | | `test_excludes_past_deadline` | Expired jobs hidden |
| 3 | | `test_includes_future_deadline` | Active jobs shown |
| 4 | | `test_includes_no_deadline` | Null deadline = never expires |
| 5 | | `test_includes_today_as_deadline` | Inclusive boundary |
| 6 | `TestJobManagerSearch` | `test_search_matches_title` | FTS on title |
| 7 | | `test_search_matches_description` | FTS on description |
| 8 | | `test_title_ranks_higher` | Weight A > Weight B |
| 9 | | `test_search_excludes_drafts` | Only published searchable |
| 10 | | `test_empty_for_no_match` | Graceful empty result |
| 11 | `TestJobManagerWithApplicationCount` | `test_annotates_count` | Count annotation works |
| 12 | | `test_zero_applications` | Zero count for no apps |
| 13 | | `test_excludes_drafts` | Only published annotated |

**`apps/jobs/tests/test_views.py`** (15 tests):

| # | Test Class | Test |
|---|------------|------|
| 1 | `TestListJobs` | `test_returns_only_published` |
| 2 | | `test_publicly_accessible` |
| 3 | | `test_pagination` |
| 4 | `TestCreateJob` | `test_member_can_create` |
| 5 | | `test_default_status_draft` |
| 6 | | `test_non_member_denied` |
| 7 | | `test_salary_max_less_than_min_400` |
| 8 | `TestJobDetail` | `test_retrieve_by_slug` |
| 9 | | `test_increments_views_count` |
| 10 | `TestPublishJob` | `test_publish_draft` |
| 11 | | `test_already_published_400` |
| 12 | | `test_non_member_denied` |
| 13 | `TestCloseJob` | `test_close_published` |
| 14 | `TestJobSearch` | `test_returns_matching_results` |
| 15 | | `test_missing_q_param_400` |

**`apps/jobs/tests/test_filters.py`** (7 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_filter_by_job_type` | Single value filter |
| 2 | `test_filter_by_experience_level` | Single value filter |
| 3 | `test_filter_by_is_remote` | Boolean filter |
| 4 | `test_filter_by_salary_range` | Range filter (min/max) |
| 5 | `test_filter_by_location` | Contains filter |
| 6 | `test_filter_by_company` | UUID filter |
| 7 | `test_multi_value_job_type` | `?job_type=full_time&job_type=contract` |

**`apps/jobs/tests/test_tasks.py`** (3 tests — per TESTING.md Section 6.3):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_closes_expired_published_jobs` | Past deadline → closed |
| 2 | `test_does_not_close_drafts` | Drafts unaffected |
| 3 | `test_idempotent_on_rerun` | Running twice closes 0 on second run |

**Total: 47 tests**

### 5.3 GREEN Phase — Implement

| Step | File | Reference |
|------|------|-----------|
| 1 | `apps/jobs/managers.py` | `published()`, `search()` (SearchVector/Query/Rank, threshold 0.1), `with_application_count()` |
| 2 | `apps/jobs/models.py` | Job model — ARCHITECTURE.md Section 2.2 (GIN index, composite indexes) |
| 3 | `apps/jobs/signals.py` | `update_search_vector` using `.filter(pk=).update()` to avoid infinite loop |
| 4 | `apps/jobs/filters.py` | `JobFilter` with all filter fields — ARCHITECTURE.md Section 3.4 |
| 5 | `apps/jobs/serializers.py` | Salary validation (max >= min), deadline validation (future) |
| 6 | `apps/jobs/views.py` | `JobViewSet` with publish/close `@action`, search `@action`, atomic F() in retrieve |
| 7 | `apps/jobs/tasks.py` | `close_expired_jobs` — ARCHITECTURE.md Section 4.2 |

### 5.4 Verification

```bash
docker compose exec web pytest apps/jobs/ -v                     # All 47 tests pass
docker compose exec web pytest --cov=apps/jobs/managers.py       # 100% on managers
# Manual: GET /api/jobs/search/?q=django → FTS results ranked by relevance
```

---

## Phase 6: Application Model, CRUD, Status Workflow, and Signals

**Goal:** Application model with unique_together, apply/list/status-update/withdraw endpoints, status state machine, signals triggering Celery tasks.

**Dependencies:** Phase 5 (Job FK), Phase 2 (User FK), Phase 1 (validate_resume).

### 6.1 Files to Create

```
apps/applications/
├── __init__.py
├── apps.py                 # ApplicationsConfig with ready() for signal import
├── models.py               # Application with status state machine
├── serializers.py          # ApplicationCreateSerializer, ApplicationListSerializer, StatusUpdateSerializer
├── views.py                # ApplicationViewSet, ApplicationStatusUpdateView
├── signals.py              # on_application_created, on_application_status_change
├── urls.py
├── admin.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_views.py
    └── test_signals.py
```

**Also update:** `tests/factories.py` (ApplicationFactory)

### 6.2 RED Phase — Tests to Write First

**`apps/applications/tests/test_models.py`** (6 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_create_application` | Application creation |
| 2 | `test_unique_together_job_applicant` | One application per candidate per job |
| 3 | `test_default_status_is_applied` | Correct default |
| 4 | `test_cascade_on_job_delete` | CASCADE behavior |
| 5 | `test_cascade_on_user_delete` | CASCADE behavior |
| 6 | `test_str_representation` | String repr |

**`apps/applications/tests/test_views.py`** (19 tests — per TESTING.md Section 4):

| # | Test Class | Test |
|---|------------|------|
| 1 | `TestCreateApplication` | `test_candidate_can_apply_successfully` |
| 2 | | `test_signal_fires_celery_task_on_create` |
| 3 | | `test_unauthenticated_user_gets_401` |
| 4 | | `test_recruiter_cannot_apply` |
| 5 | | `test_duplicate_application_rejected` |
| 6 | | `test_cannot_apply_to_draft_job` |
| 7 | | `test_cannot_apply_to_expired_job` |
| 8 | | `test_invalid_resume_type_rejected` |
| 9 | `TestListApplications` | `test_candidate_sees_own` |
| 10 | | `test_recruiter_sees_company_applications` |
| 11 | | `test_recruiter_notes_hidden_from_candidate` |
| 12 | `TestUpdateApplicationStatus` | `test_valid_transition_applied_to_reviewing` |
| 13 | | `test_invalid_transition_applied_to_offered` |
| 14 | | `test_non_member_recruiter_denied` |
| 15 | | `test_candidate_cannot_update_status` |
| 16 | | `test_status_change_triggers_email_task` |
| 17 | `TestWithdrawApplication` | `test_can_withdraw_applied` |
| 18 | | `test_cannot_withdraw_rejected` |
| 19 | | `test_non_owner_cannot_withdraw` |

**`apps/applications/tests/test_signals.py`** (5 tests — per TESTING.md Section 5):

| # | Test Class | Test |
|---|------------|------|
| 1 | `TestOnApplicationCreated` | `test_fires_on_new_application` |
| 2 | | `test_does_not_fire_on_update` |
| 3 | `TestOnStatusChange` | `test_fires_when_status_changes` |
| 4 | | `test_does_not_fire_when_status_unchanged` |
| 5 | | `test_does_not_fire_on_new_application` |

**Total: 30 tests**

### 6.3 GREEN Phase — Implement

| Step | Detail |
|------|--------|
| 1 | `apps/applications/models.py` — unique_together(job, applicant), status choices, composite indexes |
| 2 | Status transition state machine: `VALID_TRANSITIONS = {"applied": {"reviewing", "rejected"}, ...}` + `WITHDRAWABLE_STATUSES` |
| 3 | `apps/applications/signals.py` — `on_application_created` (post_save): `.delay()`. `on_application_status_change` (pre_save): detect change, `.delay()` |
| 4 | `ApplicationCreateSerializer` — validates: job is published, deadline not passed, unique_together, resume via validate_resume, sets applicant from request.user |
| 5 | `ApplicationStatusUpdateSerializer` — validates transitions against state machine dict |
| 6 | `ApplicationListSerializer` — conditional exclusion of `recruiter_notes` for candidates |
| 7 | Views: create=IsCandidate, list=IsAuthenticated (scoped by role), destroy=withdraw (IsOwnerOrReadOnly), status update=IsRecruiter+IsCompanyMember |

### 6.4 Verification

```bash
docker compose exec web pytest apps/applications/ -v                   # All 30 pass
docker compose exec web pytest --cov=apps/applications/signals.py      # 100% on signals
# State machine: applied → offered correctly returns 400
# Signal mocks confirm Celery tasks dispatched with correct args
```

---

## Phase 7: Notification Model, Celery Tasks, and Pydantic Schemas

**Goal:** Notification model, real Celery task implementations with Pydantic payload validation, notification CRUD.

**Dependencies:** Phase 6 (Application model + signals that call tasks).

### 7.1 Files to Create

```
apps/notifications/
├── __init__.py
├── apps.py
├── models.py               # Notification
├── tasks.py                # send_application_received_email, send_status_update_email
├── schemas.py              # ApplicationEmailPayload, StatusUpdateEmailPayload (Pydantic)
├── serializers.py          # NotificationSerializer
├── views.py                # NotificationViewSet (list, mark_read, mark_all_read)
├── urls.py
├── admin.py
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_tasks.py
    ├── test_schemas.py
    └── test_views.py
```

**Also update:** `tests/factories.py` (NotificationFactory)

### 7.2 RED Phase — Tests to Write First

**`apps/notifications/tests/test_schemas.py`** (9 tests — per TESTING.md Section 3.2-3.3):

| # | Test Class | Test |
|---|------------|------|
| 1 | `TestApplicationEmailPayload` | `test_valid_uuid_passes` |
| 2 | | `test_invalid_uuid_raises` |
| 3 | | `test_empty_string_raises` |
| 4 | | `test_missing_field_raises` |
| 5 | `TestStatusUpdateEmailPayload` | `test_valid_input_passes` |
| 6 | | `test_invalid_uuid_raises` |
| 7 | | `test_invalid_status_raises` (parametrized) |
| 8 | | `test_all_valid_statuses_accepted` (parametrized) |
| 9 | | `test_missing_required_fields_raises` |

**`apps/notifications/tests/test_tasks.py`** (8 tests — per TESTING.md Section 6.1-6.2):

| # | Test Class | Test |
|---|------------|------|
| 1 | `TestSendApplicationReceivedEmail` | `test_sends_email_to_applicant` |
| 2 | | `test_email_subject_contains_job_title` |
| 3 | | `test_nonexistent_application_does_not_crash` |
| 4 | | `test_invalid_uuid_does_not_retry` |
| 5 | | `test_retry_on_smtp_failure` |
| 6 | `TestSendStatusUpdateEmail` | `test_sends_email_with_status_change` |
| 7 | | `test_retry_on_smtp_failure` |
| 8 | | `test_invalid_status_does_not_retry` |

**`apps/notifications/tests/test_models.py`** (4 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_create_notification` | Notification creation |
| 2 | `test_default_is_read_false` | Correct default |
| 3 | `test_metadata_default_empty_dict` | JSONB default |
| 4 | `test_type_choices` | Valid notification types |

**`apps/notifications/tests/test_views.py`** (7 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_user_sees_own_notifications` | Scoped to user |
| 2 | `test_filter_by_is_read` | Read/unread filter |
| 3 | `test_includes_unread_count` | Aggregation in response |
| 4 | `test_unauthenticated_401` | Auth required |
| 5 | `test_mark_single_read` | Mark one as read |
| 6 | `test_cannot_mark_other_users` | Permission check |
| 7 | `test_mark_all_read_returns_count` | Bulk update + count |

**Total: 28 tests**

### 7.3 GREEN Phase — Implement

| Step | Detail | Reference |
|------|--------|-----------|
| 1 | `apps/notifications/schemas.py` | Module-level `VALID_STATUSES` frozenset, Pydantic models — ARCHITECTURE.md Section 5.2 |
| 2 | `apps/notifications/models.py` | Notification model — ARCHITECTURE.md Section 2.2 |
| 3 | `apps/notifications/tasks.py` | Validate with Pydantic → load with select_related → send_mail → retry on exception — ARCHITECTURE.md Section 4.2 |
| 4 | Views | `mark_read` as `@action(detail=True)`, `mark_all_read` as `@action(detail=False)` |
| 5 | `tests/factories.py` | Add `NotificationFactory` — TESTING.md Section 7 |

### 7.4 Verification

```bash
docker compose exec web pytest apps/notifications/ -v              # All 28 pass
docker compose exec web pytest --cov=apps/notifications/schemas.py # 100%
docker compose exec web pytest --cov=apps/notifications/tasks.py   # 95%+
# Phase 6 signal tests still pass with real task implementations
```

---

## Phase 8: Dashboard Aggregation Endpoints

**Goal:** Recruiter and candidate dashboard views with aggregated stats.

**Dependencies:** Phase 4 (Companies), Phase 5 (Jobs), Phase 6 (Applications).

### 8.1 Files to Create

```
apps/dashboard/
├── __init__.py
├── apps.py
├── views.py                # RecruiterDashboardView, CandidateDashboardView
├── serializers.py
├── urls.py
└── tests/
    ├── __init__.py
    └── test_views.py
```

### 8.2 RED Phase — Tests to Write First

**`apps/dashboard/tests/test_views.py`** (16 tests):

| # | Test Class | Test |
|---|------------|------|
| 1 | `TestRecruiterDashboard` | `test_returns_total_jobs` |
| 2 | | `test_returns_jobs_by_status` |
| 3 | | `test_returns_total_applications` |
| 4 | | `test_returns_applications_by_status` |
| 5 | | `test_returns_recent_applications` |
| 6 | | `test_only_recruiter_can_access` |
| 7 | | `test_candidate_gets_403` |
| 8 | | `test_scoped_to_recruiters_companies` (multi-tenant isolation) |
| 9 | `TestCandidateDashboard` | `test_returns_total_applications` |
| 10 | | `test_returns_applications_by_status` |
| 11 | | `test_returns_recent_applications` |
| 12 | | `test_only_candidate_can_access` |
| 13 | | `test_recruiter_gets_403` |
| 14 | | `test_unauthenticated_401` |
| 15 | | `test_scoped_to_own_applications` |
| 16 | | `test_recent_limit_is_five` |

**Total: 16 tests**

### 8.3 GREEN Phase — Implement

| View | Logic |
|------|-------|
| `RecruiterDashboardView` | Find all companies where user is member → aggregate jobs by status → aggregate applications by status → 5 most recent applications with applicant + job info |
| `CandidateDashboardView` | Count user's applications → group by status → 5 most recent with job + company info |

Wire URLs at `/api/dashboard/recruiter/` and `/api/dashboard/candidate/`. Response shapes per ARCHITECTURE.md Section 3.6.

### 8.4 Verification

```bash
docker compose exec web pytest apps/dashboard/ -v   # All 16 pass
# Multi-tenant: recruiter from Company A sees 0 jobs from Company B
```

---

## Phase 9: OpenAPI Documentation & Swagger UI

**Goal:** drf-spectacular integration for auto-generated API docs.

**Dependencies:** All endpoints from Phases 2-8.

### 9.1 Files to Modify

- `config/settings/base.py` — Add `drf-spectacular` to INSTALLED_APPS + SPECTACULAR_SETTINGS
- `config/urls.py` — Add `/api/docs/`, `/api/schema/`
- All `views.py` files — Add `@extend_schema` decorators

### 9.2 RED Phase — Tests to Write First

**`tests/test_docs.py`** (6 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_schema_endpoint_returns_200` | Schema endpoint works |
| 2 | `test_schema_is_valid_openapi` | Valid OpenAPI 3.0 |
| 3 | `test_swagger_ui_returns_200` | Swagger UI renders |
| 4 | `test_schema_contains_auth_endpoints` | Auth paths present |
| 5 | `test_schema_contains_job_endpoints` | Job paths present |
| 6 | `test_schema_contains_application_endpoints` | Application paths present |

**Total: 6 tests**

### 9.3 GREEN Phase — Implement

1. `SPECTACULAR_SETTINGS = {"TITLE": "HireFlow API", "VERSION": "1.0.0", ...}`
2. Add `SpectacularAPIView`, `SpectacularSwaggerView` URLs
3. Add `@extend_schema` annotations to all viewsets

### 9.4 Verification

```bash
docker compose exec web pytest tests/test_docs.py -v  # All 6 pass
# Manual: http://localhost:8000/api/docs/ → Swagger UI with all endpoints
```

---

## Phase 10: Production Hardening, Seed Data, and Final Integration

**Goal:** Production settings, structured logging, request logger middleware, seed data command, CI pipeline, and end-to-end integration test.

**Dependencies:** All previous phases.

### 10.1 Files to Create/Modify

```
config/settings/production.py       # HTTPS, HSTS, security hardening
config/settings/base.py             # Add LOGGING config, middleware
middleware/
└── request_logger.py               # RequestLoggerMiddleware
apps/accounts/management/commands/
└── seed_data.py                    # Seed data command
.pre-commit-config.yaml
.github/workflows/ci.yml            # GitHub Actions CI
tests/
├── test_middleware.py
├── test_seed_data.py
└── test_full_integration.py
```

### 10.2 RED Phase — Tests to Write First

**`tests/test_middleware.py`** (4 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_logs_request_method_and_path` | Request attributes logged |
| 2 | `test_logs_response_status_code` | Status code captured |
| 3 | `test_logs_authenticated_user` | User ID logged |
| 4 | `test_skips_health_check_logging` | No noise from health checks |

**`tests/test_seed_data.py`** (4 tests):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `test_seed_creates_users` | 7 users created (2 recruiters + 5 candidates) |
| 2 | `test_seed_creates_companies_and_jobs` | 2 companies + 6 jobs |
| 3 | `test_seed_creates_applications` | 15 applications |
| 4 | `test_seed_flush_wipes_and_recreates` | --flush flag works |

**`tests/test_full_integration.py`** (1 comprehensive test):

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `TestFullWorkflow::test_complete_happy_path` | Entire system works end-to-end |

**Full workflow steps:**
1. Register recruiter + candidate
2. Recruiter creates company
3. Recruiter creates job + publishes it
4. Candidate applies
5. Recruiter advances application: applied → reviewing → shortlisted → interview → offered
6. Both check dashboards — correct counts
7. Verify notifications exist

**Total: 9 tests**

### 10.3 GREEN Phase — Implement

| Step | Detail | Reference |
|------|--------|-----------|
| 1 | `middleware/request_logger.py` | JSON logging, skips /api/health/ — DEPLOYMENT.md Section 8 |
| 2 | `config/settings/production.py` | SECURE_SSL_REDIRECT, HSTS, CSRF_COOKIE_SECURE, SESSION_COOKIE_SECURE |
| 3 | LOGGING config in base.py | Structured JSON logging — DEPLOYMENT.md Section 8 |
| 4 | `seed_data.py` | 2 recruiters, 5 candidates, 2 companies, 6 jobs, 15 apps — CONTRIBUTING.md Section 7 |
| 5 | Celery Beat schedule in base.py | `close-expired-jobs-daily` — ARCHITECTURE.md Section 4.4 |
| 6 | `.pre-commit-config.yaml` | Ruff hooks — CONTRIBUTING.md Section 9.4 |
| 7 | `.github/workflows/ci.yml` | PostgreSQL + Redis services, pytest + coverage — TESTING.md Section 10 |

### 10.4 Final Verification — Complete Checklist

```bash
# ── All tests pass ──────────────────────────────────────────
docker compose exec web pytest -v
# Expected: ~215 tests passed

# ── Coverage meets target ───────────────────────────────────
docker compose exec web pytest \
  --cov=apps --cov=common \
  --cov-report=term-missing \
  --cov-fail-under=90
# Expected: >= 90% overall

# ── Coverage by layer ──────────────────────────────────────
# managers.py:     100%
# validators.py:   100%
# permissions.py:  100%
# signals.py:      100%
# schemas.py:      100%
# tasks.py:        >= 95%
# views.py:        >= 85%
# models.py:       >= 70%

# ── Linting clean ──────────────────────────────────────────
docker compose exec web ruff check .
docker compose exec web ruff format . --check

# ── Seed data works ────────────────────────────────────────
docker compose exec web python manage.py seed_data
docker compose exec web python manage.py seed_data --flush

# ── Production settings pass ───────────────────────────────
docker compose exec web python manage.py check --deploy

# ── Full integration test ──────────────────────────────────
docker compose exec web pytest tests/test_full_integration.py -v
```

---

## Summary Table

| Phase | What | New Files | Tests | Coverage Target |
|-------|------|-----------|-------|-----------------|
| 1 | Skeleton, Docker, Settings, Base Model | ~25 | ~19 | 100% validators, pagination |
| 2 | User, Auth, JWT, Email Verification | ~12 | ~25 | 100% tokens |
| 3 | Custom Permissions | 1 | ~13 | 100% permissions |
| 4 | Company & CompanyMember CRUD | ~10 | ~20 | 85% views |
| 5 | Job, FTS, Manager, Filters, Tasks | ~14 | ~47 | 100% managers |
| 6 | Application, Status Workflow, Signals | ~10 | ~30 | 100% signals |
| 7 | Notification, Celery Tasks, Pydantic | ~12 | ~28 | 100% schemas, 95% tasks |
| 8 | Dashboard Aggregation | ~6 | ~16 | 85% views |
| 9 | OpenAPI Docs & Swagger | 0 (modify) | ~6 | N/A |
| 10 | Production Hardening, Seed, Integration | ~6 | ~9 | **90% overall** |
| **Total** | | **~96 files** | **~213 tests** | |

---

## Key Design Decisions

1. **Permissions tested before their models exist** (Phase 3 uses MagicMock, re-validated with real DB objects in Phase 4) — isolates permission logic from ORM concerns.

2. **Factories built incrementally** — each phase adds only what it needs: UserFactory (Phase 2), CompanyFactory (Phase 4), JobFactory (Phase 5), ApplicationFactory (Phase 6), NotificationFactory (Phase 7).

3. **Signals tested by mocking `.delay()`**, not the signal itself — ensures the wiring is correct (the signal actually fires and calls the right task with correct args).

4. **FTS search tests use `index_search_vector` fixture** to manually populate search_vector — deterministic, not dependent on signal timing.

5. **Status state machine is a plain dict**, not a third-party library — fully testable with simple unit tests, no external dependencies.

6. **Pydantic validates Celery task payloads at task entry** — bad payloads return early without retries (invalid data will never become valid).
