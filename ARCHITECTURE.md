# HireFlow — Architecture Document

> Multi-Tenant Job Board API · Django 5.0 + DRF + Celery + Redis + PostgreSQL + Docker
>
> Last updated: 2026-03-21

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Database Design](#2-database-design)
3. [API Contract](#3-api-contract)
4. [Celery Task Architecture](#4-celery-task-architecture)
5. [Pydantic Integration](#5-pydantic-integration)
6. [Security Checklist](#6-security-checklist)
7. [Architecture Decision Records](#7-architecture-decision-records)

---

## 1. System Architecture Overview

### 1.1 Component Diagram

```
                          ┌──────────────────────────────────────────────────────┐
                          │                    Docker Network                    │
                          │                                                      │
  ┌──────────┐    HTTPS   │  ┌─────────────────────────────────────────────┐     │
  │  Client   │───────────┼─▶│          Django App (Gunicorn)              │     │
  │ (Browser/ │   :8000   │  │                                             │     │
  │  Mobile)  │◀──────────┼──│  ┌─────────┐  ┌──────┐  ┌──────────────┐    │     │
  └──────────┘            │  │  │   DRF   │  │Middl-│  │  SimpleJWT   │    │     │
                          │  │  │ Views/  │  │ware  │  │  Auth Layer  │    │     │
                          │  │  │Serializ.│  │Stack │  └──────────────┘    │     │
                          │  │  └────┬────┘  └───┬──┘                      │     │
                          │  │       │           │                         │     │
                          │  │       ▼           ▼                         │     │
                          │  │  ┌─────────────────────────┐                │     │
                          │  │  │     Django ORM Layer     │               │     │
                          │  │  │  (Models + Managers)     │               │     │
                          │  │  └────────┬────────────────┘                │     │
                          │  └───────────┼─────────────────────────────────┘     │
                          │              │                                       │
                          │     ┌────────┴────────┐                              │
                          │     ▼                  ▼                             │
                          │  ┌──────────┐   ┌───────────┐                        │
                          │  │PostgreSQL│   │   Redis    │                       │
                          │  │  :5432   │   │   :6379   │                        │
                          │  │          │   │           │                        │
                          │  │• Tables  │   │• Cache    │                        │
                          │  │• Indexes │   │• Broker   │                        │
                          │  │• FTS     │   │• Sessions │                        │
                          │  └──────────┘   └─────┬─────┘                        │
                          │                       │                              │
                          │              ┌────────┴────────┐                     │
                          │              ▼                  ▼                    │
                          │  ┌──────────────────┐  ┌──────────────────┐          │
                          │  │  Celery Worker   │  │   Celery Beat    │          │
                          │  │                  │  │                  │          │
                          │  │• Email tasks     │  │• close_expired   │          │
                          │  │• Notifications   │  │  _jobs (daily)   │          │
                          │  │• Retries (3x)    │  │• DB Scheduler    │          │
                          │  └──────────────────┘  └──────────────────┘          │
                          │                                                      │
                          └──────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

| Component | Technology | Responsibility |
|-----------|-----------|---------------|
| **Web Server** | Django 5.0 + Gunicorn | HTTP request handling, routing, serialization, authentication |
| **REST Layer** | Django REST Framework 3.15 | Viewsets, serializers, permissions, throttling, pagination |
| **Auth** | SimpleJWT 5.3 | JWT access/refresh token issuance and verification |
| **Database** | PostgreSQL 15 | Primary data store, full-text search (GIN indexes), relational integrity |
| **Cache / Broker** | Redis 7 | Response caching (published jobs), Celery message broker, rate-limit counters |
| **Task Worker** | Celery 5.3 | Async email delivery, notification creation, background processing |
| **Task Scheduler** | Celery Beat + django-celery-beat | Cron-like periodic tasks stored in PostgreSQL via `DatabaseScheduler` |
| **API Docs** | drf-spectacular 0.27 | Auto-generated OpenAPI 3.0 schema, Swagger UI |

### 1.3 Request Lifecycle — "Candidate Submits an Application"

This walkthrough traces a `POST /api/applications/` request from the client to the final response, then through the async task pipeline.

```
Step 1: HTTP Request
    Client sends POST /api/applications/ with:
    - Authorization: Bearer <access_token>
    - Body: { job: <uuid>, resume: <file>, cover_letter: "..." }

Step 2: Middleware Stack (in order)
    1. SecurityMiddleware          → HTTPS redirect, HSTS headers
    2. CorsMiddleware              → Validate Origin header
    3. SessionMiddleware           → (unused for JWT, but required by admin)
    4. CommonMiddleware            → URL normalization
    5. RequestLoggerMiddleware     → Log method, path, user, response time
    6. AuthenticationMiddleware    → Attach user to request (session-based, for admin)

Step 3: JWT Authentication (DRF layer, not middleware)
    SimpleJWT's JWTAuthentication class:
    1. Extracts token from Authorization header
    2. Decodes and verifies signature (HS256 with SECRET_KEY)
    3. Checks exp claim → 401 if expired
    4. Looks up user by token's user_id claim
    5. Sets request.user = <User instance>

Step 4: Permission Check
    IsAuthenticated + IsCandidate:
    1. request.user.is_authenticated → True
    2. request.user.role == "candidate" → True
    3. Proceed to view logic

Step 5: Serializer Validation (ApplicationCreateSerializer)
    1. Validate job UUID exists and status == "published"
    2. Validate deadline has not passed
    3. Validate unique_together(job, applicant) — no duplicate applications
    4. Validate resume file: size ≤ 5MB, type in [pdf, doc, docx]
    5. Validate expected_salary is positive if provided
    6. Set applicant = request.user (from context, not user input)

Step 6: Database Write
    1. BEGIN transaction
    2. INSERT INTO applications_application (...)
    3. COMMIT
    → Application row created with status = "applied"

Step 7: Signal Fires (post_save)
    applications.signals.on_application_created detects created=True:
    1. Calls send_application_received_email.delay(str(instance.id))
    2. This serializes the task and pushes it to Redis broker
    3. Returns immediately (non-blocking)

Step 8: HTTP Response (synchronous — complete)
    201 Created
    {
      "id": "a1b2c3d4-...",
      "job": "f5e6d7c8-...",
      "status": "applied",
      "created_at": "2026-03-21T10:30:00Z"
    }
    Total response time: ~50-100ms

Step 9: Celery Worker Picks Up Task (asynchronous)
    1. Worker deserializes task from Redis queue
    2. Loads Application with select_related("applicant", "job__company")
    3. Calls django.core.mail.send_mail(...)
    4. If SMTP fails → retry up to 3 times with 60s delay
    5. Task result stored in django-celery-results table
```

---

## 2. Database Design

### 2.1 Entity-Relationship Diagram

```
  ┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
  │     User     │       │  CompanyMember   │       │   Company    │
  │──────────────│       │──────────────────│       │──────────────│
  │ id (UUID PK) │◀──┐   │ id (UUID PK)     │   ┌──▶│ id (UUID PK) │
  │ email        │   └───│ user_id (FK)     │   │   │ name         │
  │ username     │       │ company_id (FK)──┼───┘   │ slug (UQ)    │
  │ role         │       │ role             │       │ is_verified  │
  │ password     │       │ created_at       │       │ created_at   │
  │ phone        │       │ updated_at       │       │ updated_at   │
  │ avatar       │       └──────────────────┘       └──────┬───────┘
  │ is_email_    │                                         │
  │  verified    │       ┌──────────────────┐              │
  │ created_at   │       │       Job        │              │
  │ updated_at   │       │──────────────────│              │
  └──────┬───────┘       │ id (UUID PK)     │◀─────────────┘
         │               │ company_id (FK)  │         company.jobs
         │               │ posted_by_id(FK)─┼──── User (SET_NULL)
         │               │ title            │
         │               │ slug (UQ)        │
         │               │ description      │
         │               │ requirements     │
         │               │ skills (JSON)    │
         │               │ status           │
         │               │ search_vector    │
         │               │ deadline         │
         │               │ created_at       │
         │               └──────┬───────────┘
         │                      │
         │     ┌────────────────┘ job.applications
         │     ▼
         │  ┌──────────────────┐
         │  │  Application     │
         │  │──────────────────│
         └─▶│ id (UUID PK)     │
   user.    │ job_id (FK)      │
   applica- │ applicant_id(FK) │
   tions    │ resume (file)    │
            │ cover_letter     │
            │ status           │
            │ recruiter_notes  │
            │ created_at       │
            └──────────────────┘
                    │
                    │ (logically linked via metadata)
                    ▼
            ┌──────────────────┐
            │  Notification    │
            │──────────────────│
            │ id (UUID PK)     │
            │ user_id (FK)     │◀── User.notifications
            │ type             │
            │ title            │
            │ message          │
            │ is_read          │
            │ metadata (JSON)  │
            │ created_at       │
            └──────────────────┘
```

### 2.2 Complete Table Definitions

#### `accounts_user`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK, default `uuid4`, not editable | Inherited from `TimeStampedModel` |
| `password` | `VARCHAR(128)` | NOT NULL | Django's hashed password (PBKDF2-SHA256) |
| `last_login` | `TIMESTAMP WITH TZ` | NULL | Inherited from `AbstractUser` |
| `is_superuser` | `BOOLEAN` | NOT NULL, default `false` | Django admin superuser flag |
| `username` | `VARCHAR(150)` | UNIQUE, NOT NULL | Required by `AbstractUser`; secondary identifier |
| `first_name` | `VARCHAR(150)` | blank allowed | Inherited from `AbstractUser` |
| `last_name` | `VARCHAR(150)` | blank allowed | Inherited from `AbstractUser` |
| `email` | `VARCHAR(254)` | UNIQUE, NOT NULL | Primary login identifier (`USERNAME_FIELD`) |
| `is_staff` | `BOOLEAN` | NOT NULL, default `false` | Django admin access |
| `is_active` | `BOOLEAN` | NOT NULL, default `true` | Soft-disable account without deleting |
| `date_joined` | `TIMESTAMP WITH TZ` | NOT NULL | Inherited from `AbstractUser` |
| `role` | `VARCHAR(20)` | NOT NULL, default `"candidate"` | Enum: `candidate`, `recruiter`, `admin` |
| `phone` | `VARCHAR(20)` | blank allowed | Optional contact number |
| `avatar` | `VARCHAR(100)` | NULL | File path in `avatars/` media directory |
| `is_email_verified` | `BOOLEAN` | NOT NULL, default `false` | Flipped after email verification flow |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | From `TimeStampedModel` |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | From `TimeStampedModel` |

**Indexes:**
- `PRIMARY KEY (id)` — UUID lookup
- `UNIQUE (email)` — login uniqueness, used in every auth query
- `UNIQUE (username)` — Django requirement

---

#### `companies_company`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | |
| `name` | `VARCHAR(255)` | NOT NULL | Display name |
| `slug` | `VARCHAR(50)` | UNIQUE, NOT NULL | URL-safe identifier for API routes |
| `description` | `TEXT` | blank allowed | Company bio / about text |
| `website` | `VARCHAR(200)` | blank allowed | Validated URL |
| `logo` | `VARCHAR(100)` | NULL | File path in `logos/` media directory |
| `size` | `VARCHAR(20)` | blank allowed | Enum: `1-10`, `11-50`, `51-200`, `201-500`, `500+` |
| `industry` | `VARCHAR(100)` | blank allowed | Free-text industry category |
| `location` | `VARCHAR(255)` | blank allowed | HQ location |
| `is_verified` | `BOOLEAN` | NOT NULL, default `false` | Admin-verified flag; unverified companies hidden from public listing |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |

**Indexes:**
- `PRIMARY KEY (id)`
- `UNIQUE (slug)` — used in every company detail/update URL lookup

---

#### `companies_companymember`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | FK → `accounts_user.id`, ON DELETE CASCADE | |
| `company_id` | `UUID` | FK → `companies_company.id`, ON DELETE CASCADE | |
| `role` | `VARCHAR(20)` | NOT NULL, default `"recruiter"` | Enum: `owner`, `recruiter` |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |

**Indexes:**
- `PRIMARY KEY (id)`
- `UNIQUE (user_id, company_id)` — one membership per user per company
- `INDEX (company_id)` — FK lookup when listing company members
- `INDEX (user_id)` — FK lookup when listing a user's companies

**Why a through model?** The `CompanyMember` table adds a `role` column to the many-to-many relationship. This enables ownership semantics: only `owner` can update company profile, invite members, or transfer ownership. Without a through model, all members would have equal privilege.

---

#### `jobs_job`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | |
| `company_id` | `UUID` | FK → `companies_company.id`, ON DELETE CASCADE | Tenant scoping |
| `posted_by_id` | `UUID` | FK → `accounts_user.id`, ON DELETE SET NULL, NULL | Preserves job if recruiter account deleted |
| `title` | `VARCHAR(255)` | NOT NULL | |
| `slug` | `VARCHAR(50)` | UNIQUE, NOT NULL | URL identifier |
| `description` | `TEXT` | NOT NULL | Full job description (Markdown supported) |
| `requirements` | `TEXT` | NOT NULL | |
| `responsibilities` | `TEXT` | blank allowed | |
| `skills` | `JSONB` | NOT NULL, default `[]` | Array of strings: `["Python", "Django"]` |
| `job_type` | `VARCHAR(20)` | NOT NULL | Enum: `full_time`, `part_time`, `contract`, `internship`, `remote` |
| `experience_level` | `VARCHAR(20)` | NOT NULL | Enum: `junior`, `mid`, `senior`, `lead` |
| `location` | `VARCHAR(255)` | blank allowed | |
| `is_remote` | `BOOLEAN` | NOT NULL, default `false` | |
| `salary_min` | `INTEGER` | NULL, CHECK ≥ 0 | In `currency` units |
| `salary_max` | `INTEGER` | NULL, CHECK ≥ 0 | Must be ≥ `salary_min` (validated in serializer) |
| `currency` | `VARCHAR(10)` | NOT NULL, default `"USD"` | ISO 4217 code |
| `status` | `VARCHAR(20)` | NOT NULL, default `"draft"` | Enum: `draft`, `published`, `closed` |
| `deadline` | `DATE` | NULL | Jobs with past deadlines are auto-closed by Celery Beat |
| `views_count` | `INTEGER` | NOT NULL, default `0`, CHECK ≥ 0 | Atomically incremented via `F("views_count") + 1` on detail view (see Section 3.4) |
| `search_vector` | `TSVECTOR` | NULL | Auto-populated from `title` + `description` via signal |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |

**Indexes:**

| Index | Type | Columns | Rationale |
|-------|------|---------|-----------|
| PK | B-tree | `(id)` | Primary key lookup |
| Unique | B-tree | `(slug)` | URL-based lookups: `GET /api/jobs/{slug}/` |
| GIN | GIN | `(search_vector)` | Full-text search on `GET /api/jobs/search/?q=...`. GIN indexes are optimized for `tsvector` containment queries and support ranking |
| Composite | B-tree | `(status, created_at)` | Filters published jobs sorted by recency — the most common query pattern for the public job listing |
| Composite | B-tree | `(company_id, status)` | Recruiter dashboard: "show me all my company's jobs by status" |

---

#### `applications_application`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | |
| `job_id` | `UUID` | FK → `jobs_job.id`, ON DELETE CASCADE | |
| `applicant_id` | `UUID` | FK → `accounts_user.id`, ON DELETE CASCADE | |
| `resume` | `VARCHAR(100)` | NOT NULL | File path in `resumes/YYYY/MM/` |
| `cover_letter` | `TEXT` | blank allowed | |
| `status` | `VARCHAR(20)` | NOT NULL, default `"applied"` | Enum: `applied`, `reviewing`, `shortlisted`, `interview`, `offered`, `rejected`, `withdrawn` |
| `recruiter_notes` | `TEXT` | blank allowed | Internal only — never serialized for candidate-facing endpoints |
| `expected_salary` | `INTEGER` | NULL, CHECK ≥ 0 | |
| `available_from` | `DATE` | NULL | Earliest start date |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |

**Indexes:**

| Index | Type | Columns | Rationale |
|-------|------|---------|-----------|
| PK | B-tree | `(id)` | Primary key |
| Unique | B-tree | `(job_id, applicant_id)` | Enforces one application per candidate per job at the DB level |
| Composite | B-tree | `(status, created_at)` | Recruiter filtering: "show all shortlisted applications, newest first" |
| Composite | B-tree | `(job_id, status)` | Application list for a specific job filtered by status (recruiter view) |

---

#### `notifications_notification`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | FK → `accounts_user.id`, ON DELETE CASCADE | |
| `type` | `VARCHAR(50)` | NOT NULL | Enum: `application_received`, `status_changed`, `job_expiring` |
| `title` | `VARCHAR(255)` | NOT NULL | Human-readable notification title |
| `message` | `TEXT` | NOT NULL | Notification body |
| `is_read` | `BOOLEAN` | NOT NULL, default `false` | |
| `metadata` | `JSONB` | NOT NULL, default `{}` | Structured context: `{"job_id": "...", "application_id": "..."}` |
| `created_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |
| `updated_at` | `TIMESTAMP WITH TZ` | NOT NULL, auto | |

**Indexes:**
- `PRIMARY KEY (id)`
- `INDEX (user_id)` — FK lookup; every notification query is scoped to a user
- `INDEX (created_at DESC)` — ordering; notifications are always displayed newest-first

---

### 2.3 Non-Obvious Design Decisions

**UUID Primary Keys (`uuid.uuid4`)**
Sequential integer IDs leak information: a competitor can estimate your total job count by creating a listing and reading the ID. UUIDs prevent enumeration attacks and are safe to expose in URLs. The tradeoff is slightly larger index sizes (16 bytes vs 4 bytes) and no natural ordering — mitigated by `created_at` columns on every table.

**JSONField for `skills`**
Skills are stored as a flat JSON array (`["Python", "Django", "PostgreSQL"]`) rather than a normalized many-to-many through a `Skill` table. Reasons:
- Skills are display-only — there's no skill detail page or skill-centric querying beyond `__icontains` filtering.
- Avoids a join table and an extra model for what is essentially a tag list.
- PostgreSQL's `JSONB` supports `@>` containment queries if we need exact-match filtering later.
- Tradeoff: no referential integrity on skill names. Mitigated by serializer validation against an allowed list if needed.

**SearchVectorField**
A dedicated `tsvector` column avoids recomputing the search vector on every query. The GIN index on this column makes full-text search queries O(log n) instead of sequential scans. The vector is populated via a `post_save` signal that combines `title` (weight A, highest priority) and `description` (weight B). This means a search for "Django developer" will rank a job titled "Django Developer" higher than one that merely mentions Django in the description.

**Signal implementation (`apps/jobs/signals.py`):**

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector
from .models import Job


@receiver(post_save, sender=Job)
def update_search_vector(sender, instance, **kwargs):
    """
    Rebuild the search_vector after every save.
    Uses .update() to avoid re-triggering post_save (infinite loop prevention).
    """
    Job.objects.filter(pk=instance.pk).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
        )
    )
```

Register in `apps/jobs/apps.py`:

```python
from django.apps import AppConfig

class JobsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jobs"

    def ready(self):
        import apps.jobs.signals  # noqa: F401
```

**`ON DELETE SET NULL` for `posted_by`**
If a recruiter's account is deleted, their posted jobs should persist (they belong to the company, not the individual). `SET NULL` preserves the job while clearing the now-invalid reference. All other FKs use `CASCADE` because:
- Deleting a company should remove all its jobs (company owns the jobs).
- Deleting a job should remove all its applications (applications are meaningless without the job).
- Deleting a user should remove their applications (the applicant is gone).

---

## 3. API Contract

### 3.1 Standard Response Envelope

All error responses follow a consistent format via a custom exception handler:

```json
{
  "error": "Human-readable error message.",
  "code": "machine_readable_code",
  "details": {}
}
```

All success responses return the resource directly (no wrapping envelope for successful responses — DRF convention).

Paginated list responses use cursor-based pagination:

```json
{
  "next": "https://api.hireflow.io/api/jobs/?cursor=cD0yMDI2LTAz...",
  "previous": null,
  "results": [...]
}
```

---

### 3.2 Authentication Endpoints

#### `POST /api/auth/register/`

Register a new user account.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | `string` | Yes | Valid email, unique |
| `username` | `string` | Yes | 3-150 chars, unique, alphanumeric + `_` |
| `password` | `string` | Yes | Min 8 chars, Django password validators |
| `password_confirm` | `string` | Yes | Must match `password` |
| `first_name` | `string` | No | Max 150 chars |
| `last_name` | `string` | No | Max 150 chars |
| `role` | `string` | No | `"candidate"` (default) or `"recruiter"` |
| `phone` | `string` | No | Max 20 chars |

**Success Response — `201 Created`:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "email": "jane@example.com",
  "username": "janedoe",
  "first_name": "Jane",
  "last_name": "Doe",
  "role": "candidate",
  "is_email_verified": false,
  "created_at": "2026-03-21T10:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Validation error | `{"error": "A user with this email already exists.", "code": "unique", "details": {"email": ["user with this email already exists."]}}` |
| `400` | Password mismatch | `{"error": "Passwords do not match.", "code": "password_mismatch", "details": {}}` |
| `400` | Weak password | `{"error": "This password is too common.", "code": "password_too_common", "details": {}}` |

---

#### `POST /api/auth/login/`

Obtain JWT access and refresh tokens.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | `string` | Yes | Existing user email |
| `password` | `string` | Yes | Correct password |

**Success Response — `200 OK`:**

```json
{
  "access": "eyJhbGciOiJIUzI1NiIs...",
  "refresh": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "email": "jane@example.com",
    "role": "candidate",
    "first_name": "Jane",
    "last_name": "Doe"
  }
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `401` | Invalid credentials | `{"error": "No active account found with the given credentials.", "code": "authentication_failed", "details": {}}` |
| `401` | Inactive account | `{"error": "User account is disabled.", "code": "account_disabled", "details": {}}` |

---

#### `POST /api/auth/token/refresh/`

Refresh an expired access token.

| Field | Details |
|---|---|
| **Auth** | None (refresh token in body) |
| **Permission** | Any |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `refresh` | `string` | Yes | Valid, unexpired refresh token |

**Success Response — `200 OK`:**

```json
{
  "access": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `401` | Expired/invalid refresh token | `{"error": "Token is invalid or expired.", "code": "token_not_valid", "details": {}}` |

---

#### `POST /api/auth/verify-email/`

Verify a user's email address via a one-time token sent to their email.

**Token mechanism:** On registration, a `post_save` signal generates a signed token using Django's `TimestampSigner` and dispatches a Celery task to email it to the user. The token is not stored in the database — it is a stateless HMAC signature that embeds the user ID and a timestamp. Verification decodes the token, checks the signature and expiry, and sets `is_email_verified = True`.

**Token generation and verification (`apps/accounts/tokens.py`):**

```python
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

signer = TimestampSigner(salt="email-verification")

def make_email_verification_token(user_id: str) -> str:
    """Create a signed, timestamped token encoding the user ID."""
    return signer.sign(str(user_id))

def verify_email_token(token: str, max_age_seconds: int = 86400) -> str:
    """
    Verify the token and return the user_id.
    Raises BadSignature or SignatureExpired on failure.
    max_age_seconds: 86400 = 24 hours.
    """
    return signer.unsign(token, max_age=max_age_seconds)
```

**Signal to send verification email on registration (`apps/accounts/signals.py`):**

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings as auth_settings
from .tokens import make_email_verification_token

@receiver(post_save, sender=auth_settings.AUTH_USER_MODEL)
def send_verification_email_on_register(sender, instance, created, **kwargs):
    if created and not instance.is_email_verified:
        from apps.notifications.tasks import send_verification_email
        token = make_email_verification_token(str(instance.id))
        send_verification_email.delay(str(instance.id), token)
```

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `token` | `string` | Yes | Valid HMAC-signed token, not expired (24h TTL) |

**Success Response — `200 OK`:**

```json
{
  "message": "Email verified successfully."
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Invalid signature | `{"error": "Verification token is invalid.", "code": "invalid_token", "details": {}}` |
| `400` | Token expired (>24h) | `{"error": "Verification token has expired. Please request a new one.", "code": "token_expired", "details": {}}` |

---

### 3.3 Company Endpoints

#### `GET /api/companies/`

List all verified companies with pagination.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `cursor` | `string` | Pagination cursor |
| `search` | `string` | Filter by company name (icontains) |
| `industry` | `string` | Filter by industry |

**Success Response — `200 OK`:**

```json
{
  "next": "https://api.hireflow.io/api/companies/?cursor=cD0yMDI2...",
  "previous": null,
  "results": [
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "name": "Acme Corp",
      "slug": "acme-corp",
      "description": "Building the future of widgets.",
      "website": "https://acme.com",
      "logo": "https://api.hireflow.io/media/logos/acme.png",
      "size": "51-200",
      "industry": "Technology",
      "location": "San Francisco, CA",
      "is_verified": true,
      "created_at": "2026-01-15T08:30:00Z"
    }
  ]
}
```

---

#### `POST /api/companies/`

Create a new company. The creating user becomes the `owner` in `CompanyMember`.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Recruiter only (`IsRecruiter`) |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `name` | `string` | Yes | Max 255 chars |
| `slug` | `string` | Yes | Unique, slug format (lowercase, hyphens) |
| `description` | `string` | No | |
| `website` | `string` | No | Valid URL |
| `logo` | `file` | No | Image file (jpg, png), max 2MB |
| `size` | `string` | No | One of: `1-10`, `11-50`, `51-200`, `201-500`, `500+` |
| `industry` | `string` | No | Max 100 chars |
| `location` | `string` | No | Max 255 chars |

**Success Response — `201 Created`:**

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "description": "Building the future of widgets.",
  "website": "https://acme.com",
  "logo": null,
  "size": "51-200",
  "industry": "Technology",
  "location": "San Francisco, CA",
  "is_verified": false,
  "members": [
    {
      "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "email": "recruiter@example.com",
      "role": "owner"
    }
  ],
  "created_at": "2026-03-21T10:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Duplicate slug | `{"error": "Company with this slug already exists.", "code": "unique", "details": {"slug": ["company with this slug already exists."]}}` |
| `401` | Missing/invalid JWT | `{"error": "Authentication credentials were not provided.", "code": "not_authenticated", "details": {}}` |
| `403` | Non-recruiter user | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |

---

#### `GET /api/companies/{slug}/`

Retrieve company detail by slug.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Success Response — `200 OK`:**

```json
{
  "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "description": "Building the future of widgets.",
  "website": "https://acme.com",
  "logo": "https://api.hireflow.io/media/logos/acme.png",
  "size": "51-200",
  "industry": "Technology",
  "location": "San Francisco, CA",
  "is_verified": true,
  "job_count": 12,
  "created_at": "2026-01-15T08:30:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `404` | Company not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `PATCH /api/companies/{slug}/`

Update company details.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Company owner only (`IsCompanyMember` + role=`owner`) |

**Request Body:** Same fields as `POST /api/companies/`, all optional.

**Success Response — `200 OK`:** Updated company object (same shape as detail).

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `401` | Missing JWT | `{"error": "Authentication credentials were not provided.", "code": "not_authenticated", "details": {}}` |
| `403` | Not company owner | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `404` | Company not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `POST /api/companies/{slug}/members/`

Invite a recruiter to the company.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Company owner only |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email` | `string` | Yes | Must be a registered recruiter-role user |
| `role` | `string` | No | `"recruiter"` (default). Cannot assign `"owner"` via this endpoint |

**Success Response — `201 Created`:**

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "user": {
    "id": "d4e5f6a7-b8c9-0123-defa-234567890123",
    "email": "newrecruiter@example.com"
  },
  "company": "acme-corp",
  "role": "recruiter",
  "created_at": "2026-03-21T11:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | User already a member | `{"error": "This user is already a member of this company.", "code": "already_member", "details": {}}` |
| `400` | User not found or not a recruiter | `{"error": "No recruiter found with this email.", "code": "invalid_user", "details": {}}` |
| `403` | Not company owner | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |

---

### 3.4 Job Endpoints

#### `GET /api/jobs/`

List published, non-expired jobs with filtering and cursor-based pagination.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `cursor` | `string` | Pagination cursor (opaque, from `next`/`previous` URLs) |
| `title` | `string` | Filter by title (case-insensitive contains) |
| `location` | `string` | Filter by location (case-insensitive contains) |
| `skill` | `string` | Filter by skill (case-insensitive, matches within JSON array) |
| `salary_min` | `integer` | Minimum salary floor (`salary_min >= value`) |
| `salary_max` | `integer` | Maximum salary ceiling (`salary_max <= value`) |
| `is_remote` | `boolean` | `true` / `false` |
| `job_type` | `string` | Multi-value: `?job_type=full_time&job_type=contract` |
| `experience_level` | `string` | Multi-value: `?experience_level=senior&experience_level=lead` |
| `company` | `UUID` | Filter by company ID |

**Success Response — `200 OK`:**

```json
{
  "next": "https://api.hireflow.io/api/jobs/?cursor=cD0yMDI2LTAz...",
  "previous": null,
  "results": [
    {
      "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
      "title": "Senior Django Developer",
      "slug": "senior-django-developer-acme",
      "company": {
        "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "name": "Acme Corp",
        "slug": "acme-corp",
        "logo": "https://api.hireflow.io/media/logos/acme.png"
      },
      "job_type": "full_time",
      "experience_level": "senior",
      "location": "San Francisco, CA",
      "is_remote": true,
      "salary_min": 150000,
      "salary_max": 200000,
      "currency": "USD",
      "skills": ["Python", "Django", "PostgreSQL", "Redis"],
      "deadline": "2026-04-30",
      "created_at": "2026-03-20T14:00:00Z"
    }
  ]
}
```

---

#### `POST /api/jobs/`

Create a new job listing (in `draft` status by default).

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Recruiter who is a member of the target company (`IsRecruiter` + `IsCompanyMember`) |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `company` | `UUID` | Yes | Must be a company the user is a member of |
| `title` | `string` | Yes | Max 255 chars |
| `slug` | `string` | Yes | Unique, slug format |
| `description` | `string` | Yes | Non-empty |
| `requirements` | `string` | Yes | Non-empty |
| `responsibilities` | `string` | No | |
| `skills` | `array[string]` | No | Default `[]`. Each skill: max 50 chars |
| `job_type` | `string` | Yes | One of: `full_time`, `part_time`, `contract`, `internship`, `remote` |
| `experience_level` | `string` | Yes | One of: `junior`, `mid`, `senior`, `lead` |
| `location` | `string` | No | Max 255 chars |
| `is_remote` | `boolean` | No | Default `false` |
| `salary_min` | `integer` | No | Positive integer |
| `salary_max` | `integer` | No | Positive integer, must be ≥ `salary_min` |
| `currency` | `string` | No | Max 10 chars, default `"USD"` |
| `deadline` | `date` | No | Must be in the future (`YYYY-MM-DD`) |

**Success Response — `201 Created`:**

```json
{
  "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
  "company": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "posted_by": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Senior Django Developer",
  "slug": "senior-django-developer-acme",
  "description": "We are looking for...",
  "requirements": "5+ years of Django...",
  "responsibilities": "",
  "skills": ["Python", "Django", "PostgreSQL"],
  "job_type": "full_time",
  "experience_level": "senior",
  "location": "San Francisco, CA",
  "is_remote": true,
  "salary_min": 150000,
  "salary_max": 200000,
  "currency": "USD",
  "status": "draft",
  "deadline": "2026-04-30",
  "views_count": 0,
  "created_at": "2026-03-21T10:00:00Z",
  "updated_at": "2026-03-21T10:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | salary_max < salary_min | `{"error": "Maximum salary must be greater than or equal to minimum salary.", "code": "invalid_salary_range", "details": {}}` |
| `400` | Deadline in the past | `{"error": "Deadline must be a future date.", "code": "invalid_deadline", "details": {}}` |
| `400` | Duplicate slug | `{"error": "Job with this slug already exists.", "code": "unique", "details": {"slug": ["job with this slug already exists."]}}` |
| `401` | Missing JWT | `{"error": "Authentication credentials were not provided.", "code": "not_authenticated", "details": {}}` |
| `403` | Not a company member | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |

---

#### `GET /api/jobs/{slug}/`

Retrieve a single job by slug. Increments `views_count` atomically using Django's `F()` expression to avoid race conditions under concurrent requests.

**Atomic view count implementation (in the viewset's `retrieve` method):**

```python
from django.db.models import F

def retrieve(self, request, *args, **kwargs):
    instance = self.get_object()
    # Atomic increment — no read-modify-write race condition.
    # F("views_count") + 1 translates to: UPDATE jobs_job SET views_count = views_count + 1
    Job.objects.filter(pk=instance.pk).update(views_count=F("views_count") + 1)
    instance.refresh_from_db(fields=["views_count"])
    serializer = self.get_serializer(instance)
    return Response(serializer.data)
```

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public). Only published jobs are accessible to anonymous users. Drafts visible to company members only |

**Success Response — `200 OK`:**

```json
{
  "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
  "title": "Senior Django Developer",
  "slug": "senior-django-developer-acme",
  "company": {
    "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "name": "Acme Corp",
    "slug": "acme-corp",
    "logo": "https://api.hireflow.io/media/logos/acme.png",
    "is_verified": true
  },
  "posted_by": {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "first_name": "Jane",
    "last_name": "Doe"
  },
  "description": "We are looking for a senior Django developer...",
  "requirements": "5+ years of experience with Django...",
  "responsibilities": "Design and build APIs...",
  "skills": ["Python", "Django", "PostgreSQL", "Redis"],
  "job_type": "full_time",
  "experience_level": "senior",
  "location": "San Francisco, CA",
  "is_remote": true,
  "salary_min": 150000,
  "salary_max": 200000,
  "currency": "USD",
  "status": "published",
  "deadline": "2026-04-30",
  "views_count": 342,
  "application_count": 28,
  "created_at": "2026-03-20T14:00:00Z",
  "updated_at": "2026-03-21T09:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `404` | Job not found or not published | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `PATCH /api/jobs/{slug}/`

Update a job listing.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Company member only (`IsCompanyMember`) |

**Request Body:** Same fields as `POST /api/jobs/`, all optional. `company` and `posted_by` are read-only.

**Success Response — `200 OK`:** Updated job object.

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Validation error | (same patterns as create) |
| `401` | Missing JWT | `{"error": "Authentication credentials were not provided.", "code": "not_authenticated", "details": {}}` |
| `403` | Not a company member | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `404` | Job not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `DELETE /api/jobs/{slug}/`

Delete a job listing (soft delete recommended — sets `is_deleted=True`).

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Company member only (`IsCompanyMember`) |

**Success Response — `204 No Content`:** Empty body.

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `401` | Missing JWT | `{"error": "Authentication credentials were not provided.", "code": "not_authenticated", "details": {}}` |
| `403` | Not a company member | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `404` | Job not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `POST /api/jobs/{slug}/publish/`

Transition a job from `draft` → `published`.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Company member only |

**Request Body:** None.

**Validation:** Job must be in `draft` status. Required fields must be populated (title, description, requirements, job_type, experience_level).

**Success Response — `200 OK`:**

```json
{
  "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
  "status": "published",
  "message": "Job published successfully."
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Job not in draft status | `{"error": "Only draft jobs can be published.", "code": "invalid_status_transition", "details": {}}` |
| `403` | Not a company member | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |

---

#### `POST /api/jobs/{slug}/close/`

Transition a job from `published` → `closed`.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Company member only |

**Request Body:** None.

**Success Response — `200 OK`:**

```json
{
  "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
  "status": "closed",
  "message": "Job closed successfully."
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Job not in published status | `{"error": "Only published jobs can be closed.", "code": "invalid_status_transition", "details": {}}` |
| `403` | Not a company member | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |

---

#### `GET /api/jobs/search/?q=django`

Full-text search across published jobs using PostgreSQL `tsvector`.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any (public) |

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | `string` | Yes | Search query. Supports PostgreSQL FTS syntax (e.g., `"django & python"`) |
| `cursor` | `string` | No | Pagination cursor |

**Success Response — `200 OK`:**

```json
{
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
      "title": "Senior Django Developer",
      "slug": "senior-django-developer-acme",
      "company": {
        "name": "Acme Corp",
        "slug": "acme-corp"
      },
      "location": "San Francisco, CA",
      "is_remote": true,
      "salary_min": 150000,
      "salary_max": 200000,
      "currency": "USD",
      "rank": 0.6079
    }
  ]
}
```

Results are ordered by search relevance (`rank` descending). Minimum rank threshold: `0.1`.

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Missing `q` parameter | `{"error": "Search query parameter 'q' is required.", "code": "missing_query", "details": {}}` |

---

### 3.5 Application Endpoints

#### `POST /api/applications/`

Submit a job application.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Candidate only. Rate-limited: 10 requests/hour per user |

**Request Body (multipart/form-data):**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `job` | `UUID` | Yes | Must be a published job with an active deadline |
| `resume` | `file` | Yes | PDF/DOC/DOCX only, max 5MB |
| `cover_letter` | `string` | No | |
| `expected_salary` | `integer` | No | Positive integer |
| `available_from` | `date` | No | `YYYY-MM-DD`, must be today or future |

**Success Response — `201 Created`:**

```json
{
  "id": "f6a7b8c9-d0e1-2345-fab0-678901234567",
  "job": {
    "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
    "title": "Senior Django Developer",
    "company": "Acme Corp"
  },
  "applicant": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "resume": "https://api.hireflow.io/media/resumes/2026/03/jane_doe_resume.pdf",
  "cover_letter": "I am excited to apply...",
  "status": "applied",
  "expected_salary": 180000,
  "available_from": "2026-05-01",
  "created_at": "2026-03-21T10:30:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Already applied | `{"error": "You have already applied to this job.", "code": "duplicate_application", "details": {}}` |
| `400` | Job not published | `{"error": "This job is not accepting applications.", "code": "job_not_published", "details": {}}` |
| `400` | Job deadline passed | `{"error": "The application deadline for this job has passed.", "code": "deadline_passed", "details": {}}` |
| `400` | Invalid file type | `{"error": "Resume must be a PDF, DOC, or DOCX file.", "code": "invalid_file_type", "details": {}}` |
| `400` | File too large | `{"error": "Resume file size must not exceed 5MB.", "code": "file_too_large", "details": {}}` |
| `401` | Missing JWT | `{"error": "Authentication credentials were not provided.", "code": "not_authenticated", "details": {}}` |
| `403` | Not a candidate | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `429` | Rate limit exceeded | `{"error": "Request was throttled. Expected available in 1800 seconds.", "code": "throttled", "details": {}}` |

---

#### `GET /api/applications/`

List the authenticated candidate's own applications, or list applications for a recruiter's jobs.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Authenticated users. Candidates see their own applications. Recruiters see applications for their company's jobs |

**Query Parameters (for recruiters):**

| Param | Type | Description |
|-------|------|-------------|
| `job` | `UUID` | Filter by job ID |
| `status` | `string` | Filter by application status |
| `cursor` | `string` | Pagination cursor |

**Success Response — `200 OK` (candidate view):**

```json
{
  "next": null,
  "previous": null,
  "results": [
    {
      "id": "f6a7b8c9-d0e1-2345-fab0-678901234567",
      "job": {
        "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
        "title": "Senior Django Developer",
        "company": {
          "name": "Acme Corp",
          "slug": "acme-corp"
        },
        "status": "published"
      },
      "status": "reviewing",
      "resume": "https://api.hireflow.io/media/resumes/2026/03/jane_doe_resume.pdf",
      "cover_letter": "I am excited to apply...",
      "expected_salary": 180000,
      "available_from": "2026-05-01",
      "created_at": "2026-03-21T10:30:00Z",
      "updated_at": "2026-03-22T08:00:00Z"
    }
  ]
}
```

Note: `recruiter_notes` is **never** included in candidate responses.

---

#### `PATCH /api/applications/{id}/status/`

Update the status of an application (recruiter workflow).

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Recruiter who is a member of the application's job's company |

**Request Body:**

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `status` | `string` | Yes | Valid transition from current status (see state machine below) |
| `recruiter_notes` | `string` | No | Internal notes for the hiring team |

**Valid Status Transitions:**

```
applied → reviewing → shortlisted → interview → offered
                                   │          │          → rejected
                                   │          → rejected
                                   → rejected
         → rejected

Candidate can withdraw from any active status:
  applied    → withdrawn  (via DELETE /api/applications/{id}/)
  reviewing  → withdrawn
  shortlisted→ withdrawn
  interview  → withdrawn

Terminal statuses (no further transitions):
  offered    (recruiter may still → rejected)
  rejected
  withdrawn
```

**Success Response — `200 OK`:**

```json
{
  "id": "f6a7b8c9-d0e1-2345-fab0-678901234567",
  "status": "shortlisted",
  "recruiter_notes": "Strong Django experience, schedule technical interview.",
  "updated_at": "2026-03-22T15:00:00Z"
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Invalid status transition | `{"error": "Cannot transition from 'applied' to 'offered'.", "code": "invalid_status_transition", "details": {}}` |
| `403` | Not a company member | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `404` | Application not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `DELETE /api/applications/{id}/`

Withdraw an application (sets status to `withdrawn`).

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Applicant only (`IsOwnerOrReadOnly`) |

**Success Response — `204 No Content`:** Empty body.

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `400` | Application already withdrawn/rejected/offered | `{"error": "Cannot withdraw an application in its current status.", "code": "invalid_status_transition", "details": {}}` |
| `403` | Not the applicant | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `404` | Application not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

### 3.6 Dashboard Endpoints

#### `GET /api/dashboard/recruiter/`

Aggregated recruiter dashboard: jobs posted and application stats.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Recruiter only |

**Success Response — `200 OK`:**

```json
{
  "total_jobs": 15,
  "jobs_by_status": {
    "draft": 3,
    "published": 10,
    "closed": 2
  },
  "total_applications": 142,
  "applications_by_status": {
    "applied": 45,
    "reviewing": 30,
    "shortlisted": 25,
    "interview": 18,
    "offered": 8,
    "rejected": 12,
    "withdrawn": 4
  },
  "recent_applications": [
    {
      "id": "f6a7b8c9-d0e1-2345-fab0-678901234567",
      "applicant": {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com"
      },
      "job": {
        "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
        "title": "Senior Django Developer"
      },
      "status": "applied",
      "created_at": "2026-03-21T10:30:00Z"
    }
  ]
}
```

---

#### `GET /api/dashboard/candidate/`

Candidate dashboard: their applications and status breakdown.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Candidate only |

**Success Response — `200 OK`:**

```json
{
  "total_applications": 8,
  "applications_by_status": {
    "applied": 3,
    "reviewing": 2,
    "shortlisted": 1,
    "interview": 1,
    "offered": 1,
    "rejected": 0,
    "withdrawn": 0
  },
  "recent_applications": [
    {
      "id": "f6a7b8c9-d0e1-2345-fab0-678901234567",
      "job": {
        "id": "e5f6a7b8-c9d0-1234-efab-567890123456",
        "title": "Senior Django Developer",
        "company": {
          "name": "Acme Corp",
          "slug": "acme-corp"
        }
      },
      "status": "interview",
      "created_at": "2026-03-21T10:30:00Z",
      "updated_at": "2026-03-22T15:00:00Z"
    }
  ]
}
```

---

### 3.7 Notification Endpoints

#### `GET /api/notifications/`

List the authenticated user's notifications.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Authenticated users |

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `is_read` | `boolean` | Filter by read/unread |
| `type` | `string` | Filter by notification type |
| `cursor` | `string` | Pagination cursor |

**Success Response — `200 OK`:**

```json
{
  "next": null,
  "previous": null,
  "unread_count": 3,
  "results": [
    {
      "id": "a7b8c9d0-e1f2-3456-ab01-789012345678",
      "type": "status_changed",
      "title": "Application status updated",
      "message": "Your application status changed from reviewing to shortlisted.",
      "is_read": false,
      "metadata": {
        "job_id": "e5f6a7b8-c9d0-1234-efab-567890123456",
        "application_id": "f6a7b8c9-d0e1-2345-fab0-678901234567"
      },
      "created_at": "2026-03-22T15:00:00Z"
    }
  ]
}
```

---

#### `PATCH /api/notifications/{id}/read/`

Mark a single notification as read.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Notification owner only |

**Request Body:** None.

**Success Response — `200 OK`:**

```json
{
  "id": "a7b8c9d0-e1f2-3456-ab01-789012345678",
  "is_read": true
}
```

**Error Responses:**

| Status | Condition | Example |
|--------|-----------|---------|
| `403` | Not the notification owner | `{"error": "You do not have permission to perform this action.", "code": "permission_denied", "details": {}}` |
| `404` | Notification not found | `{"error": "Not found.", "code": "not_found", "details": {}}` |

---

#### `POST /api/notifications/mark-all-read/`

Mark all of the authenticated user's unread notifications as read.

| Field | Details |
|---|---|
| **Auth** | JWT Bearer |
| **Permission** | Authenticated users |

**Request Body:** None.

**Success Response — `200 OK`:**

```json
{
  "marked_count": 5,
  "message": "5 notifications marked as read."
}
```

---

### 3.8 Documentation Endpoints

#### `GET /api/docs/`

Swagger UI — interactive API documentation.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any |

Returns an HTML page rendered by `drf-spectacular`.

---

#### `GET /api/schema/`

OpenAPI 3.0 schema download.

| Field | Details |
|---|---|
| **Auth** | None |
| **Permission** | Any |

Returns a YAML or JSON file depending on `Accept` header.

---

## 4. Celery Task Architecture

### 4.1 Task Inventory

| Task | Module | Trigger | Async? | Why Async |
|------|--------|---------|--------|-----------|
| `send_application_received_email` | `notifications.tasks` | `post_save` signal on `Application` (created=True) | Yes | SMTP delivery takes 200-500ms and can fail; async keeps API response under 100ms |
| `send_status_update_email` | `notifications.tasks` | `pre_save` signal on `Application` (status changed) | Yes | Same as above — email delivery should never block the recruiter's workflow |
| `close_expired_jobs` | `jobs.tasks` | Celery Beat (daily cron) | Yes | Bulk update operation that scans all published jobs; inappropriate for a request-response cycle |

### 4.2 Task Details

#### `send_application_received_email`

```
Signature:    send_application_received_email(application_id: str)
Binding:      bind=True (access to self for retry)
Max Retries:  3
Retry Delay:  60 seconds (fixed)
Retry On:     Any exception (SMTPException, ConnectionError, etc.)
Idempotent:   Yes — sending the same email twice is acceptable (not destructive)
Side Effects: Sends email via Django's SMTP backend

Flow:
  1. Load Application with select_related("applicant", "job__company")
  2. Compose email: subject, plain-text body
  3. Call django.core.mail.send_mail()
  4. On failure: self.retry(exc=exc) up to 3 times
  5. After 3 failures: task enters FAILURE state in django-celery-results
```

#### `send_status_update_email`

```
Signature:    send_status_update_email(application_id: str, old_status: str, new_status: str)
Binding:      bind=True
Max Retries:  3
Retry Delay:  60 seconds (fixed)
Retry On:     Any exception
Idempotent:   Yes
Side Effects: Sends email via Django's SMTP backend

Flow:
  1. Load Application with select_related("applicant", "job")
  2. Compose email with old_status → new_status context
  3. Call django.core.mail.send_mail()
  4. On failure: self.retry(exc=exc) up to 3 times
```

#### `close_expired_jobs`

```
Module:       apps.jobs.tasks (NOT notifications — this is a Job model operation)
Signature:    close_expired_jobs()
Binding:      No (no retry logic — runs daily anyway)
Max Retries:  0
Retry Delay:  N/A
Idempotent:   Yes — UPDATE with WHERE clause is naturally idempotent
Side Effects: Bulk-updates Job rows from "published" → "closed"

Flow:
  1. Query: Job.objects.filter(status="published", deadline__lt=today)
  2. Bulk update: .update(status="closed")
  3. Return count string for logging: "Closed 5 expired jobs."
```

**Implementation (`apps/jobs/tasks.py`):**

```python
from celery import shared_task
from django.utils import timezone


@shared_task
def close_expired_jobs():
    """Periodic task — runs daily via Celery Beat."""
    from apps.jobs.models import Job

    expired = Job.objects.filter(
        status=Job.Status.PUBLISHED,
        deadline__lt=timezone.now().date(),
    )
    count = expired.update(status=Job.Status.CLOSED)
    return f"Closed {count} expired jobs."
```

### 4.3 Celery Configuration

```python
# config/celery.py
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
app = Celery("hireflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

```python
# config/settings/base.py (Celery section)
CELERY_BROKER_URL = "redis://redis:6379/0"
CELERY_RESULT_BACKEND = "django-db"           # django-celery-results
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300                  # Hard kill after 5 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 240             # Raise SoftTimeLimitExceeded after 4 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1         # Fair task distribution
```

### 4.4 Celery Beat Schedule

```python
# config/settings/base.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "close-expired-jobs-daily": {
        "task": "apps.jobs.tasks.close_expired_jobs",
        "schedule": crontab(hour=0, minute=30),    # Every day at 00:30 UTC
        "options": {"queue": "default"},
    },
}
```

The `DatabaseScheduler` from `django-celery-beat` is used in production so that schedules can be modified at runtime via Django admin without restarting the Beat process.

### 4.5 Queue Architecture

```
Redis (Broker)
  └── Queue: "default"
        ├── send_application_received_email
        ├── send_status_update_email
        └── close_expired_jobs
```

Single queue is sufficient at this scale. If email volume grows, split into dedicated queues:

```
# Future scaling
CELERY_TASK_ROUTES = {
    "apps.notifications.tasks.send_*": {"queue": "email"},
    "apps.jobs.tasks.close_*": {"queue": "maintenance"},
}
```

---

## 5. Pydantic Integration

### 5.1 Environment Variable Validation with `pydantic-settings`

Install: `pip install pydantic-settings`

```python
# config/env.py
"""
Validated environment configuration using pydantic-settings.
Import this in settings files instead of using os.environ or python-decouple directly.

Usage in config/settings/base.py:
    from config.env import env
    SECRET_KEY = env.SECRET_KEY
"""

from pydantic import Field, field_validator, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class HireFlowSettings(BaseSettings):
    """
    All environment variables for the HireFlow application.
    Validated at startup — the app will refuse to start with missing or invalid config.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ──────────────────────────────────────────────
    # Django Core
    # ──────────────────────────────────────────────
    SECRET_KEY: str = Field(
        ...,
        min_length=50,
        description="Django secret key. Must be at least 50 characters.",
    )
    DEBUG: bool = Field(default=False)
    ALLOWED_HOSTS: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Comma-separated in .env: ALLOWED_HOSTS=localhost,127.0.0.1",
    )
    DJANGO_SETTINGS_MODULE: str = Field(default="config.settings.development")

    # ──────────────────────────────────────────────
    # Database (PostgreSQL)
    # ──────────────────────────────────────────────
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="Full PostgreSQL connection string: postgres://user:pass@host:port/dbname",
    )

    # ──────────────────────────────────────────────
    # Redis
    # ──────────────────────────────────────────────
    REDIS_URL: RedisDsn = Field(
        default="redis://redis:6379/0",
        description="Redis URL for caching and Celery broker.",
    )

    # ──────────────────────────────────────────────
    # Celery
    # ──────────────────────────────────────────────
    CELERY_BROKER_URL: RedisDsn = Field(default="redis://redis:6379/0")
    CELERY_TASK_TIME_LIMIT: int = Field(default=300, ge=30, le=3600)
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=240, ge=30, le=3600)

    # ──────────────────────────────────────────────
    # JWT
    # ──────────────────────────────────────────────
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES: int = Field(default=30, ge=5, le=1440)
    JWT_REFRESH_TOKEN_LIFETIME_DAYS: int = Field(default=7, ge=1, le=30)

    # ──────────────────────────────────────────────
    # Email (SMTP)
    # ──────────────────────────────────────────────
    EMAIL_BACKEND: str = Field(default="django.core.mail.backends.smtp.EmailBackend")
    EMAIL_HOST: str = Field(default="smtp.gmail.com")
    EMAIL_PORT: int = Field(default=587, ge=1, le=65535)
    EMAIL_USE_TLS: bool = Field(default=True)
    EMAIL_HOST_USER: str = Field(default="")
    EMAIL_HOST_PASSWORD: str = Field(default="")
    DEFAULT_FROM_EMAIL: str = Field(default="noreply@hireflow.io")

    # ──────────────────────────────────────────────
    # File Uploads
    # ──────────────────────────────────────────────
    MAX_RESUME_SIZE_MB: int = Field(default=5, ge=1, le=25)
    ALLOWED_RESUME_TYPES: list[str] = Field(
        default=["application/pdf", "application/msword",
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    )

    # ──────────────────────────────────────────────
    # CORS
    # ──────────────────────────────────────────────
    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default=["http://localhost:3000"],
        description="Frontend origins allowed to make requests.",
    )

    # ──────────────────────────────────────────────
    # Validators
    # ──────────────────────────────────────────────
    @field_validator("CELERY_TASK_SOFT_TIME_LIMIT")
    @classmethod
    def soft_limit_must_be_less_than_hard_limit(cls, v, info):
        hard_limit = info.data.get("CELERY_TASK_TIME_LIMIT", 300)
        if v >= hard_limit:
            raise ValueError(
                f"CELERY_TASK_SOFT_TIME_LIMIT ({v}) must be less than "
                f"CELERY_TASK_TIME_LIMIT ({hard_limit})"
            )
        return v


# Singleton — instantiated once at import time.
# If any env var is missing or invalid, the app will crash immediately with a clear error.
env = HireFlowSettings()
```

**Usage in Django settings:**

```python
# config/settings/base.py
from config.env import env

SECRET_KEY = env.SECRET_KEY
DEBUG = env.DEBUG
ALLOWED_HOSTS = env.ALLOWED_HOSTS

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.DATABASE_URL.path.lstrip("/"),
        "USER": env.DATABASE_URL.username,
        "PASSWORD": env.DATABASE_URL.password,
        "HOST": env.DATABASE_URL.host,
        "PORT": str(env.DATABASE_URL.port),
    }
}

CELERY_BROKER_URL = str(env.CELERY_BROKER_URL)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(env.REDIS_URL),
    }
}

from datetime import timedelta
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.JWT_ACCESS_TOKEN_LIFETIME_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.JWT_REFRESH_TOKEN_LIFETIME_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}
```

### 5.2 Pydantic Models for Celery Task Payload Validation

Celery serializes task arguments as JSON. If a caller passes malformed data (wrong type, missing field, invalid UUID), the task will fail deep in the execution with an opaque error. Pydantic models validate payloads at task entry, producing clear error messages.

```python
# apps/notifications/schemas.py
"""
Pydantic models for validating Celery task payloads.
Used inside task functions to validate input before any DB queries or side effects.
"""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID


# Module-level constant — NOT inside the Pydantic model.
# Pydantic would treat a class attribute as a model field and raise a validation error.
VALID_STATUSES = frozenset({
    "applied", "reviewing", "shortlisted",
    "interview", "offered", "rejected", "withdrawn",
})


class ApplicationEmailPayload(BaseModel):
    """
    Validates the payload for send_application_received_email task.
    Ensures the application_id is a valid UUID string before we hit the database.
    """
    application_id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="UUID of the application (string format, as serialized by Celery).",
    )

    @field_validator("application_id")
    @classmethod
    def must_be_valid_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid UUID.")
        return v


class StatusUpdateEmailPayload(BaseModel):
    """
    Validates the payload for send_status_update_email task.
    Ensures both the application_id and status strings are valid before processing.
    """
    application_id: str = Field(..., min_length=36, max_length=36)
    old_status: str = Field(
        ...,
        description="Previous application status.",
    )
    new_status: str = Field(
        ...,
        description="New application status.",
    )

    @field_validator("application_id")
    @classmethod
    def must_be_valid_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid UUID.")
        return v

    @field_validator("old_status", "new_status")
    @classmethod
    def must_be_valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"'{v}' is not a valid application status. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        return v
```

**Updated tasks using Pydantic validation:**

```python
# apps/notifications/tasks.py
import logging
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from pydantic import ValidationError
from .schemas import ApplicationEmailPayload, StatusUpdateEmailPayload

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_application_received_email(self, application_id: str):
    """Notify candidate their application was received."""
    # Validate payload before any DB access
    try:
        payload = ApplicationEmailPayload(application_id=application_id)
    except ValidationError as e:
        logger.error("Invalid task payload for send_application_received_email: %s", e)
        return  # Do not retry — bad payload will never become valid

    try:
        from apps.applications.models import Application
        application = Application.objects.select_related(
            "applicant", "job__company"
        ).get(id=payload.application_id)

        send_mail(
            subject=f"Application received — {application.job.title}",
            message=(
                f"Hi {application.applicant.first_name}, your application to "
                f"{application.job.company.name} for {application.job.title} "
                f"has been received."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.applicant.email],
        )
    except Application.DoesNotExist:
        logger.warning("Application %s not found, skipping email.", payload.application_id)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_status_update_email(self, application_id: str, old_status: str, new_status: str):
    """Notify candidate when their application status changes."""
    # Validate payload before any DB access
    try:
        payload = StatusUpdateEmailPayload(
            application_id=application_id,
            old_status=old_status,
            new_status=new_status,
        )
    except ValidationError as e:
        logger.error("Invalid task payload for send_status_update_email: %s", e)
        return  # Do not retry — bad payload will never become valid

    try:
        from apps.applications.models import Application
        application = Application.objects.select_related(
            "applicant", "job"
        ).get(id=payload.application_id)

        send_mail(
            subject=f"Your application status has been updated — {application.job.title}",
            message=(
                f"Hi {application.applicant.first_name}, your application status "
                f"changed from {payload.old_status} to {payload.new_status}."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.applicant.email],
        )
    except Application.DoesNotExist:
        logger.warning("Application %s not found, skipping email.", payload.application_id)
    except Exception as exc:
        raise self.retry(exc=exc)
```

---

## 6. Security Checklist

### 6.1 JWT Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Access token lifetime | 30 minutes | Short-lived; minimizes window if token is stolen |
| Refresh token lifetime | 7 days | Balances UX (no frequent re-logins) with security |
| Algorithm | HS256 | Symmetric signing using `SECRET_KEY`. Sufficient for single-service architecture |
| `ROTATE_REFRESH_TOKENS` | `True` | Each refresh request issues a new refresh token, invalidating the old one |
| `BLACKLIST_AFTER_ROTATION` | `True` | Old refresh tokens are added to a blacklist table, preventing reuse |
| `UPDATE_LAST_LOGIN` | `True` | Tracks last login time on the User model |
| `USER_ID_FIELD` | `"id"` | UUID in token payload — no sequential ID leakage |
| `USER_ID_CLAIM` | `"user_id"` | Standard claim name |
| Token storage (client) | `httpOnly` cookie or secure local storage | Recommend `httpOnly` cookie to prevent XSS-based token theft |

```python
# config/settings/base.py — SIMPLE_JWT
from datetime import timedelta
from config.env import env

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.JWT_ACCESS_TOKEN_LIFETIME_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.JWT_REFRESH_TOKEN_LIFETIME_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": env.SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}
```

### 6.2 Rate Limiting Strategy

```python
# config/settings/base.py — DRF throttling
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",            # Unauthenticated users
        "user": "1000/hour",           # Authenticated users (general)
        "applications": "10/hour",     # POST /api/applications/
        "auth": "5/minute",            # Login/register endpoints
        "search": "30/minute",         # Full-text search (expensive query)
    },
}
```

| Endpoint Group | Scope | Rate | Rationale |
|----------------|-------|------|-----------|
| `POST /api/auth/login/` | `auth` | 5/minute | Brute-force protection |
| `POST /api/auth/register/` | `auth` | 5/minute | Spam account prevention |
| `POST /api/applications/` | `applications` | 10/hour | Prevent application spam |
| `GET /api/jobs/search/` | `search` | 30/minute | FTS queries are CPU-intensive |
| All authenticated endpoints | `user` | 1000/hour | General abuse prevention |
| All anonymous endpoints | `anon` | 100/hour | Scraping prevention |

Applied per-view using `throttle_scope`:

```python
class ApplicationCreateView(CreateAPIView):
    throttle_scope = "applications"
```

### 6.3 File Upload Validation (Resumes)

```python
# common/validators.py
import os
from django.core.exceptions import ValidationError


ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx"}
ALLOWED_RESUME_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def validate_resume(file):
    """
    Validates resume uploads for:
    1. File extension (whitelist)
    2. MIME type (whitelist) — checked via python-magic if available, else Content-Type header
    3. File size (max 5MB)
    """
    # Extension check
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise ValidationError(
            f"File type '{ext}' is not allowed. Accepted: {', '.join(ALLOWED_RESUME_EXTENSIONS)}"
        )

    # Size check
    if file.size > MAX_RESUME_SIZE_BYTES:
        raise ValidationError(
            f"File size {file.size / (1024*1024):.1f}MB exceeds the 5MB limit."
        )

    # MIME type check (Content-Type header — defense in depth, not foolproof)
    if hasattr(file, "content_type") and file.content_type not in ALLOWED_RESUME_MIME_TYPES:
        raise ValidationError(
            f"MIME type '{file.content_type}' is not allowed."
        )
```

Applied in the serializer:

```python
# apps/applications/serializers.py
from common.validators import validate_resume

class ApplicationCreateSerializer(serializers.ModelSerializer):
    resume = serializers.FileField(validators=[validate_resume])
```

### 6.4 Sensitive Field Protection

Fields that must **never** appear in API responses:

| Field | Model | Why |
|-------|-------|-----|
| `password` | `User` | Password hash — never exposed, even hashed |
| `recruiter_notes` | `Application` | Internal hiring notes — visible only to company members, never to candidates |
| `is_superuser` | `User` | Admin privilege flag — internal only |
| `is_staff` | `User` | Admin access flag — internal only |
| `search_vector` | `Job` | Internal PostgreSQL tsvector — meaningless to clients |
| `EMAIL_HOST_PASSWORD` | Settings | SMTP credential — never in any response |
| `SECRET_KEY` | Settings | Django signing key — never in any response |

Enforced via explicit serializer field declarations (whitelist approach, not blacklist):

```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "username", "first_name", "last_name",
                  "role", "phone", "avatar", "is_email_verified", "created_at"]
        # password, is_superuser, is_staff are excluded by omission
```

### 6.5 Additional Security Measures

| Measure | Implementation |
|---------|---------------|
| **CORS** | `django-cors-headers` with explicit `CORS_ALLOWED_ORIGINS` whitelist. No wildcard `*` in production |
| **CSRF** | Disabled for API (JWT-based auth doesn't use cookies by default). If using `httpOnly` cookies, re-enable CSRF |
| **SQL Injection** | Django ORM parameterizes all queries. No raw SQL in this project |
| **XSS** | DRF returns JSON responses with `Content-Type: application/json`. No HTML rendering in API |
| **HTTPS** | `SECURE_SSL_REDIRECT = True` in production. `SECURE_HSTS_SECONDS = 31536000` |
| **Password Hashing** | Django default PBKDF2-SHA256 with 720,000 iterations (Django 5.0 default) |
| **UUID PKs** | Prevents sequential ID enumeration (e.g., guessing application IDs) |
| **`select_related` in signals** | Prevents N+1 queries in Celery tasks that load related objects |

---

## 7. Architecture Decision Records

### ADR-001: Celery for Asynchronous Email Delivery

**Decision:** Use Celery with Redis as the message broker for all email-sending operations.

**Context:** When a candidate submits an application, the system needs to send a confirmation email. When a recruiter changes an application's status, the candidate needs to be notified.

**Why:**
- SMTP delivery takes 200-500ms per email, which would double API response times if done synchronously.
- SMTP servers can be temporarily unavailable. Celery's retry mechanism (3 retries, 60s delay) handles transient failures automatically.
- The API can return `201 Created` immediately while the email is delivered in the background, providing a better user experience.

**Alternatives Considered:**

| Alternative | Why Rejected |
|-------------|-------------|
| Synchronous `send_mail()` in the view | Blocks the HTTP response for 200-500ms. If SMTP fails, the API returns 500 even though the application was saved successfully. Unacceptable UX. |
| Django's `send_mail()` with `fail_silently=True` | Hides failures. No retries. Candidate never receives confirmation and has no way to know. |
| Django Channels (WebSocket) for notifications | Over-engineered for email delivery. Channels solves real-time push, not background processing. Would still need a task queue for email. |
| Amazon SQS / RabbitMQ as broker | SQS adds AWS dependency. RabbitMQ is more operationally complex than Redis. Redis is already in the stack for caching, so reusing it as a broker reduces infrastructure complexity. |

**Consequences:**
- Added operational complexity: Celery worker and Beat processes must run alongside the web server.
- Redis becomes a critical dependency (both cache and broker). Mitigation: Redis is battle-tested, and its failure mode is graceful (emails queue up and are delivered when it recovers).
- Task results are stored in PostgreSQL via `django-celery-results`, adding minimal DB load.

---

### ADR-002: UUID Primary Keys

**Decision:** All models use `UUIDField(primary_key=True, default=uuid.uuid4)` instead of Django's default auto-incrementing integer.

**Context:** Primary keys are exposed in API URLs (`/api/applications/{id}/`). Sequential integers leak business information and are vulnerable to enumeration attacks.

**Why:**
- **Security:** A competitor cannot estimate total job count or application volume by observing IDs.
- **Enumeration prevention:** An attacker cannot iterate over `/api/applications/1/`, `/api/applications/2/`, etc. to scrape data (even with proper auth, this is defense-in-depth).
- **Distributed readiness:** If the system scales to multiple write replicas or microservices, UUIDs avoid ID collisions without coordination.
- **URL safety:** UUIDs are opaque and carry no semantic meaning, which is appropriate for API identifiers.

**Alternatives Considered:**

| Alternative | Why Rejected |
|-------------|-------------|
| Auto-incrementing integer | Leaks information. Requires additional obfuscation layer (e.g., hashids) to safely expose in URLs. |
| HashID / Sqids | Adds a serialization/deserialization layer. Library dependency. Can be reversed with enough effort. |
| ULID (Universally Unique Lexicographically Sortable Identifier) | Good option, but not natively supported by Django. UUIDs are first-class citizens in both Django and PostgreSQL. |
| NanoID | Not globally unique by specification. Collision risk at scale. |

**Consequences:**
- Index size increases: UUID indexes are 16 bytes vs 4 bytes for integers. At the scale of this project (thousands, not billions of rows), the performance impact is negligible.
- UUIDs are not naturally sortable by creation time. Mitigated by `created_at` + `ordering = ["-created_at"]` on all models.
- Slightly less readable in logs. Acceptable tradeoff for security.

---

### ADR-003: DRF Serializers as the Validation Layer (Not Pydantic for Request/Response)

**Decision:** Use Django REST Framework's `ModelSerializer` for all request validation and response serialization. Use Pydantic only for environment validation (`pydantic-settings`) and Celery task payload validation.

**Context:** Pydantic is a popular validation library. Some projects use it as a full replacement for DRF serializers.

**Why:**
- DRF serializers are deeply integrated with Django's ORM: they handle `ModelSerializer` field introspection, nested relationships, `create()`/`update()` methods, and `unique_together` validation automatically.
- DRF's permission classes, pagination, filtering, and throttling all expect serializer instances. Replacing serializers with Pydantic would require custom adapter code for every DRF feature.
- The team is expected to be proficient in Django/DRF. Introducing Pydantic as a parallel validation layer increases cognitive load without proportional benefit.

**Alternatives Considered:**

| Alternative | Why Rejected |
|-------------|-------------|
| Pydantic for all request/response validation | Loses DRF's automatic model field introspection, `unique_together` validation, and nested serializer write support. Requires writing significant glue code. |
| `django-ninja` (Pydantic-native Django framework) | Replaces DRF entirely. Loses DRF's ecosystem (filters, pagination, spectacular). This project is built around DRF conventions. |
| Pydantic for Celery only, DRF for API | **This is the chosen approach.** Pydantic validates Celery payloads where DRF serializers don't apply (Celery tasks receive raw primitives, not HTTP requests). |

**Consequences:**
- Pydantic is used in a focused scope (env config + task payloads), not as a general-purpose validation layer.
- DRF serializers remain the single source of truth for API contracts.
- Developers familiar with DRF can onboard immediately without learning Pydantic patterns.

---

### ADR-004: PostgreSQL Full-Text Search over Elasticsearch

**Decision:** Use PostgreSQL's built-in full-text search (`tsvector`, `tsquery`, GIN indexes) for the job search endpoint.

**Context:** The `GET /api/jobs/search/?q=django` endpoint needs to search across job titles, descriptions, and skills with relevance ranking.

**Why:**
- PostgreSQL's FTS is sufficient for the expected dataset size (thousands to low millions of job listings).
- No additional infrastructure: the search engine lives inside the existing database. No separate cluster to provision, monitor, or synchronize.
- Native `SearchRank` provides relevance scoring. Weighted vectors (title=A, description=B) ensure title matches rank higher.
- GIN indexes make FTS queries performant at scale.

**Alternatives Considered:**

| Alternative | Why Rejected |
|-------------|-------------|
| Elasticsearch | Massive operational overhead for a feature this size. Requires a separate cluster (3+ nodes for HA), data synchronization pipeline, and monitoring. Justified only when FTS needs exceed PostgreSQL's capabilities (fuzzy matching, autocomplete, faceted search across millions of documents). |
| `ILIKE` queries | No relevance ranking. Full table scan on every query. Unusable beyond a few thousand rows. |
| Typesense / Meilisearch | Lighter than Elasticsearch, but still an additional service to deploy and sync. Not justified at this scale. |
| Django Haystack | Abstraction layer that supports multiple backends. Adds complexity without benefit when using PostgreSQL FTS directly via Django's `django.contrib.postgres.search`. |

**Consequences:**
- Search capabilities are limited compared to Elasticsearch: no fuzzy matching, no "did you mean", no faceted search out of the box. These can be added later if needed by migrating to Elasticsearch.
- The `search_vector` column must be kept in sync with `title` and `description`. Implemented via a `post_save` signal in `apps/jobs/signals.py` (see Section 2.3 for the full implementation).
- Performance is excellent up to ~10M rows with GIN indexes. Beyond that, evaluate Elasticsearch.

---

### ADR-005: Cursor-Based Pagination over Page-Number Pagination

**Decision:** Use cursor-based pagination (`CursorPagination` in DRF) for all list endpoints.

**Context:** List endpoints (`/api/jobs/`, `/api/applications/`, `/api/notifications/`) need pagination to handle large result sets.

**Why:**
- **Consistency under writes:** Page-number pagination breaks when rows are inserted or deleted between page requests. If a new job is created while a user is on page 2, page 3 will contain a duplicate from page 2. Cursor pagination guarantees no duplicates and no gaps.
- **Performance:** `OFFSET`-based queries (used by page-number pagination) become slower linearly with the offset value. `SELECT * FROM jobs OFFSET 10000 LIMIT 20` still scans 10,020 rows. Cursor pagination uses a `WHERE created_at < '2026-03-20' ORDER BY created_at DESC LIMIT 20` pattern, which is always O(log n) with an index.
- **Security:** Page-number pagination exposes total count and page count, which leaks dataset size. Cursor pagination provides only `next`/`previous` links.

**Alternatives Considered:**

| Alternative | Why Rejected |
|-------------|-------------|
| Page-number pagination (`PageNumberPagination`) | O(n) performance degradation on deep pages. Inconsistent results under concurrent writes. Exposes total count. |
| Limit-offset pagination (`LimitOffsetPagination`) | Same performance problems as page-number. Clients can request arbitrary offsets, enabling abuse. |
| No pagination | Unacceptable for any list endpoint with more than a trivial number of rows. |

**Consequences:**
- Clients cannot jump to "page 5" — they must traverse sequentially. This is acceptable for API consumers (infinite scroll, "load more" buttons) but less ideal for traditional paginated UIs with page numbers.
- Sort order is fixed (determined by the cursor field, typically `created_at DESC`). Multi-column or user-selected sorting requires additional configuration.
- Opaque cursor strings are not human-readable. This is a feature (prevents tampering), not a bug.

```python
# common/pagination.py
from rest_framework.pagination import CursorPagination


class HireFlowCursorPagination(CursorPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
```

---

### ADR-006: Multi-Tenancy via CompanyMember Through Model over Separate Schemas

**Decision:** Implement multi-tenancy using a shared database with a `CompanyMember` through model to scope data access, rather than using separate PostgreSQL schemas per tenant.

**Context:** HireFlow is a multi-tenant job board where multiple companies (tenants) post jobs. Each company's data must be isolated: Acme Corp's recruiters should not see Widget Inc's draft jobs or applications.

**Why:**
- **Simplicity:** A single database schema with row-level scoping (filtering by `company_id`) is dramatically simpler to implement, migrate, and maintain than per-tenant schemas.
- **Appropriate for the access pattern:** Tenancy in this system is shallow — companies share the same models, the same fields, and the same business logic. The only difference is data ownership. This is perfectly served by FK-based scoping.
- **No `django-tenants` dependency:** Separate-schema multi-tenancy in Django requires `django-tenants`, which patches the ORM, connection handling, and migration system. This introduces complexity and subtle bugs.
- **Cross-tenant queries are easy:** A public job listing page shows jobs from all companies. With separate schemas, this requires querying across schemas or maintaining a denormalized public table. With shared schema, it's a simple `Job.objects.published()`.

**Alternatives Considered:**

| Alternative | Why Rejected |
|-------------|-------------|
| Separate PostgreSQL schema per company (`django-tenants`) | Massive operational overhead: each new company requires a schema migration. Cross-tenant queries (public job listing) require schema iteration. Connection pooling becomes complex. Justified only for strict data isolation requirements (e.g., healthcare, enterprise SaaS with regulatory constraints). |
| Separate database per company | Even more extreme isolation. Impractical for a job board where the public listing is a core feature. |
| Row-level security (PostgreSQL RLS) | Powerful but complex. Requires setting `current_setting('app.company_id')` on every connection, which is difficult with Django's connection pooling. Not well-supported by Django ORM. Better suited for systems that need DB-enforced isolation (compliance requirements). |

**Consequences:**
- Data isolation is enforced at the application layer (Django ORM filtering + DRF permissions), not at the database layer. A bug in a view could theoretically expose another company's data. Mitigated by:
  - Custom managers (`by_company()`) that encapsulate tenant filtering.
  - `IsCompanyMember` permission class applied to every company-scoped endpoint.
  - Tests that verify cross-tenant isolation.
- All companies share the same database tables and indexes. At extreme scale (10,000+ companies, millions of rows), query performance may degrade. Mitigated by composite indexes on `(company_id, status)`.
- Schema migrations apply to all tenants simultaneously. This is actually an advantage — no need to iterate over schemas.

**Data Access Pattern:**

```python
# Every company-scoped query goes through the manager or explicit filter:

# In views — recruiter sees only their company's jobs:
jobs = Job.objects.by_company(request.user.companies.first())

# In permissions — verify the user is a member of the resource's company:
class IsCompanyMember(BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.company.members.filter(id=request.user.id).exists()

# Public listing — no tenant filter, but only published jobs:
jobs = Job.objects.published()  # All companies, published only
```

---

## Appendix A: Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Django secret key (min 50 chars) |
| `DEBUG` | No | `false` | Debug mode |
| `ALLOWED_HOSTS` | No | `localhost,127.0.0.1` | Comma-separated host list |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | No | `redis://redis:6379/0` | Redis connection string |
| `CELERY_BROKER_URL` | No | `redis://redis:6379/0` | Celery broker URL |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | No | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | No | `7` | Refresh token TTL |
| `EMAIL_HOST` | No | `smtp.gmail.com` | SMTP server |
| `EMAIL_PORT` | No | `587` | SMTP port |
| `EMAIL_USE_TLS` | No | `true` | Use TLS for SMTP |
| `EMAIL_HOST_USER` | No | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | No | — | SMTP password |
| `DEFAULT_FROM_EMAIL` | No | `noreply@hireflow.io` | Sender address |
| `CORS_ALLOWED_ORIGINS` | No | `http://localhost:3000` | CORS whitelist |

---

## Appendix B: Project File Map

```
hireflow/
├── config/
│   ├── __init__.py
│   ├── env.py                      ← Pydantic settings (Section 5.1)
│   ├── celery.py                   ← Celery app definition
│   ├── urls.py                     ← Root URL configuration
│   ├── wsgi.py
│   └── settings/
│       ├── base.py                 ← Shared settings (uses config.env)
│       ├── development.py          ← DEBUG=True, console email backend
│       └── production.py           ← HTTPS, real SMTP, Sentry
│
├── apps/
│   ├── accounts/
│   │   ├── models.py               ← User model (AbstractUser + TimeStampedModel)
│   │   ├── tokens.py               ← Email verification token (TimestampSigner)
│   │   ├── signals.py              ← Send verification email on registration
│   │   └── ...
│   ├── companies/                  ← Company + CompanyMember (tenancy)
│   ├── jobs/
│   │   ├── models.py               ← Job model + FTS
│   │   ├── tasks.py                ← close_expired_jobs (Celery Beat)
│   │   ├── signals.py              ← search_vector update on save
│   │   ├── filters.py              ← JobFilter (django-filter)
│   │   ├── managers.py             ← JobManager (published, search, by_company)
│   │   └── ...
│   ├── applications/               ← Job applications + signals
│   └── notifications/
│       ├── models.py               ← Notification model
│       ├── schemas.py              ← Pydantic task payloads (Section 5.2)
│       ├── tasks.py                ← Email Celery tasks (Section 4)
│       └── emails.py               ← Email template helpers
│
├── common/
│   ├── models.py                   ← TimeStampedModel (UUID + timestamps)
│   ├── pagination.py               ← HireFlowCursorPagination
│   ├── permissions.py              ← IsRecruiter, IsCompanyMember, IsOwnerOrReadOnly
│   ├── exceptions.py               ← Custom exception handler
│   └── validators.py               ← validate_resume (Section 6.3)
│
├── middleware/
│   └── request_logger.py           ← Request logging middleware
│
├── docker-compose.yml
├── Dockerfile
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
├── .env.example
├── ARCHITECTURE.md                 ← This document
└── README.md
```
