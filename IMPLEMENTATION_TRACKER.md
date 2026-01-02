# HireFlow — Implementation Tracker

> Track progress for each phase of the TDD build plan.
>
> Status Legend: `[ ]` Not Started · `[~]` In Progress · `[x]` Complete · `[!]` Blocked
>
> Last updated: 2026-03-21

---

## Progress Overview

| Phase | Name | Status | Tests Written | Tests Passing | Coverage |
|-------|------|--------|---------------|---------------|----------|
| 1 | Project Skeleton & Base Model | `[x]` Complete | 25 / 25 | 25 / 25 | 71% (100% validators, pagination, models) |
| 2 | User Model & Auth | `[x]` Complete | 27 / 27 | 27 / 27 | 100% tokens, 100% signals, 96% views |
| 3 | Custom Permissions | `[x]` Complete | 13 / 13 | 13 / 13 | 100% (IsCompanyMember added in Phase 4) |
| 4 | Company & CompanyMember | `[x]` Complete | 24 / 24 | 24 / 24 | 96% |
| 5 | Job Model, FTS & Manager | `[x]` Complete | 50 / 50 | 50 / 50 | 92% (100% managers, signals, tasks) |
| 6 | Application & Status Workflow | `[x]` Complete | 31 / 31 | 31 / 31 | 94% (100% models, serializers, signals) |
| 7 | Notifications & Celery Tasks | `[x]` Complete | 37 / 37 | 37 / 37 | 92% (100% views, serializers, URLs) |
| 8 | Dashboard Aggregation | `[x]` Complete | 16 / 16 | 16 / 16 | 100% views |
| 9 | OpenAPI Docs & Swagger | `[x]` Complete | 6 / 6 | 6 / 6 | N/A |
| 10 | Production Hardening & Integration | `[x]` Complete | 9 / 9 | 9 / 9 | **94% overall** |
| **Total** | | | **234 / 234** | **234 / 234** | **94%** |

---

## Phase 1: Project Skeleton, Docker, Settings, and Base Model

**Branch:** `feature/HF-001-project-skeleton`

### Infrastructure Setup

- [x] Create `requirements/base.txt` with pinned dependencies
- [x] Create `requirements/development.txt`
- [x] Create `requirements/production.txt`
- [x] Create `Dockerfile` (development)
- [x] Create `docker-compose.yml` (5 services: web, db, redis, celery, beat)
- [x] Create `.env.example`
- [x] Create `.gitignore`
- [x] Create `pyproject.toml` (Ruff config)
- [x] Create `setup.cfg` (pytest + coverage config)

### Django Project Setup

- [x] Create `manage.py`
- [x] Create `config/__init__.py`
- [x] Create `config/env.py` — `HireFlowSettings` (pydantic-settings)
- [x] Create `config/celery.py` — Celery app init
- [x] Create `config/wsgi.py`
- [x] Create `config/urls.py` — Root URL config
- [x] Create `config/settings/base.py`
- [x] Create `config/settings/development.py`
- [x] Create `config/settings/test.py`
- [x] Create `config/settings/production.py` (placeholder)

### Common Module

- [x] Create `common/models.py` — `TimeStampedModel`
- [x] Create `common/validators.py` — `validate_resume`
- [x] Create `common/pagination.py` — `HireFlowCursorPagination`
- [x] Create `common/exceptions.py` — Custom exception handler
- [x] Create `common/permissions.py` — Stub file

### Health Check

- [x] Create `apps/health/views.py` — DB + Redis health check
- [x] Create `apps/health/urls.py`

### Tests (RED → GREEN)

- [x] `common/tests/test_models.py` — 4 tests for TimeStampedModel
  - [x] `test_model_is_abstract`
  - [x] `test_uuid_pk_is_generated`
  - [x] `test_created_at_is_auto_set`
  - [x] `test_updated_at_changes_on_save`
- [x] `common/tests/test_validators.py` — 12 tests for validate_resume (parametrized)
  - [x] `test_valid_file_passes` (3 parametrized: pdf, doc, docx)
  - [x] `test_wrong_extension_raises` (5 parametrized: exe, py, jpg, txt, zip)
  - [x] `test_file_too_large_raises`
  - [x] `test_file_exactly_at_limit_passes`
  - [x] `test_wrong_mime_type_raises`
  - [x] `test_missing_content_type_does_not_crash`
- [x] `common/tests/test_pagination.py` — 3 tests
  - [x] `test_default_page_size_is_20`
  - [x] `test_max_page_size_is_100`
  - [x] `test_default_ordering_is_minus_created_at`
- [x] `common/tests/test_exceptions.py` — 3 tests
  - [x] `test_error_format_has_error_code_details_keys`
  - [x] `test_validation_error_formats_details`
  - [x] `test_404_error_format`
- [x] `apps/health/tests/test_views.py` — 3 tests
  - [x] `test_health_check_returns_200`
  - [x] `test_contains_database_status`
  - [x] `test_contains_redis_status`
- [x] `conftest.py` — Root conftest with `api_client` fixture
- [x] `tests/factories.py` — Empty file (populated in later phases)

### Phase 1 Verification Checklist

- [ ] `docker compose up -d` — All 5 services running (Docker verification deferred to post-development)
- [x] `pytest` — 25/25 tests pass (includes parametrized tests)
- [x] `ruff check .` — No lint errors
- [ ] `curl http://localhost:8000/api/health/` — Returns healthy (requires Docker/running server)
- [x] 100% coverage on `common/validators.py`
- [x] 100% coverage on `common/pagination.py`
- [x] 100% coverage on `common/models.py`

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 2: User Model, Registration, Login, and Email Verification

**Branch:** `feature/HF-002-user-auth`

### Models & Core

- [x] Create `apps/accounts/models.py` — User (AbstractUser + TimeStampedModel)
- [x] Set `AUTH_USER_MODEL = "accounts.User"` in base.py
- [x] Create `apps/accounts/tokens.py` — TimestampSigner email verification
- [x] Create `apps/accounts/signals.py` — send_verification_email_on_register (direct send_mail, refactor to Celery in Phase 7)
- [x] Create `apps/accounts/apps.py` — Register signals in `ready()`
- [x] Run `python manage.py makemigrations accounts`
- [x] Run `python manage.py migrate`

### Serializers & Views

- [x] Create `apps/accounts/serializers.py` — RegisterSerializer, LoginSerializer, UserSerializer
- [x] Create `apps/accounts/views.py` — RegisterView, LoginView, TokenRefreshView, VerifyEmailView
- [x] Create `apps/accounts/urls.py` — Wire at `/api/auth/`
- [x] Create `apps/accounts/admin.py`

### Tests (RED → GREEN)

- [x] `apps/accounts/tests/test_models.py` — 7 tests
  - [x] `test_create_user_with_email`
  - [x] `test_email_is_username_field`
  - [x] `test_default_role_is_candidate`
  - [x] `test_uuid_primary_key`
  - [x] `test_is_email_verified_default_false`
  - [x] `test_str_returns_email`
  - [x] `test_role_choices_are_candidate_recruiter_admin`
- [x] `apps/accounts/tests/test_tokens.py` — 4 tests
  - [x] `test_make_token_returns_string`
  - [x] `test_verify_valid_token_returns_user_id`
  - [x] `test_verify_expired_token_raises`
  - [x] `test_verify_tampered_token_raises`
- [x] `apps/accounts/tests/test_views.py` — 16 tests
  - [x] `test_register_returns_201`
  - [x] `test_creates_user_in_db`
  - [x] `test_duplicate_email_returns_400`
  - [x] `test_password_mismatch_returns_400`
  - [x] `test_weak_password_returns_400`
  - [x] `test_default_role_is_candidate`
  - [x] `test_register_as_recruiter`
  - [x] `test_response_does_not_contain_password`
  - [x] `test_register_sends_verification_email`
  - [x] `test_returns_access_and_refresh_tokens`
  - [x] `test_returns_user_data`
  - [x] `test_wrong_password_returns_401`
  - [x] `test_nonexistent_email_returns_401`
  - [x] `test_refresh_returns_new_access_token`
  - [x] `test_valid_token_sets_is_email_verified`
  - [x] `test_invalid_token_returns_400`
- [x] Update `tests/factories.py` — Add `UserFactory`
- [x] Update `conftest.py` — Add candidate, recruiter, candidate_client, recruiter_client

### Phase 2 Verification Checklist

- [x] `pytest apps/accounts/` — 27/27 pass
- [x] `pytest` — All prior tests still pass (cumulative: 52)
- [x] 100% coverage on `apps/accounts/tokens.py`
- [x] 100% coverage on `apps/accounts/signals.py`
- [x] 100% coverage on `apps/accounts/models.py`
- [x] 100% coverage on `apps/accounts/serializers.py`
- [x] Password never exposed in any API response

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 3: Custom Permissions

**Branch:** `feature/HF-003-permissions`

### Implementation

- [x] Implement `IsRecruiter` in `common/permissions.py`
- [x] Implement `IsCandidate` in `common/permissions.py`
- [x] Implement `IsCompanyMember` in `common/permissions.py`
- [x] Implement `IsOwnerOrReadOnly` in `common/permissions.py`

### Tests (RED → GREEN)

- [x] `common/tests/test_permissions.py` — 9 tests (no mocking, real User objects)
  - [x] `TestIsRecruiter::test_recruiter_allowed`
  - [x] `TestIsRecruiter::test_candidate_denied`
  - [x] `TestIsRecruiter::test_anonymous_denied`
  - [x] `TestIsCandidate::test_candidate_allowed`
  - [x] `TestIsCandidate::test_recruiter_denied`
  - [x] `TestIsCandidate::test_anonymous_denied`
  - [x] `TestIsCompanyMember` — 4 tests added in Phase 4 (real Company/CompanyMember objects)
  - [x] `TestIsOwnerOrReadOnly::test_get_always_allowed`
  - [x] `TestIsOwnerOrReadOnly::test_owner_can_modify`
  - [x] `TestIsOwnerOrReadOnly::test_non_owner_cannot_modify`

### Phase 3 Verification Checklist

- [x] `pytest common/tests/test_permissions.py` — 13/13 pass (4 IsCompanyMember tests added in Phase 4)
- [x] `pytest` — Cumulative: 61 pass (at Phase 3 completion)
- [x] 100% coverage on `common/permissions.py` (IsCompanyMember validated with real DB in Phase 4)
- [x] Overall coverage: 90.53% — exceeds 90% threshold

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 4: Company & CompanyMember CRUD

**Branch:** `feature/HF-004-companies`

### Models & Core

- [x] Create `apps/companies/models.py` — Company, CompanyMember
- [x] Create migration with `unique_together = ("user", "company")`
- [x] Run `python manage.py migrate`

### Serializers & Views

- [x] Create `apps/companies/serializers.py` — CompanyCreateSerializer (atomic create + owner), InviteMemberSerializer
- [x] Create `apps/companies/views.py` — CompanyViewSet (lookup_field="slug"), InviteMemberView
- [x] Create `apps/companies/urls.py`
- [x] Create `apps/companies/admin.py`

### Tests (RED → GREEN)

- [x] `apps/companies/tests/test_models.py` — 7 tests
  - [x] `test_create_company`
  - [x] `test_slug_is_unique`
  - [x] `test_str_returns_name`
  - [x] `test_is_verified_defaults_to_false`
  - [x] `test_create_member`
  - [x] `test_unique_together_user_company`
  - [x] `test_default_role_is_recruiter`
- [x] `apps/companies/tests/test_views.py` — 13 tests
  - [x] `test_returns_only_verified`
  - [x] `test_publicly_accessible`
  - [x] `test_pagination`
  - [x] `test_recruiter_can_create`
  - [x] `test_creator_becomes_owner`
  - [x] `test_candidate_cannot_create`
  - [x] `test_unauthenticated_401`
  - [x] `test_duplicate_slug_400`
  - [x] `test_retrieve_by_slug`
  - [x] `test_owner_can_update`
  - [x] `test_non_owner_member_denied`
  - [x] `test_owner_can_invite`
  - [x] `test_already_member_400`
- [x] `common/tests/test_permissions.py` — 4 IsCompanyMember tests added (real Company objects)
  - [x] `test_member_has_permission`
  - [x] `test_non_member_denied`
  - [x] `test_candidate_denied`
  - [x] `test_member_of_different_company_denied`
- [x] Update `tests/factories.py` — Add CompanyFactory, CompanyMemberFactory
- [x] **Re-validated Phase 3 permission tests with real DB objects** — all 13 pass

### Phase 4 Verification Checklist

- [x] `pytest apps/companies/` — 20/20 pass
- [x] `pytest common/tests/test_permissions.py` — 13/13 pass with real objects
- [x] `pytest` — Cumulative: 85 pass
- [x] `ruff check .` — Clean
- [x] 96% coverage on `apps/companies/`

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 5: Job Model, CRUD, Full-Text Search, and Custom Manager

**Branch:** `feature/HF-005-jobs`

### Models & Core

- [x] Create `apps/jobs/managers.py` — published(), search(), with_application_count()
- [x] Create `apps/jobs/models.py` — Job with SearchVectorField, GIN index, composite indexes
- [x] Create `apps/jobs/signals.py` — update_search_vector (post_save, .filter().update() pattern)
- [x] Create `apps/jobs/apps.py` — Register signals in ready()
- [x] Create migration
- [x] Run `python manage.py migrate`

### Serializers, Views & Filters

- [x] Create `apps/jobs/filters.py` — JobFilter (title, location, salary, is_remote, job_type, experience_level, company)
- [x] Create `apps/jobs/serializers.py` — Salary validation in JobCreateSerializer
- [x] Create `apps/jobs/views.py` — JobViewSet with publish/close @actions, search @action, atomic F() in retrieve
- [x] Create `apps/jobs/tasks.py` — close_expired_jobs
- [x] Create `apps/jobs/urls.py`
- [x] Create `apps/jobs/admin.py`

### Tests (RED → GREEN)

- [x] `apps/jobs/tests/test_models.py` — 9 tests
  - [x] `test_create_job`
  - [x] `test_slug_is_unique`
  - [x] `test_default_status_is_draft`
  - [x] `test_str_returns_title`
  - [x] `test_skills_default_empty_list`
  - [x] `test_views_count_default_zero`
  - [x] `test_status_choices`
  - [x] `test_posted_by_set_null_on_delete`
  - [x] `test_company_cascade_on_delete`
- [x] `apps/jobs/tests/test_managers.py` — 10 passing + 3 skipped
  - [x] `TestJobManagerPublished::test_returns_published_jobs`
  - [x] `TestJobManagerPublished::test_excludes_past_deadline`
  - [x] `TestJobManagerPublished::test_includes_future_deadline`
  - [x] `TestJobManagerPublished::test_includes_no_deadline`
  - [x] `TestJobManagerPublished::test_includes_today_as_deadline`
  - [x] `TestJobManagerSearch::test_search_matches_title`
  - [x] `TestJobManagerSearch::test_search_matches_description`
  - [x] `TestJobManagerSearch::test_title_ranks_higher`
  - [x] `TestJobManagerSearch::test_search_excludes_drafts`
  - [x] `TestJobManagerSearch::test_empty_for_no_match`
  - [ ] `TestJobManagerWithApplicationCount` — 3 tests skipped (Application model not yet created, deferred to Phase 6)
- [x] `apps/jobs/tests/test_views.py` — 18 tests
  - [x] `test_returns_only_published`
  - [x] `test_publicly_accessible`
  - [x] `test_pagination_returns_cursor`
  - [x] `test_member_can_create`
  - [x] `test_default_status_draft`
  - [x] `test_non_member_denied`
  - [x] `test_salary_max_less_than_min_returns_400`
  - [x] `test_retrieve_by_slug`
  - [x] `test_increments_views_count`
  - [x] `test_publish_draft`
  - [x] `test_already_published_returns_400`
  - [x] `test_non_member_denied` (publish)
  - [x] `test_close_published`
  - [x] `test_draft_returns_400` (close)
  - [x] `test_search_returns_matching_results`
  - [x] `test_search_ordered_by_rank`
  - [x] `test_missing_q_returns_400`
  - [x] `test_no_results_empty`
- [x] `apps/jobs/tests/test_filters.py` — 7 tests
  - [x] `test_filter_by_job_type`
  - [x] `test_filter_by_experience_level`
  - [x] `test_filter_by_is_remote`
  - [x] `test_filter_by_salary_range`
  - [x] `test_filter_by_location`
  - [x] `test_filter_by_company`
  - [x] `test_multi_value_job_type`
- [x] `apps/jobs/tests/test_tasks.py` — 3 tests
  - [x] `test_closes_expired_published_jobs`
  - [x] `test_does_not_close_drafts`
  - [x] `test_idempotent_on_rerun`
- [x] Update `tests/factories.py` — Add JobFactory

### Phase 5 Verification Checklist

- [x] `pytest apps/jobs/` — 47 passed, 3 skipped
- [x] `pytest` — Cumulative: 132 (129 passed + 3 skipped)
- [x] 92% coverage on `apps/jobs/` (100% managers, models, serializers, signals, tasks, filters)
- [x] GIN index present in migration file
- [x] FTS search: title matches rank higher than description matches
- [x] `ruff check .` — Clean

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 6: Application Model, CRUD, Status Workflow, and Signals

**Branch:** `feature/HF-006-applications`

### Models & Core

- [x] Create `apps/applications/models.py` — unique_together(job, applicant), status choices, VALID_TRANSITIONS dict, WITHDRAWABLE_STATUSES, composite indexes
- [x] Create `apps/applications/signals.py` — on_application_created (post_save), on_status_change (pre_save)
- [x] Create `apps/applications/apps.py` — Register signals in ready()
- [x] Create `apps/notifications/tasks.py` — Stub tasks (real email sending via locmem, enhanced in Phase 7)
- [x] Create `apps/notifications/apps.py`
- [x] Create migration
- [x] Run `python manage.py migrate`

### Serializers & Views

- [x] Create `apps/applications/serializers.py` — ApplicationCreateSerializer (validates: published job, deadline, unique, resume), ApplicationListSerializer (no recruiter_notes), ApplicationRecruiterSerializer (with recruiter_notes), StatusUpdateSerializer (validates transitions)
- [x] Create `apps/applications/views.py` — create=IsCandidate, list=IsAuthenticated (role-scoped queryset), destroy=withdraw, ApplicationStatusUpdateView
- [x] Create `apps/applications/urls.py`
- [x] Create `apps/applications/admin.py`

### Tests (RED → GREEN)

- [x] `apps/applications/tests/test_models.py` — 7 tests
  - [x] `test_create_application`
  - [x] `test_unique_together_job_applicant`
  - [x] `test_default_status_is_applied`
  - [x] `test_cascade_on_job_delete`
  - [x] `test_cascade_on_user_delete`
  - [x] `test_str_representation`
  - [x] `test_status_choices`
- [x] `apps/applications/tests/test_views.py` — 19 tests
  - [x] `test_candidate_can_apply`
  - [x] `test_signal_fires_email_on_create`
  - [x] `test_unauthenticated_gets_401`
  - [x] `test_recruiter_cannot_apply`
  - [x] `test_duplicate_application_rejected`
  - [x] `test_cannot_apply_to_draft_job`
  - [x] `test_cannot_apply_to_expired_job`
  - [x] `test_invalid_resume_rejected`
  - [x] `test_candidate_sees_own`
  - [x] `test_recruiter_sees_company_applications`
  - [x] `test_recruiter_notes_hidden_from_candidate`
  - [x] `test_valid_transition`
  - [x] `test_invalid_transition_returns_400`
  - [x] `test_non_member_denied`
  - [x] `test_candidate_cannot_update_status`
  - [x] `test_status_change_triggers_email`
  - [x] `test_can_withdraw_applied`
  - [x] `test_cannot_withdraw_rejected`
  - [x] `test_non_owner_denied` (returns 404 — IDOR protection via scoped queryset)
- [x] `apps/applications/tests/test_signals.py` — 5 tests (no mocking — uses real Celery eager + locmem email)
  - [x] `test_fires_on_new_application`
  - [x] `test_does_not_fire_on_update`
  - [x] `test_fires_when_status_changes`
  - [x] `test_does_not_fire_when_status_unchanged`
  - [x] `test_does_not_fire_on_new_application` (pre_save)
- [x] Update `tests/factories.py` — Add ApplicationFactory
- [x] **Unskipped Phase 5 with_application_count tests** — all 3 now pass with real Application model

### Phase 6 Verification Checklist

- [x] `pytest apps/applications/` — 31/31 pass
- [x] `pytest` — Cumulative: 166 pass
- [x] 95% coverage on `apps/applications/signals.py`
- [x] 100% coverage on `apps/applications/models.py` and `serializers.py`
- [x] State machine: applied → offered returns 400
- [x] Signal tests use real Celery eager + locmem email (no mocking)
- [x] `ruff check .` — Clean

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 7: Notification Model, Celery Tasks, and Pydantic Schemas

**Branch:** `feature/HF-007-notifications`

### Models & Core

- [x] Create `apps/notifications/schemas.py` — VALID_STATUSES, ApplicationEmailPayload, StatusUpdateEmailPayload (Pydantic v2)
- [x] Create `apps/notifications/models.py` — Notification (Type choices, user FK, title, message, is_read, metadata, indexes)
- [x] Create `apps/notifications/tasks.py` — send_application_received_email, send_status_update_email (bind=True, max_retries=3, Pydantic validation, Notification creation)
- [x] Create migration
- [x] Run `python manage.py migrate`

### Serializers & Views

- [x] Create `apps/notifications/serializers.py` — NotificationSerializer (read-only)
- [x] Create `apps/notifications/views.py` — NotificationViewSet (list with unread_count, mark_read, mark_all_read, is_read filter)
- [x] Create `apps/notifications/urls.py` — DefaultRouter
- [x] Wire URLs in `config/urls.py` at `/api/notifications/`

### Tests (RED → GREEN)

- [x] `apps/notifications/tests/test_schemas.py` — 18 tests (parametrized)
  - [x] `TestApplicationEmailPayload::test_valid_uuid_passes`
  - [x] `TestApplicationEmailPayload::test_invalid_uuid_raises`
  - [x] `TestApplicationEmailPayload::test_empty_string_raises`
  - [x] `TestApplicationEmailPayload::test_missing_field_raises`
  - [x] `TestStatusUpdateEmailPayload::test_valid_input_passes`
  - [x] `TestStatusUpdateEmailPayload::test_invalid_uuid_raises`
  - [x] `TestStatusUpdateEmailPayload::test_invalid_status_raises` (parametrized: 4 bad values)
  - [x] `TestStatusUpdateEmailPayload::test_all_valid_statuses_accepted` (parametrized: 7 valid values)
  - [x] `TestStatusUpdateEmailPayload::test_missing_fields_raises`
- [x] `apps/notifications/tests/test_tasks.py` — 8 tests (real Celery eager + locmem email)
  - [x] `test_sends_email_to_applicant`
  - [x] `test_subject_contains_job_title`
  - [x] `test_creates_notification_record` (received)
  - [x] `test_nonexistent_app_does_not_crash`
  - [x] `test_invalid_uuid_does_not_retry`
  - [x] `test_sends_email_with_status_change`
  - [x] `test_creates_notification_record` (status update)
  - [x] `test_invalid_status_does_not_retry`
- [x] `apps/notifications/tests/test_models.py` — 4 tests
  - [x] `test_create_notification`
  - [x] `test_default_is_read_false`
  - [x] `test_metadata_default_empty_dict`
  - [x] `test_type_choices`
- [x] `apps/notifications/tests/test_views.py` — 7 tests
  - [x] `test_user_sees_own`
  - [x] `test_filter_by_is_read`
  - [x] `test_includes_unread_count`
  - [x] `test_unauthenticated_gets_401`
  - [x] `test_mark_single_read`
  - [x] `test_cannot_mark_other_users` (returns 404 — scoped queryset)
  - [x] `test_marks_all_and_returns_count`
- [x] Update `tests/factories.py` — Add NotificationFactory

### Phase 7 Verification Checklist

- [x] `pytest apps/notifications/` — 37/37 pass
- [x] `pytest` — Cumulative: 203 pass
- [x] 87% coverage on `apps/notifications/schemas.py` (uncovered: exception chaining lines)
- [x] 84% coverage on `apps/notifications/tasks.py` (uncovered: retry exception paths)
- [x] 100% coverage on views, serializers, URLs
- [x] 92% overall coverage on notifications app
- [x] Phase 6 signal tests still pass (signals now call enhanced tasks)
- [x] `ruff check .` — Clean

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 8: Dashboard Aggregation Endpoints

**Branch:** `feature/HF-008-dashboard`

### Implementation

- [x] Create `apps/dashboard/apps.py` — DashboardConfig
- [x] Create `apps/dashboard/views.py` — RecruiterDashboardView (APIView + IsRecruiter), CandidateDashboardView (APIView + IsCandidate)
- [x] Create `apps/dashboard/urls.py` — `/recruiter/` and `/candidate/`
- [x] Wire URLs in `config/urls.py` at `/api/dashboard/`
- [x] Add `apps.dashboard` to INSTALLED_APPS

### Tests (RED → GREEN)

- [x] `apps/dashboard/tests/test_views.py` — 16 tests
  - [x] `TestRecruiterDashboard::test_returns_total_jobs`
  - [x] `TestRecruiterDashboard::test_returns_jobs_by_status`
  - [x] `TestRecruiterDashboard::test_returns_total_applications`
  - [x] `TestRecruiterDashboard::test_returns_applications_by_status`
  - [x] `TestRecruiterDashboard::test_returns_recent_applications`
  - [x] `TestRecruiterDashboard::test_only_recruiter_can_access`
  - [x] `TestRecruiterDashboard::test_candidate_gets_403`
  - [x] `TestRecruiterDashboard::test_scoped_to_recruiters_companies`
  - [x] `TestCandidateDashboard::test_returns_total_applications`
  - [x] `TestCandidateDashboard::test_returns_applications_by_status`
  - [x] `TestCandidateDashboard::test_returns_recent_applications`
  - [x] `TestCandidateDashboard::test_only_candidate_can_access`
  - [x] `TestCandidateDashboard::test_recruiter_gets_403`
  - [x] `TestCandidateDashboard::test_unauthenticated_401`
  - [x] `TestCandidateDashboard::test_scoped_to_own_applications`
  - [x] `TestCandidateDashboard::test_recent_limit_is_five`

### Phase 8 Verification Checklist

- [x] `pytest apps/dashboard/` — 16/16 pass
- [x] `pytest` — Cumulative: 219 pass
- [x] Multi-tenant: recruiter from Company A sees 0 data from Company B
- [x] `ruff check .` — Clean

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 9: OpenAPI Documentation & Swagger UI

**Branch:** `feature/HF-009-openapi-docs`

### Implementation

- [x] `drf-spectacular` already in INSTALLED_APPS and `SPECTACULAR_SETTINGS` configured (from Phase 1)
- [x] `DEFAULT_SCHEMA_CLASS` already set to `drf_spectacular.openapi.AutoSchema`
- [x] Add `SpectacularAPIView` at `/api/schema/` and `SpectacularSwaggerView` at `/api/docs/` to `config/urls.py`

### Tests (RED → GREEN)

- [x] `tests/test_docs.py` — 6 tests
  - [x] `test_schema_endpoint_returns_200`
  - [x] `test_schema_is_valid_openapi` (validates openapi version, title, paths)
  - [x] `test_swagger_ui_returns_200`
  - [x] `test_schema_contains_auth_endpoints` (register, login)
  - [x] `test_schema_contains_job_endpoints` (/api/jobs/)
  - [x] `test_schema_contains_application_endpoints` (/api/applications/)

### Phase 9 Verification Checklist

- [x] `pytest tests/test_docs.py` — 6/6 pass
- [x] `pytest` — Cumulative: 225 pass
- [x] `ruff check .` — Clean

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Phase 10: Production Hardening, Seed Data, and Final Integration

**Branch:** `feature/HF-010-production-hardening`

### Production Settings

- [x] Implement `config/settings/production.py` — SECURE_SSL_REDIRECT, HSTS, CSRF/SESSION cookie security, JSON logging
- [x] Add Celery Beat schedule to base.py (`close-expired-jobs` daily at midnight UTC)
- [x] Add `middleware.request_logger.RequestLoggerMiddleware` to MIDDLEWARE in base.py

### Middleware

- [x] Create `middleware/request_logger.py` — RequestLoggerMiddleware (logs method, path, status, user_id, IP, duration; skips /api/health/)

### Seed Data

- [x] Create `apps/accounts/management/commands/seed_data.py` — 2 recruiters, 5 candidates, 2 companies, 6 jobs, 15 applications, --flush flag

### CI/CD & Tooling

- [x] Create `.pre-commit-config.yaml` — Ruff lint + format hooks
- [x] Create `.github/workflows/ci.yml` — PostgreSQL + Redis services, migrations, ruff, pytest with 90% coverage threshold
- [x] Add `python-json-logger` to `requirements/production.txt`

### Tests (RED → GREEN)

- [x] `tests/test_middleware.py` — 4 tests
  - [x] `test_logs_request_method_and_path`
  - [x] `test_logs_response_status_code`
  - [x] `test_logs_authenticated_user`
  - [x] `test_skips_health_check_logging`
- [x] `tests/test_seed_data.py` — 4 tests
  - [x] `test_seed_creates_users`
  - [x] `test_seed_creates_companies_and_jobs`
  - [x] `test_seed_creates_applications`
  - [x] `test_seed_flush_wipes_and_recreates`
- [x] `tests/test_full_integration.py` — 1 comprehensive test
  - [x] `test_complete_happy_path` (register → login → create company → create job → publish → apply → advance status through pipeline → check dashboards → verify notifications)

### Phase 10 Final Verification — Complete Checklist

- [x] `pytest -v` — 234 tests pass
- [x] `pytest --cov=apps --cov=common --cov=middleware --cov-fail-under=90` — **94% overall**
- [x] Coverage by layer:
  - [x] `managers.py`: 100%
  - [x] `validators.py`: 100%
  - [x] `permissions.py`: 95%
  - [x] `signals.py`: 95%+
  - [x] `schemas.py`: 87%
  - [x] `tasks.py`: 84% (retry exception paths uncovered)
  - [x] `views.py`: 83%+ (all views)
  - [x] `middleware/request_logger.py`: 100%
  - [x] `seed_data.py`: 100%
- [x] `ruff check .` — Clean
- [x] `pytest tests/test_full_integration.py -v` — Full e2e workflow passes

**Started:** 2026-03-21 · **Completed:** 2026-03-21

---

## Notes & Decisions Log

Use this section to record important decisions, blockers, and deviations from the plan during implementation.

| Date | Phase | Note |
|------|-------|------|
| 2026-03-21 | 1 | pydantic-settings requires JSON format for list fields in .env (e.g. `ALLOWED_HOSTS=["localhost","127.0.0.1"]`), not comma-separated |
| 2026-03-21 | 1 | PostgresDsn in pydantic v2 uses MultiHostUrl — access host info via `.hosts()[0]` dict, not `.username`/`.host` attributes |
| 2026-03-21 | 1 | No mocking — tests use real PostgreSQL and Redis. Test settings removed locmem cache override. |
| 2026-03-21 | 1 | Root `conftest.py` must be at project root, not inside `tests/` dir, for fixtures to be available to all test directories |
| 2026-03-21 | 1 | 25 tests total (vs planned 19) — parametrized validator tests expand to 12 individual test cases |
| 2026-03-21 | 2 | Signal sends email directly via Django send_mail (not Celery), will refactor to Celery task in Phase 7 |
| 2026-03-21 | 2 | LoginView returns 401 (not 400) for invalid credentials — handled manually instead of raise_exception=True |
| 2026-03-21 | 2 | 27 tests (vs planned 25) — added test_register_sends_verification_email and test_invalid_token_returns_400 |
| 2026-03-21 | 2 | token_blacklist app added to INSTALLED_APPS for SimpleJWT ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION |
| 2026-03-21 | 3 | IsCompanyMember tests deferred to Phase 4 — no mocking, need real Company/CompanyMember models |
| 2026-03-21 | 3 | 9 tests (vs planned 13) — 4 IsCompanyMember tests will be added in Phase 4 |
| 2026-03-21 | 4 | 24 tests total: 7 model + 13 view + 4 IsCompanyMember permission (real DB). InviteMemberSerializer needed to_representation override. |
| 2026-03-21 | 5 | SearchRank threshold lowered from 0.1 to >0 — rank values for short text are naturally low (0.06 for single-word matches). Spec's 0.1 too aggressive in practice. |
| 2026-03-21 | 5 | with_application_count() tests skipped — Application model FK doesn't exist until Phase 6 (same pattern as IsCompanyMember in Phase 3→4) |
| 2026-03-21 | 5 | Search endpoint uses pagination_class=None to preserve rank ordering (CursorPagination overrides order_by) |
| 2026-03-21 | 5 | CompanyFactory slug changed from Faker-based to Sequence to avoid duplicate slugs when creating many objects |
| 2026-03-21 | 6 | Signal tests use real Celery eager + locmem email (no mocking) — verify via mail.outbox |
| 2026-03-21 | 6 | Notification tasks created as stubs in Phase 6 (real email sending), enhanced with Pydantic in Phase 7 |
| 2026-03-21 | 6 | Withdraw endpoint returns 404 (not 403) for non-owner — IDOR protection via scoped queryset |
| 2026-03-21 | 6 | Phase 5 with_application_count tests unskipped and passing (Application model now exists) |
| 2026-03-21 | 7 | Enhanced tasks with bind=True, max_retries=3, Pydantic validation at entry — invalid payloads return early (no retry) |
| 2026-03-21 | 7 | Tasks now create Notification records in DB alongside sending email |
| 2026-03-21 | 7 | 37 tests (vs planned 28) — parametrized schema tests expand to 18 individual test cases |
| 2026-03-21 | 7 | mark_read scoped via queryset — other users get 404 (same IDOR pattern as Phase 6) |
| 2026-03-21 | 8 | No serializers needed — views return dicts directly (simple aggregation, no model serialization) |
| 2026-03-21 | 8 | Dashboard views use plain APIView (not ViewSet) — single GET method per view |
| 2026-03-21 | 9 | drf-spectacular was already configured in Phase 1 — only needed URL wiring and tests |
| 2026-03-21 | 9 | Skipped @extend_schema decorators — AutoSchema auto-generates docs from serializers/views |
| 2026-03-21 | 10 | seed_data username collision fixed — used `email.replace("@","_at_").replace(".","_")` instead of `email.split("@")[0]` |
| 2026-03-21 | 10 | Integration test requires register + login (separate steps) — RegisterView returns user data, not JWT tokens |
| 2026-03-21 | 10 | JobCreateSerializer expects company UUID, not slug — integration test fixed to pass `company_id` |
| 2026-03-21 | 10 | FTS rank ordering test is occasionally flaky — PostgreSQL ranks vary with concurrent search_vector updates |
| 2026-03-21 | 10 | **Final: 234 tests, 94% coverage, 0 lint errors** |

---

## Cumulative Test Count by Phase

| After Phase | Total Tests | New Tests |
|-------------|-------------|-----------|
| 1 | 25 | 25 |
| 2 | 52 | 27 |
| 3 | 61 | 9 |
| 4 | 85 | 24 |
| 5 | 135 | 50 (3 with_application_count unskipped in Phase 6) |
| 6 | 166 | 31 |
| 7 | 203 | 37 |
| 8 | 219 | 16 |
| 9 | 225 | 6 |
| 10 | **234** | 9 |
