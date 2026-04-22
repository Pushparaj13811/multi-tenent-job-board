# HireFlow

A multi-tenant job board API built with Django 5.0, Django REST Framework, Celery, Redis, and PostgreSQL. Companies can post jobs, manage applications, and track hiring pipelines — all in complete isolation from each other.

I built this to get hands-on with multi-tenancy patterns, full-text search in PostgreSQL, and async task processing with Celery. It follows strict TDD throughout.

---

## What it does

- **Companies** can register, post jobs, and manage their hiring pipeline
- **Candidates** can search jobs, apply, and track their application status
- **Recruiters** move applications through a state machine: applied → reviewing → shortlisted → interview → offered / rejected
- **Email notifications** fire asynchronously via Celery when applications are created or status changes
- **Full-text search** on job title and description using PostgreSQL's `SearchVector` with weighted ranking
- **Dashboard endpoints** give recruiters and candidates aggregated stats without N+1 queries
- **JWT authentication** with email verification on registration

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| API | Django 5.0 + Django REST Framework 3.15 |
| Auth | SimpleJWT 5.3 (access + refresh tokens) |
| Database | PostgreSQL 15 with GIN indexes for FTS |
| Cache / Broker | Redis 7 |
| Task queue | Celery 5.3 + Celery Beat |
| Payload validation | Pydantic v2 (Celery task schemas) |
| API docs | drf-spectacular (OpenAPI 3.0 + Swagger UI) |
| Containerization | Docker + Docker Compose |
| Linting | Ruff |
| CI | GitHub Actions |

---

## Getting started

### Prerequisites

- Docker and Docker Compose
- Git

That's it — everything else runs inside containers.

### Setup

```bash
git clone <repo-url>
cd multi-tenent-job-board-api
cp .env.example .env
docker compose up -d
docker compose exec web python manage.py migrate
```

The API will be available at `http://localhost:8000`.

### Seed data

If you want some sample data to play with:

```bash
docker compose exec web python manage.py seed_data
```

This creates 2 recruiters, 5 candidates, 2 companies, 6 jobs, and 15 applications. Run with `--flush` to wipe and recreate:

```bash
docker compose exec web python manage.py seed_data --flush
```

---

## Running tests

```bash
docker compose exec web pytest
```

For coverage:

```bash
docker compose exec web pytest --cov=apps --cov=common --cov-report=term-missing
```

There are around 215 tests covering models, serializers, views, signals, Celery tasks, Pydantic schemas, permissions, filters, and a full end-to-end integration test. Overall coverage is ≥90%.

---

## API overview

Interactive docs are available at `http://localhost:8000/api/docs/` once the server is running.

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register/` | Register (candidate or recruiter) |
| POST | `/api/auth/login/` | Get access + refresh tokens |
| POST | `/api/auth/token/refresh/` | Refresh access token |
| POST | `/api/auth/verify-email/` | Verify email address |

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs/` | List published jobs (public) |
| POST | `/api/jobs/` | Create a job (company member) |
| GET | `/api/jobs/{slug}/` | Job detail |
| PATCH | `/api/jobs/{slug}/` | Update job |
| POST | `/api/jobs/{slug}/publish/` | Publish a draft |
| POST | `/api/jobs/{slug}/close/` | Close a job |
| GET | `/api/jobs/search/?q=django` | Full-text search |

### Applications

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/applications/` | Apply to a job |
| GET | `/api/applications/` | List applications (scoped by role) |
| PATCH | `/api/applications/{id}/status/` | Update application status (recruiter) |
| DELETE | `/api/applications/{id}/` | Withdraw application |

### Companies

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/companies/` | List verified companies (public) |
| POST | `/api/companies/` | Create a company (recruiter) |
| GET | `/api/companies/{slug}/` | Company detail |
| POST | `/api/companies/{slug}/members/` | Invite a member |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/recruiter/` | Recruiter stats (jobs, applications, pipeline) |
| GET | `/api/dashboard/candidate/` | Candidate stats (applications by status) |

### Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications/` | List notifications |
| POST | `/api/notifications/{id}/mark-read/` | Mark one as read |
| POST | `/api/notifications/mark-all-read/` | Mark all as read |

---

## Project structure

```
.
├── apps/
│   ├── accounts/        # User model, JWT auth, email verification
│   ├── applications/    # Application model, status workflow, signals
│   ├── companies/       # Company and CompanyMember models
│   ├── dashboard/       # Aggregation views for recruiters and candidates
│   ├── health/          # Health check endpoint (DB + Redis)
│   ├── jobs/            # Job model, FTS, custom manager, filters, tasks
│   └── notifications/   # Notification model, Celery tasks, Pydantic schemas
├── common/
│   ├── exceptions.py    # Custom DRF exception handler
│   ├── models.py        # TimeStampedModel (UUID PK, created_at, updated_at)
│   ├── pagination.py    # Cursor pagination (page_size=20, max=100)
│   ├── permissions.py   # IsRecruiter, IsCandidate, IsCompanyMember, IsOwnerOrReadOnly
│   └── validators.py    # Resume file validator (PDF/DOC/DOCX, ≤5MB)
├── config/
│   ├── celery.py        # Celery app init
│   ├── env.py           # Pydantic-settings config
│   ├── settings/        # base / development / test / production
│   └── urls.py          # Root URL config
├── middleware/
│   └── request_logger.py  # Structured JSON request logging
├── tests/               # Integration and cross-cutting tests
├── docker-compose.yml
├── Dockerfile
└── .github/workflows/   # GitHub Actions CI
```

---

## Multi-tenancy

Isolation is enforced at the model layer, not through separate schemas or databases. Every resource that belongs to a company (`Job`, `Application`, etc.) is filtered through `CompanyMember` membership checks in the permission classes and querysets.

A recruiter from Company A has no way to see or modify Company B's jobs or applications — this is verified explicitly in the test suite with cross-tenant isolation tests.

---

## Application status flow

```
applied → reviewing → shortlisted → interview → offered
                 ↘                          ↘
               rejected                  rejected
```

Candidates can withdraw from `applied` or `reviewing`. Transitions outside the valid set return 400. The state machine is a plain Python dict — no third-party library needed.

---

## Environment variables

Copy `.env.example` to `.env` and update as needed. The main ones:

```
DJANGO_SECRET_KEY=your-secret-key
DATABASE_URL=postgres://hireflow:hireflow@db:5432/hireflow
REDIS_URL=redis://redis:6379/0
EMAIL_HOST=smtp.example.com
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

See `.env.example` for the full list.

---

## License

MIT
