# HireFlow — Contributing Guide

> Local development setup, coding standards, and team workflow for the HireFlow multi-tenant job board API.
>
> Goal: A new developer should go from `git clone` to a passing test suite in under 10 minutes.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Structure](#2-repository-structure)
3. [Local Development Setup](#3-local-development-setup)
4. [Environment Configuration](#4-environment-configuration)
5. [Running the Application](#5-running-the-application)
6. [Database Migrations](#6-database-migrations)
7. [Seeding Test Data](#7-seeding-test-data)
8. [Running Tests](#8-running-tests)
9. [Code Style & Linting](#9-code-style--linting)
10. [Git Workflow & PR Conventions](#10-git-workflow--pr-conventions)
11. [Common Development Tasks](#11-common-development-tasks)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Prerequisites

Install these before starting:

| Tool | Version | Why |
|------|---------|-----|
| **Docker** | 24+ | Runs PostgreSQL, Redis, and the full app stack |
| **Docker Compose** | v2+ (bundled with Docker Desktop) | Orchestrates multi-container setup |
| **Python** | 3.12+ | Only needed if you run tests/linters outside Docker |
| **Git** | 2.40+ | Version control |

Verify your setup:

```bash
docker --version          # Docker version 24.x+
docker compose version    # Docker Compose version v2.x+
python3 --version         # Python 3.12.x (optional, for local tooling)
git --version             # git version 2.40+
```

---

## 2. Repository Structure

```
hireflow/
├── apps/
│   ├── accounts/              # User model, registration, JWT auth, email verification
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── permissions.py
│   │   ├── tokens.py          # TimestampSigner email verification tokens
│   │   ├── signals.py         # Send verification email on registration
│   │   └── tests/
│   │
│   ├── companies/             # Company CRUD, member management (multi-tenancy through model)
│   │   ├── models.py          # Company, CompanyMember
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── permissions.py     # IsCompanyMember, IsRecruiter
│   │   └── tests/
│   │
│   ├── jobs/                  # Job listings, PostgreSQL full-text search
│   │   ├── models.py          # Job model with SearchVectorField
│   │   ├── managers.py        # published(), search(), with_application_count()
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── signals.py         # update_search_vector on Job save
│   │   ├── tasks.py           # close_expired_jobs periodic task
│   │   ├── filters.py         # django-filter FilterSet
│   │   └── tests/
│   │
│   ├── applications/          # Job applications, status workflow
│   │   ├── models.py          # Application with status state machine
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── signals.py         # Trigger email tasks on create/status change
│   │   └── tests/
│   │
│   ├── notifications/         # In-app + email notifications
│   │   ├── models.py
│   │   ├── tasks.py           # send_application_received_email, send_status_update_email
│   │   ├── schemas.py         # Pydantic payload validation for Celery tasks
│   │   └── tests/
│   │
│   └── health/                # Health check endpoint (DB + Redis)
│       └── views.py
│
├── config/
│   ├── settings/
│   │   ├── base.py            # Shared settings (installed apps, middleware, Celery, JWT)
│   │   ├── development.py     # DEBUG=True, console email backend
│   │   ├── production.py      # Security hardening, SMTP email
│   │   └── test.py            # Fast test settings (MD5 hasher, eager Celery)
│   ├── urls.py                # Root URL configuration
│   ├── wsgi.py
│   ├── celery.py              # Celery app initialization
│   └── env.py                 # Pydantic-settings environment validation
│
├── tests/
│   ├── conftest.py            # Shared pytest fixtures (api_client, factories)
│   └── factories.py           # factory_boy factories for all models
│
├── docker-compose.yml         # Development stack (Django + Postgres + Redis)
├── docker-compose.prod.yml    # Production stack (adds Nginx, Celery Beat)
├── Dockerfile                 # Development Dockerfile
├── Dockerfile.prod            # Production multi-stage Dockerfile
├── manage.py
├── requirements/
│   ├── base.txt               # Core dependencies
│   ├── development.txt        # Dev tools (pytest, factory-boy, ruff, etc.)
│   └── production.txt         # Production (gunicorn, sentry-sdk, etc.)
├── setup.cfg                  # pytest + coverage config
└── .env.example               # Template for environment variables
```

---

## 3. Local Development Setup

### 3.1 Clone and Configure

```bash
# Clone the repository
git clone git@github.com:<your-org>/hireflow-api.git
cd hireflow-api

# Create your local env file from the template
cp .env.example .env
```

### 3.2 The `.env.example` File

```dotenv
# ─── Django ───────────────────────────────────────────
SECRET_KEY=django-insecure-local-dev-key-change-this-in-production-must-be-at-least-50-characters
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_SETTINGS_MODULE=config.settings.development

# ─── Database ─────────────────────────────────────────
DATABASE_URL=postgres://hireflow:hireflow@db:5432/hireflow
DB_USER=hireflow
DB_PASSWORD=hireflow

# ─── Redis ────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# ─── JWT ──────────────────────────────────────────────
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# ─── Email (development uses console backend) ────────
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=noreply@hireflow.local

# ─── CORS ─────────────────────────────────────────────
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

> **Note:** The `SECRET_KEY` in `.env.example` is intentionally insecure. It passes the minimum 50-character validation from our Pydantic settings but should never be used in production.

### 3.3 Build and Start

```bash
# Build the Docker images
docker compose build

# Start all services (Django, PostgreSQL, Redis, Celery worker, Celery beat)
docker compose up -d

# Verify everything is running
docker compose ps
```

**Expected output:**

```
NAME                STATUS              PORTS
hireflow-web-1      Up (healthy)        0.0.0.0:8000->8000/tcp
hireflow-db-1       Up (healthy)        5432/tcp
hireflow-redis-1    Up (healthy)        6379/tcp
hireflow-celery-1   Up
hireflow-beat-1     Up
```

### 3.4 Development `docker-compose.yml`

```yaml
# docker-compose.yml (development)
version: "3.9"

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app                    # Live reload — code changes apply instantly
      - media_files:/app/media
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: hireflow
      POSTGRES_USER: ${DB_USER:-hireflow}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-hireflow}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"               # Exposed for local DB tools (pgAdmin, DBeaver)
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-hireflow} -d hireflow"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"               # Exposed for redis-cli debugging
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  celery:
    build:
      context: .
      dockerfile: Dockerfile
    command: >
      celery -A config worker
      --loglevel=info
      --concurrency=1
    volumes:
      - .:/app
      - media_files:/app/media
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
    command: >
      celery -A config beat
      --loglevel=info
      --scheduler django_celery_beat.schedulers:DatabaseScheduler
    volumes:
      - .:/app
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
  media_files:
```

### 3.5 Development Dockerfile

```dockerfile
# Dockerfile (development)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg2 and Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/base.txt requirements/development.txt ./
RUN pip install --no-cache-dir -r development.txt

COPY . .
```

### 3.6 Apply Migrations and Verify

```bash
# Run migrations
docker compose exec web python manage.py migrate

# Create a superuser for Django admin
docker compose exec web python manage.py createsuperuser

# Verify the API is responding
curl http://localhost:8000/api/health/
```

**Expected health check response:**

```json
{
  "status": "healthy",
  "database": {"status": "up", "latency_ms": 1.2},
  "redis": {"status": "up", "latency_ms": 0.3}
}
```

You can now access:
- **API Root:** http://localhost:8000/api/
- **Swagger UI:** http://localhost:8000/api/docs/
- **Django Admin:** http://localhost:8000/admin/

---

## 4. Environment Configuration

### 4.1 How Environment Variables Work

HireFlow uses `pydantic-settings` (see `config/env.py`) to validate all environment variables at startup. If a required variable is missing or invalid, the app crashes immediately with a clear error message — not silently later at runtime.

```python
# config/env.py — singleton loaded once at startup
env = HireFlowSettings()

# config/settings/base.py — uses validated values
SECRET_KEY = env.SECRET_KEY
```

### 4.2 Settings Hierarchy

```
config/settings/
├── base.py          # Everything shared across all environments
├── development.py   # Imports base.py, sets DEBUG=True, console email
├── production.py    # Imports base.py, enforces HTTPS, SMTP email
└── test.py          # Imports base.py, fast password hasher, eager Celery
```

The active settings module is controlled by:

```bash
# In .env
DJANGO_SETTINGS_MODULE=config.settings.development

# Or for tests (set in setup.cfg, not .env)
DJANGO_SETTINGS_MODULE=config.settings.test
```

### 4.3 Key Differences by Environment

| Setting | Development | Test | Production |
|---------|------------|------|------------|
| `DEBUG` | `True` | `True` | `False` |
| `SECRET_KEY` | Insecure placeholder | Insecure placeholder | 50+ char random string |
| `EMAIL_BACKEND` | `console` (prints to stdout) | `locmem` (in-memory) | `smtp` (real delivery) |
| `PASSWORD_HASHER` | Default (PBKDF2) | `MD5` (fast for tests) | Default (PBKDF2) |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | `True` (synchronous) | `False` |
| `DEFAULT_FILE_STORAGE` | Local filesystem | Temp directory | Local filesystem |

---

## 5. Running the Application

### 5.1 Start Everything

```bash
docker compose up -d
```

### 5.2 View Logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f web
docker compose logs -f celery

# Last 50 lines
docker compose logs --tail 50 web
```

### 5.3 Open a Django Shell

```bash
docker compose exec web python manage.py shell
```

```python
# Quick model exploration
from apps.accounts.models import User
from apps.jobs.models import Job

User.objects.count()
Job.objects.published().count()
```

### 5.4 Run a One-Off Management Command

```bash
docker compose exec web python manage.py <command>

# Examples
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py collectstatic --noinput
```

### 5.5 Stop Everything

```bash
# Stop containers (preserves data in volumes)
docker compose down

# Stop containers AND delete volumes (clean slate — wipes your local database)
docker compose down -v
```

---

## 6. Database Migrations

### 6.1 Creating Migrations

After modifying any model:

```bash
# Generate migration files
docker compose exec web python manage.py makemigrations

# Review what was generated
docker compose exec web python manage.py showmigrations

# Apply migrations
docker compose exec web python manage.py migrate
```

### 6.2 Migration Rules

| Operation | Risk | Rule |
|-----------|------|------|
| **Add column** (nullable or with default) | Safe | One-step deploy |
| **Add index** | Low | Use `CONCURRENTLY` for large tables via `AddIndexConcurrently` |
| **Remove column** | Medium | Two-phase: deploy code that stops reading the column first, then drop it in a follow-up migration |
| **Rename column** | High | Three-phase deploy (see DEPLOYMENT.md Section 4) |
| **Drop table** | High | Ensure no code references it, then migrate |

### 6.3 Squashing Migrations

If a single app accumulates 10+ migration files during development:

```bash
# Squash into a single migration (only for unreleased migrations)
docker compose exec web python manage.py squashmigrations <app_name> 0001 0010
```

> **Never squash migrations that have already been applied in production.**

---

## 7. Seeding Test Data

### 7.1 Management Command

Create `apps/accounts/management/commands/seed_data.py`:

```python
"""
Seed command for local development.
Creates a realistic set of users, companies, jobs, and applications.

Usage:
    docker compose exec web python manage.py seed_data
    docker compose exec web python manage.py seed_data --flush  # Wipe and re-seed
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job
from apps.applications.models import Application


class Command(BaseCommand):
    help = "Seed the database with sample data for local development"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing data before seeding",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Flushing existing data...")
            Application.objects.all().delete()
            Job.objects.all().delete()
            CompanyMember.objects.all().delete()
            Company.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        self.stdout.write("Creating users...")

        # ── Recruiters ──
        recruiter1 = User.objects.create_user(
            email="recruiter@acme.com",
            username="recruiter_acme",
            password="testpass123",
            role="recruiter",
            first_name="Alice",
            last_name="Johnson",
            is_email_verified=True,
        )
        recruiter2 = User.objects.create_user(
            email="recruiter@globex.com",
            username="recruiter_globex",
            password="testpass123",
            role="recruiter",
            first_name="Bob",
            last_name="Smith",
            is_email_verified=True,
        )

        # ── Candidates ──
        candidates = []
        for i in range(1, 6):
            candidates.append(User.objects.create_user(
                email=f"candidate{i}@example.com",
                username=f"candidate{i}",
                password="testpass123",
                role="candidate",
                first_name=f"Candidate",
                last_name=f"#{i}",
                is_email_verified=True,
            ))

        self.stdout.write("Creating companies...")

        acme = Company.objects.create(
            name="Acme Corp",
            slug="acme-corp",
            description="Building the future of widgets.",
            website="https://acme.example.com",
            size="51-200",
            industry="Technology",
            location="San Francisco, CA",
            is_verified=True,
        )
        CompanyMember.objects.create(
            user=recruiter1, company=acme, role="owner"
        )

        globex = Company.objects.create(
            name="Globex Corporation",
            slug="globex-corp",
            description="Innovative solutions for a better tomorrow.",
            website="https://globex.example.com",
            size="201-500",
            industry="Engineering",
            location="New York, NY",
            is_verified=True,
        )
        CompanyMember.objects.create(
            user=recruiter2, company=globex, role="owner"
        )

        self.stdout.write("Creating jobs...")

        from django.utils import timezone
        from datetime import timedelta

        job_data = [
            ("Senior Django Developer", "full_time", "senior", 150000, 200000, acme),
            ("Frontend React Engineer", "full_time", "mid", 120000, 160000, acme),
            ("DevOps Engineer", "contract", "senior", 140000, 180000, acme),
            ("Junior Python Developer", "full_time", "junior", 70000, 90000, globex),
            ("Data Analyst", "full_time", "mid", 100000, 130000, globex),
            ("QA Engineer", "part_time", "mid", 80000, 110000, globex),
        ]

        jobs = []
        for title, job_type, exp, sal_min, sal_max, company in job_data:
            poster = recruiter1 if company == acme else recruiter2
            jobs.append(Job.objects.create(
                company=company,
                posted_by=poster,
                title=title,
                description=f"We are looking for a {title.lower()} to join our team.",
                requirements="3+ years of relevant experience.",
                skills=["Python", "Django"] if "Python" in title or "Django" in title else ["JavaScript"],
                job_type=job_type,
                experience_level=exp,
                salary_min=sal_min,
                salary_max=sal_max,
                location=company.location,
                status="published",
                deadline=timezone.now().date() + timedelta(days=30),
            ))

        self.stdout.write("Creating applications...")

        statuses = ["applied", "reviewing", "shortlisted", "interview", "offered"]
        for i, candidate in enumerate(candidates):
            for j, job in enumerate(jobs[:3]):  # Each candidate applies to first 3 jobs
                Application.objects.create(
                    job=job,
                    applicant=candidate,
                    cover_letter=f"I am very interested in the {job.title} position.",
                    status=statuses[(i + j) % len(statuses)],
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nSeed complete:"
            f"\n  Users:        {User.objects.filter(is_superuser=False).count()}"
            f"\n  Companies:    {Company.objects.count()}"
            f"\n  Jobs:         {Job.objects.count()}"
            f"\n  Applications: {Application.objects.count()}"
            f"\n"
            f"\nTest accounts (all passwords: testpass123):"
            f"\n  Recruiter:  recruiter@acme.com"
            f"\n  Recruiter:  recruiter@globex.com"
            f"\n  Candidate:  candidate1@example.com"
        ))
```

### 7.2 Run the Seed

```bash
# First time (creates data)
docker compose exec web python manage.py seed_data

# Reset and re-seed (wipes non-superuser data first)
docker compose exec web python manage.py seed_data --flush
```

### 7.3 Quick Auth Test with Seeded Data

```bash
# Get JWT tokens
curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "recruiter@acme.com", "password": "testpass123"}' | python3 -m json.tool

# Use the access token to list jobs
curl -s http://localhost:8000/api/jobs/ \
  -H "Authorization: Bearer <paste-access-token-here>" | python3 -m json.tool
```

---

## 8. Running Tests

### 8.1 Run the Full Suite

```bash
# Inside Docker (recommended — matches CI)
docker compose exec web pytest

# With verbose output
docker compose exec web pytest -v

# With coverage report
docker compose exec web pytest --cov --cov-report=term-missing
```

### 8.2 Run Specific Tests

```bash
# Single app
docker compose exec web pytest apps/jobs/tests/

# Single file
docker compose exec web pytest apps/jobs/tests/test_managers.py

# Single test class
docker compose exec web pytest apps/jobs/tests/test_managers.py::TestJobManagerPublished

# Single test method
docker compose exec web pytest apps/jobs/tests/test_managers.py::TestJobManagerPublished::test_excludes_draft_jobs

# Tests matching a keyword
docker compose exec web pytest -k "search"
```

### 8.3 Useful pytest Flags

| Flag | Purpose |
|------|---------|
| `-v` | Verbose — show each test name |
| `-x` | Stop on first failure |
| `--pdb` | Drop into debugger on failure |
| `--lf` | Re-run only last-failed tests |
| `--ff` | Run last-failed first, then the rest |
| `-n auto` | Parallel execution (requires `pytest-xdist`) |
| `--no-header` | Suppress pytest header |

### 8.4 Test Settings

Tests use `config.settings.test` which configures:

```python
# config/settings/test.py
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # Fast
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"        # In-memory
CELERY_TASK_ALWAYS_EAGER = True                                        # Synchronous
CELERY_TASK_EAGER_PROPAGATES = True                                    # Exceptions bubble up
```

This is set in `setup.cfg`:

```ini
[tool:pytest]
DJANGO_SETTINGS_MODULE = config.settings.test
python_files = tests.py test_*.py
python_classes = Test*
python_functions = test_*
addopts = --reuse-db --no-header -q
```

### 8.5 Coverage

```bash
# Generate coverage with terminal summary
docker compose exec web pytest --cov --cov-report=term-missing

# Generate HTML report
docker compose exec web pytest --cov --cov-report=html
# Open htmlcov/index.html in your browser
```

Coverage target: **90%** (enforced in CI via `fail_under=90` in `setup.cfg`).

> See [TESTING.md](./TESTING.md) for the complete testing strategy, all test examples, factory setup, and CI configuration.

---

## 9. Code Style & Linting

### 9.1 Tool Stack

| Tool | Purpose | Config File |
|------|---------|-------------|
| **Ruff** | Linter + formatter (replaces flake8, isort, black) | `pyproject.toml` |
| **mypy** | Static type checking (optional, gradually adopted) | `pyproject.toml` |

### 9.2 Ruff Configuration

```toml
# pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 120
src = ["apps", "config", "tests"]

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "DJ",     # flake8-django
    "SIM",    # flake8-simplify
]
ignore = [
    "E501",   # Line length — handled by formatter
]

[tool.ruff.lint.isort]
known-first-party = ["apps", "config"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### 9.3 Running Linters

```bash
# Check for lint errors
docker compose exec web ruff check .

# Auto-fix lint errors
docker compose exec web ruff check . --fix

# Format code
docker compose exec web ruff format .

# Check formatting without changing files
docker compose exec web ruff format . --check
```

### 9.4 Pre-Commit Hook (Optional)

If you want automatic linting before every commit:

```bash
# Install pre-commit (outside Docker, in your local Python)
pip install pre-commit
```

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

```bash
# Install the hooks
pre-commit install

# Now ruff runs automatically on every `git commit`
```

### 9.5 Coding Conventions

| Convention | Rule |
|------------|------|
| **Imports** | Standard library → third-party → Django → local apps. Ruff handles this via `isort` rules |
| **Model ordering** | Fields → `Meta` → `__str__` → `save` → custom methods |
| **Serializer ordering** | Fields → `Meta` → validators → `create` → `update` |
| **View ordering** | `queryset` → `serializer_class` → `permission_classes` → `filter_backends` → action methods |
| **Naming** | `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants |
| **URLs** | Plural nouns, no trailing verbs: `/api/jobs/`, not `/api/getJobs/` |
| **Tests** | One `Test*` class per unit under test, `test_` prefix for methods, descriptive names |

---

## 10. Git Workflow & PR Conventions

### 10.1 Branch Strategy

```
main                  ← Always deployable. Protected branch.
 └── feature/HF-123-add-job-search
 └── fix/HF-456-duplicate-application-bug
 └── chore/HF-789-upgrade-django
```

**Branch naming:** `<type>/<ticket-id>-<short-description>`

| Type | Use For |
|------|---------|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `chore/` | Dependency updates, config changes, refactoring |
| `docs/` | Documentation only |

### 10.2 Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

**Examples:**

```
feat(jobs): add PostgreSQL full-text search with GIN index

fix(applications): prevent duplicate application for same job

chore(deps): upgrade Django from 5.0.3 to 5.0.4

test(accounts): add email verification token tests

docs(api): update Swagger annotations for job filters
```

**Types:** `feat`, `fix`, `chore`, `test`, `docs`, `refactor`, `perf`, `ci`

**Scope:** The app name (`jobs`, `applications`, `accounts`, `companies`, `notifications`) or infrastructure concern (`deps`, `docker`, `ci`).

### 10.3 Pull Request Process

1. **Create a feature branch** from `main`:

   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/HF-123-add-job-search
   ```

2. **Make your changes.** Commit early and often.

3. **Before pushing**, ensure:

   ```bash
   # Tests pass
   docker compose exec web pytest

   # Linting passes
   docker compose exec web ruff check .
   docker compose exec web ruff format . --check

   # No migration conflicts
   docker compose exec web python manage.py makemigrations --check
   ```

4. **Push and open a PR:**

   ```bash
   git push -u origin feature/HF-123-add-job-search
   ```

5. **PR template:**

   ```markdown
   ## Summary
   - Brief description of what changed and why

   ## Changes
   - Bullet list of specific changes

   ## Test Plan
   - [ ] Unit tests added/updated
   - [ ] Integration tests added/updated
   - [ ] Manual testing steps (if applicable)

   ## Related
   - Closes #123
   ```

### 10.4 PR Review Checklist

Reviewers should check:

- [ ] Tests pass in CI
- [ ] Coverage doesn't drop below 90%
- [ ] No new linting warnings
- [ ] Migration is safe (see DEPLOYMENT.md Section 4)
- [ ] API changes are reflected in serializers and documented in Swagger
- [ ] No secrets or credentials in the diff
- [ ] Error responses follow the standard format: `{"error": "...", "code": "...", "details": {}}`

### 10.5 Merging

- **Squash merge** for feature branches (clean single-commit history on `main`)
- **Merge commit** for release branches or large multi-commit features that tell a story
- Delete the branch after merging

---

## 11. Common Development Tasks

### 11.1 Add a New App

```bash
# Create the app inside the apps/ directory
docker compose exec web python manage.py startapp <app_name> apps/<app_name>

# Update apps/<app_name>/apps.py
# Change: name = '<app_name>'
# To:     name = 'apps.<app_name>'

# Add to INSTALLED_APPS in config/settings/base.py
INSTALLED_APPS = [
    ...
    "apps.<app_name>",
]
```

### 11.2 Add a New API Endpoint

1. **Model** → `apps/<app>/models.py`
2. **Serializer** → `apps/<app>/serializers.py`
3. **View** → `apps/<app>/views.py` (use `ModelViewSet` or `APIView`)
4. **URL** → `apps/<app>/urls.py` (register with router or `path()`)
5. **Wire up** → `config/urls.py` (include the app's URLs)
6. **Tests** → `apps/<app>/tests/test_views.py`
7. **Migration** → `python manage.py makemigrations`

### 11.3 Add a New Celery Task

1. **Task** → `apps/<app>/tasks.py`
2. **Pydantic schema** (if task accepts external input) → `apps/<app>/schemas.py`
3. **Signal** (if triggered by model changes) → `apps/<app>/signals.py`
4. **Register signal** → `apps/<app>/apps.py` in `ready()`
5. **Test** → `apps/<app>/tests/test_tasks.py`

If it's a periodic task, add to `CELERY_BEAT_SCHEDULE` in `config/settings/base.py`.

### 11.4 Access the Database Directly

```bash
# PostgreSQL shell
docker compose exec db psql -U hireflow -d hireflow

# Useful queries
\dt                                    -- List all tables
\d+ jobs_job                           -- Describe jobs_job table
SELECT count(*) FROM jobs_job WHERE status = 'published';
```

### 11.5 Monitor Celery

```bash
# Watch Celery worker logs
docker compose logs -f celery

# Inspect active/reserved/scheduled tasks
docker compose exec celery celery -A config inspect active
docker compose exec celery celery -A config inspect reserved
docker compose exec celery celery -A config inspect scheduled

# Purge all pending tasks (use with caution in dev)
docker compose exec celery celery -A config purge
```

### 11.6 Monitor Redis

```bash
# Redis CLI
docker compose exec redis redis-cli

# Inside redis-cli:
INFO memory              # Memory usage
DBSIZE                   # Number of keys
KEYS *                   # List all keys (dev only — never in production)
```

---

## 12. Troubleshooting

### "Port 5432 already in use"

You have a local PostgreSQL running on the same port.

```bash
# Option 1: Stop your local PostgreSQL
brew services stop postgresql     # macOS
sudo systemctl stop postgresql    # Linux

# Option 2: Change the exposed port in docker-compose.yml
ports:
  - "5433:5432"    # Map to host port 5433 instead
```

### "django.db.utils.OperationalError: could not connect to server"

The database container isn't ready yet. Wait a few seconds and retry:

```bash
# Check container health
docker compose ps

# If db shows "starting", wait for it
docker compose logs db
```

### "ModuleNotFoundError: No module named 'apps.xxx'"

Ensure the app is in `INSTALLED_APPS` with the `apps.` prefix:

```python
# Correct
"apps.jobs"

# Wrong
"jobs"
```

### Celery Tasks Not Executing

```bash
# 1. Is the Celery worker running?
docker compose ps celery

# 2. Is Redis reachable?
docker compose exec celery python -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"

# 3. Check Celery worker logs for errors
docker compose logs celery

# 4. Are tasks being discovered?
docker compose exec celery celery -A config inspect registered
```

### Migration Conflicts

Two developers created migrations for the same app simultaneously:

```bash
# Check for conflicts
docker compose exec web python manage.py showmigrations

# Resolve by merging
docker compose exec web python manage.py makemigrations --merge
```

### "Permission denied" on media files

The Docker volume for media files may have wrong ownership:

```bash
# Fix permissions (inside the container)
docker compose exec web chmod -R 755 /app/media
```

### Fresh Start (Nuclear Option)

When all else fails:

```bash
# Stop everything, remove all volumes, rebuild from scratch
docker compose down -v
docker compose build --no-cache
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_data
```

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Start dev environment | `docker compose up -d` |
| Stop dev environment | `docker compose down` |
| View logs | `docker compose logs -f web` |
| Run migrations | `docker compose exec web python manage.py migrate` |
| Create migrations | `docker compose exec web python manage.py makemigrations` |
| Seed database | `docker compose exec web python manage.py seed_data` |
| Run all tests | `docker compose exec web pytest` |
| Run tests with coverage | `docker compose exec web pytest --cov --cov-report=term-missing` |
| Lint check | `docker compose exec web ruff check .` |
| Format code | `docker compose exec web ruff format .` |
| Django shell | `docker compose exec web python manage.py shell` |
| Database shell | `docker compose exec db psql -U hireflow -d hireflow` |
| Celery inspect | `docker compose exec celery celery -A config inspect active` |
