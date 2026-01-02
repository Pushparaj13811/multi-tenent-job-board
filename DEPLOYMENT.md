# HireFlow — Deployment & Operations Runbook

> Production operations guide for the HireFlow multi-tenant job board API.
>
> Infrastructure: Single DigitalOcean Droplet (2 vCPU / 2 GB RAM) running Docker Compose.
>
> Written for the engineer debugging at 2am. Every command is copy-pasteable.

---

## Table of Contents

1. [Infrastructure Overview](#1-infrastructure-overview)
2. [Production Environment Variables](#2-production-environment-variables)
3. [Zero-Downtime Deployment Procedure](#3-zero-downtime-deployment-procedure)
4. [Database Migration Safety Rules](#4-database-migration-safety-rules)
5. [Celery Worker Management](#5-celery-worker-management)
6. [Health Checks](#6-health-checks)
7. [Monitoring](#7-monitoring)
8. [Log Aggregation](#8-log-aggregation)
9. [Rollback Procedure](#9-rollback-procedure)
10. [Backup Strategy](#10-backup-strategy)

---

## 1. Infrastructure Overview

### 1.1 What Runs Where

```
┌──────────────────────────────────────────────────────────────────┐
│                  DigitalOcean Droplet                             │
│                  Ubuntu 22.04 LTS                                │
│                  2 vCPU / 2 GB RAM / 50 GB SSD                   │
│                  Region: Choose closest to your users             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                    Docker Compose                          │  │
│  │                                                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │  │  Nginx   │  │  Django  │  │  Celery  │  │  Celery  │  │  │
│  │  │ (reverse │  │ Gunicorn │  │  Worker  │  │   Beat   │  │  │
│  │  │  proxy)  │  │  :8000   │  │          │  │          │  │  │
│  │  │  :80/443 │  │ 3 workers│  │ 2 conc.  │  │ 1 proc.  │  │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │  │
│  │       │              │              │              │        │  │
│  │       └──────┬───────┘              │              │        │  │
│  │              │                      │              │        │  │
│  │  ┌───────────▼──────────────────────▼──────────────▼────┐  │  │
│  │  │              Docker Network (hireflow_net)            │  │  │
│  │  └───────────┬──────────────────────┬───────────────────┘  │  │
│  │              │                      │                      │  │
│  │  ┌───────────▼─────┐  ┌────────────▼────┐                 │  │
│  │  │   PostgreSQL 15 │  │    Redis 7      │                 │  │
│  │  │     :5432       │  │     :6379       │                 │  │
│  │  │  Volume: pgdata │  │  Volume: redis  │                 │  │
│  │  └─────────────────┘  └─────────────────┘                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  /opt/hireflow/          ← App root                              │
│  /opt/hireflow/backups/  ← PostgreSQL daily dumps                │
│  /opt/hireflow/media/    ← Uploaded resumes, avatars, logos      │
│  /opt/hireflow/.env      ← Production environment (chmod 600)    │
└──────────────────────────────────────────────────────────────────┘
```

### 1.2 Resource Budget (2 GB RAM)

| Service | Memory Limit | Notes |
|---------|-------------|-------|
| Nginx | ~20 MB | Reverse proxy, TLS termination, static files |
| Gunicorn (3 workers) | ~450 MB | 150 MB per worker (Django + DRF) |
| Celery Worker (concurrency=2) | ~300 MB | 150 MB per subprocess |
| Celery Beat | ~80 MB | Single lightweight scheduler |
| PostgreSQL 15 | ~400 MB | `shared_buffers=128MB`, connection limit 50 |
| Redis 7 | ~100 MB | `maxmemory 100mb` with `allkeys-lru` |
| OS + Docker overhead | ~300 MB | Kernel, systemd, Docker daemon |
| **Total** | **~1,650 MB** | Leaves ~350 MB headroom for spikes |

### 1.3 Production docker-compose.yml

```yaml
# docker-compose.prod.yml
version: "3.9"

services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./certbot/conf:/etc/letsencrypt:ro
      - ./certbot/www:/var/www/certbot:ro
      - static_files:/app/staticfiles:ro
      - media_files:/app/media:ro
    depends_on:
      web:
        condition: service_healthy
    restart: always
    mem_limit: 64m
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/api/health/"]
      interval: 30s
      timeout: 5s
      retries: 3

  web:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: >
      gunicorn config.wsgi:application
      --bind 0.0.0.0:8000
      --workers 3
      --worker-class gthread
      --threads 2
      --timeout 30
      --graceful-timeout 10
      --max-requests 1000
      --max-requests-jitter 50
      --access-logfile -
      --error-logfile -
    volumes:
      - static_files:/app/staticfiles
      - media_files:/app/media
    env_file: .env
    expose:
      - "8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: always
    mem_limit: 512m
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  celery:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: >
      celery -A config worker
      --loglevel=info
      --concurrency=2
      --max-tasks-per-child=100
      --without-heartbeat
      --without-mingle
      --without-gossip
    volumes:
      - media_files:/app/media
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: always
    mem_limit: 384m

  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: >
      celery -A config beat
      --loglevel=info
      --scheduler django_celery_beat.schedulers:DatabaseScheduler
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: always
    mem_limit: 128m

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: hireflow
      POSTGRES_USER: ${DB_USER:-hireflow}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backups:/backups
    ports:
      - "127.0.0.1:5432:5432"  # Only accessible from localhost
    restart: always
    mem_limit: 512m
    shm_size: 128m
    command: >
      postgres
      -c shared_buffers=128MB
      -c effective_cache_size=512MB
      -c work_mem=4MB
      -c maintenance_work_mem=64MB
      -c max_connections=50
      -c log_min_duration_statement=500
      -c log_statement=ddl
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-hireflow} -d hireflow"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: >
      redis-server
      --maxmemory 100mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
    volumes:
      - redisdata:/data
    ports:
      - "127.0.0.1:6379:6379"  # Only accessible from localhost
    restart: always
    mem_limit: 128m
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
  redisdata:
  static_files:
  media_files:
```

### 1.4 Production Dockerfile

```dockerfile
# Dockerfile.prod
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg2 and Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/production.txt ./
RUN pip install -r production.txt

COPY . .
RUN python manage.py collectstatic --noinput

# Non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser
```

### 1.5 Nginx Configuration

```nginx
# nginx/conf.d/hireflow.conf
upstream django {
    server web:8000;
}

server {
    listen 80;
    server_name api.hireflow.io;

    # Let's Encrypt challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name api.hireflow.io;

    ssl_certificate     /etc/letsencrypt/live/api.hireflow.io/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.hireflow.io/privkey.pem;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Max upload size (resumes are capped at 5MB, give headroom)
    client_max_body_size 10M;

    # Static files (collected by collectstatic)
    location /static/ {
        alias /app/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Media files (user uploads)
    location /media/ {
        alias /app/media/;
        expires 7d;
    }

    # API proxy
    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
        proxy_connect_timeout 5s;
    }
}
```

---

## 2. Production Environment Variables

### 2.1 Complete Production .env

```bash
# ══════════════════════════════════════════════════════════════
# HireFlow Production Environment
# ══════════════════════════════════════════════════════════════
# SECURITY: This file must be chmod 600 and owned by root.
#           NEVER commit this to git.
# ══════════════════════════════════════════════════════════════

# ── Django Core ───────────────────────────────────────────────
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=<generate-with-command-below>
DEBUG=false
ALLOWED_HOSTS=api.hireflow.io,<droplet-ip>

# ── Database ──────────────────────────────────────────────────
DATABASE_URL=postgres://hireflow:<db-password>@db:5432/hireflow
DB_USER=hireflow
DB_PASSWORD=<generate-40-char-password>

# ── Redis ─────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0

# ── JWT ───────────────────────────────────────────────────────
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=15
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# ── Email (SMTP) ─────────────────────────────────────────────
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.postmarkapp.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=<postmark-server-api-token>
EMAIL_HOST_PASSWORD=<postmark-server-api-token>
DEFAULT_FROM_EMAIL=notifications@hireflow.io

# ── CORS ──────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS=https://hireflow.io,https://www.hireflow.io

# ── Sentry (error tracking) ──────────────────────────────────
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
```

### 2.2 What Must Change from Development

| Variable | Dev Default | Production Requirement | Why |
|----------|-----------|----------------------|-----|
| `SECRET_KEY` | (none — required) | **Unique, random, 50+ chars** | Signs JWT tokens, CSRF tokens, sessions. Reusing across envs = total compromise |
| `DEBUG` | `true` | **`false`** | Debug mode leaks stack traces, SQL queries, and settings to attackers |
| `ALLOWED_HOSTS` | `localhost` | **Your actual domain + IP** | Without this, Django accepts requests for any Host header (host header injection) |
| `DATABASE_URL` | `postgres://postgres:postgres@...` | **Dedicated user, strong password** | Default `postgres` user has superuser privileges |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | **Your production frontend URL(s)** | Open CORS allows any website to make authenticated API calls |
| `EMAIL_BACKEND` | `console` | **Real SMTP provider** | Console backend prints emails to stdout — users never receive them |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `30` | **`15`** | Shorter lifetime in prod reduces window if a token is stolen |

### 2.3 Generating a Secure SECRET_KEY

```bash
# Option 1: Python (recommended — produces Django-compatible key)
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
# Output: 4&s!k7^w9#q2@r5$n8m3...  (50 characters)

# Option 2: OpenSSL (if Django is not installed locally)
openssl rand -base64 64 | tr -d '\n' | head -c 64
# Output: a3Bf9Kp2Wz8Qd1Rv... (64 characters)

# Option 3: Python stdlib (no Django needed)
python -c "import secrets; print(secrets.token_urlsafe(64))"
# Output: aBcDeFgHiJkL... (86 characters)
```

**Rules for SECRET_KEY in production:**
- Minimum 50 characters (the `pydantic-settings` validator enforces this)
- Generated once, never changed (changing it invalidates all existing JWT tokens, sessions, and signed URLs)
- If compromised: generate a new one immediately, redeploy, force all users to re-authenticate

### 2.4 Securing the .env File

```bash
# On the Droplet
sudo chown root:root /opt/hireflow/.env
sudo chmod 600 /opt/hireflow/.env

# Verify
ls -la /opt/hireflow/.env
# Expected: -rw------- 1 root root 1234 Mar 21 10:00 /opt/hireflow/.env

# Docker Compose reads .env as root — non-root processes inside
# containers receive the values as environment variables, but cannot
# read the .env file itself.
```

---

## 3. Zero-Downtime Deployment Procedure

### 3.1 Deployment Overview

```
                    TIMELINE
                    ────────
    Old containers     │     New containers
    serving traffic    │     serving traffic
         ▼             │            ▼
  ───────────────────┬─┼─┬────────────────────
                     │ │ │
           Pull code─┘ │ └─Nginx routes to new
           Build image  │
           Run migrations│
           Rolling restart│
                         │
              ~60 seconds of overlap
              (old + new both running)
```

### 3.2 Step-by-Step Deploy

SSH into the Droplet and run these commands:

```bash
# ── Step 0: Record what we're deploying ───────────────────────
cd /opt/hireflow
OLD_COMMIT=$(git rev-parse HEAD)
echo "Current: $OLD_COMMIT"

# ── Step 1: Pull latest code ─────────────────────────────────
git fetch origin main
git log --oneline HEAD..origin/main    # Review what's new
git pull origin main
NEW_COMMIT=$(git rev-parse HEAD)
echo "Deploying: $OLD_COMMIT → $NEW_COMMIT"

# ── Step 2: Build the new image (does NOT affect running containers)
docker compose -f docker-compose.prod.yml build web

# ── Step 3: Run database migrations (see Section 4 for safety rules)
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py migrate --verbosity=1

# Expected output:
#   Running migrations:
#     Applying jobs.0003_add_is_deleted... OK
#
# If you see "No migrations to apply." — that's fine, skip to step 4.
# If a migration FAILS — STOP. Do NOT proceed. See Section 9 (Rollback).

# ── Step 4: Collect static files ──────────────────────────────
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py collectstatic --noinput

# ── Step 5: Rolling restart of web workers ────────────────────
# This is the zero-downtime trick:
# - "up -d --no-deps web" recreates ONLY the web container
# - Nginx health-checks detect the new container
# - Old container receives SIGTERM → finishes in-flight requests
#   (Gunicorn's --graceful-timeout 10 gives it 10 seconds)
docker compose -f docker-compose.prod.yml up -d --no-deps --build web

# Wait for the new container to be healthy
echo "Waiting for health check..."
sleep 10
docker compose -f docker-compose.prod.yml ps web
# Expected: web   Up (healthy)

# ── Step 6: Restart Celery (graceful — see Section 5) ────────
docker compose -f docker-compose.prod.yml up -d --no-deps --build celery
docker compose -f docker-compose.prod.yml up -d --no-deps --build celery-beat

# ── Step 7: Verify ───────────────────────────────────────────
curl -s https://api.hireflow.io/api/health/ | python -m json.tool
# Expected:
# {
#     "status": "healthy",
#     "database": "connected",
#     "redis": "connected",
#     "timestamp": "2026-03-21T10:05:00Z"
# }

# Smoke test a real endpoint
curl -s https://api.hireflow.io/api/jobs/ | head -c 200

# ── Step 8: Tag the deploy ────────────────────────────────────
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $NEW_COMMIT" >> /opt/hireflow/deploy.log
echo "Deploy complete."
```

### 3.3 Migration Timing Decision Tree

```
Is this migration additive-only?
(Adding columns with defaults, adding tables, adding indexes)
│
├── YES → Run migration BEFORE restarting code (Step 3 above).
│         Old code ignores new columns. New code uses them.
│
└── NO → Is it a column removal or rename?
         │
         ├── REMOVAL → Two-phase deploy. See Section 4.2.
         │             Deploy 1: Remove code references, keep column.
         │             Deploy 2: Run migration to drop column.
         │
         └── RENAME → Three-phase deploy. See Section 4.3.
                      Deploy 1: Add new column, backfill, code reads both.
                      Deploy 2: Code uses only new column.
                      Deploy 3: Drop old column.
```

---

## 4. Database Migration Safety Rules

### 4.1 What Makes a Migration Dangerous

| Operation | Danger Level | Why It's Dangerous | Safe Alternative |
|-----------|-------------|-------------------|------------------|
| `DROP COLUMN` | **HIGH** | Old code still references the column during deploy overlap | Two-phase deploy |
| `RENAME COLUMN` | **HIGH** | Both old and new code must work during rollout | Add new → backfill → swap → drop old |
| `ALTER COLUMN TYPE` | **HIGH** | May require full table rewrite, locks table | Add new column, backfill, swap |
| `ADD COLUMN (no default)` | **MEDIUM** | Existing rows have NULL; old code may not handle it | Always set `default=` or `null=True` |
| `ADD COLUMN (with default)` | **LOW** | Django 5.0+ sets DB-level defaults, no table rewrite | Safe for normal deploys |
| `ADD INDEX` | **MEDIUM** | Locks table during creation on large tables | Use `CREATE INDEX CONCURRENTLY` |
| `ADD TABLE` | **LOW** | No impact on existing code | Safe |
| `ADD INDEX (GIN)` | **MEDIUM** | GIN index builds are slow on large text columns | Use `CONCURRENTLY` |

### 4.2 Safely Removing a Column (Two-Phase Deploy)

**Example:** Remove the `responsibilities` column from `jobs_job`.

```
Phase 1 (Deploy A): Remove all code references
────────────────────────────────────────────────
1. Remove `responsibilities` from all serializers, views, filters
2. Remove from the Model class (but do NOT create a migration yet)
   Actually: keep the field in the model, just stop using it in code
3. Deploy. Old and new code both have the column. No breakage.

Phase 2 (Deploy B): Drop the column (24 hours later)
─────────────────────────────────────────────────────
1. Remove the field from the model
2. Run: python manage.py makemigrations
3. Review the migration:
```

```python
# jobs/migrations/0005_remove_job_responsibilities.py
# Verify this is the ONLY operation in the migration
class Migration(migrations.Migration):
    operations = [
        migrations.RemoveField(
            model_name='job',
            name='responsibilities',
        ),
    ]
```

```
4. Deploy normally. Migration runs, column is dropped.
   Since no code references it anymore, zero impact.
```

### 4.3 Safely Renaming a Column (Three-Phase Deploy)

**Example:** Rename `salary_min` → `compensation_floor`.

```
Phase 1 (Deploy A): Add new column, write to both
──────────────────────────────────────────────────
1. Add new field `compensation_floor` to model (nullable)
2. Create data migration to backfill:
```

```python
# jobs/migrations/0006_add_compensation_floor.py
from django.db import migrations

def backfill(apps, schema_editor):
    Job = apps.get_model("jobs", "Job")
    Job.objects.all().update(compensation_floor=models.F("salary_min"))

class Migration(migrations.Migration):
    operations = [
        migrations.AddField(
            model_name="job",
            name="compensation_floor",
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
```

```
3. Update code to WRITE to both columns, READ from new column
4. Deploy.

Phase 2 (Deploy B): Read/write only new column
───────────────────────────────────────────────
1. Remove all references to `salary_min` from code
2. Deploy. Old column still exists in DB but is unused.

Phase 3 (Deploy C): Drop old column
────────────────────────────────────
1. Remove `salary_min` from model, makemigrations
2. Deploy with migration.
```

### 4.4 Safe Index Creation on Large Tables

Standard `CREATE INDEX` locks the table. For tables with 100K+ rows:

```python
# jobs/migrations/0007_add_index_concurrently.py
from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models

class Migration(migrations.Migration):
    atomic = False  # REQUIRED for CONCURRENTLY

    operations = [
        AddIndexConcurrently(
            model_name="job",
            index=models.Index(
                fields=["location", "is_remote"],
                name="jobs_job_location_remote_idx",
            ),
        ),
    ]
```

Run with: `python manage.py migrate --database=default`

**Important:** `atomic = False` means this migration cannot be rolled back automatically. If it fails midway, you must manually clean up.

---

## 5. Celery Worker Management

### 5.1 Graceful Restart After Deploy

```bash
# ── Option A: Docker Compose rolling restart (recommended) ────
# Sends SIGTERM → worker finishes current task → exits → Docker restarts it
docker compose -f docker-compose.prod.yml restart celery

# Verify the worker came back
docker compose -f docker-compose.prod.yml logs --tail=20 celery
# Expected: "celery@<hostname> ready." and "Connected to redis://..."

# ── Option B: Send warm shutdown signal directly ──────────────
# SIGTERM = finish current task, then exit
docker compose -f docker-compose.prod.yml exec celery \
  celery -A config control shutdown

# Wait for it to stop, then bring it back up
docker compose -f docker-compose.prod.yml up -d celery
```

**NEVER send SIGKILL (kill -9) to a Celery worker.** It terminates mid-task, leaving the task in a "started" state that will never complete or retry.

### 5.2 Check Queue Depth (Are Tasks Backing Up?)

```bash
# Method 1: Celery inspect (connects to running worker)
docker compose -f docker-compose.prod.yml exec celery \
  celery -A config inspect active
# Shows currently executing tasks. If empty = worker is idle = good.

docker compose -f docker-compose.prod.yml exec celery \
  celery -A config inspect reserved
# Shows tasks claimed but not yet started. Should be 0-2 normally.

# Method 2: Redis CLI (check queue length directly)
docker compose -f docker-compose.prod.yml exec redis \
  redis-cli LLEN default
# Returns: (integer) 0
# If this number is growing → tasks are enqueuing faster than workers can process.
# Action: scale workers or investigate slow tasks.

# Method 3: Check scheduled (ETA/countdown) tasks
docker compose -f docker-compose.prod.yml exec celery \
  celery -A config inspect scheduled
```

### 5.3 Diagnosing Stuck Tasks

```bash
# ── Is the worker even running? ───────────────────────────────
docker compose -f docker-compose.prod.yml ps celery
# Expected: celery   Up   (if it says "Restarting" → it's crash-looping)

# ── Check worker logs for errors ──────────────────────────────
docker compose -f docker-compose.prod.yml logs --tail=100 celery | grep -i error

# ── List active tasks with timing ─────────────────────────────
docker compose -f docker-compose.prod.yml exec celery \
  celery -A config inspect active --json | python -m json.tool
# Look for tasks running for more than 5 minutes (time_start field)

# ── Check for tasks stuck in "STARTED" state in DB ────────────
docker compose -f docker-compose.prod.yml exec web \
  python manage.py shell -c "
from django_celery_results.models import TaskResult
stuck = TaskResult.objects.filter(status='STARTED')
for t in stuck[:10]:
    print(f'{t.task_id} | {t.task_name} | started: {t.date_created}')
"
```

### 5.4 Flush the Queue (Nuclear Option)

**WARNING:** This discards ALL pending tasks. Only do this if tasks are corrupted or you need to clear a backlog of bad tasks.

```bash
# Flush the default queue
docker compose -f docker-compose.prod.yml exec redis \
  redis-cli DEL default

# Verify it's empty
docker compose -f docker-compose.prod.yml exec redis \
  redis-cli LLEN default
# Expected: (integer) 0

# Restart workers to pick up fresh state
docker compose -f docker-compose.prod.yml restart celery
```

### 5.5 Celery Decision Tree for Incidents

```
Tasks not being processed?
│
├── Is the worker running?
│   docker compose -f docker-compose.prod.yml ps celery
│   │
│   ├── NO (Exited/Restarting)
│   │   → Check logs: docker compose logs --tail=50 celery
│   │   → Common causes: OOM kill, Redis unreachable, import error
│   │   → Fix the issue, then: docker compose up -d celery
│   │
│   └── YES (Up)
│       → Is Redis reachable?
│         docker compose exec redis redis-cli PING
│         │
│         ├── NO (connection refused)
│         │   → Restart Redis: docker compose restart redis
│         │   → Workers will auto-reconnect
│         │
│         └── YES (PONG)
│             → Check queue depth: redis-cli LLEN default
│             │
│             ├── Queue is GROWING (>50 tasks)
│             │   → Worker is slow or stuck
│             │   → Check active tasks: celery inspect active
│             │   → If task running >5min: likely a deadlock or external timeout
│             │   → Restart worker: docker compose restart celery
│             │
│             └── Queue is EMPTY (0 tasks)
│                 → Tasks are not being enqueued
│                 → Check Django logs for signal errors
│                 → Verify .delay() is being called (not .apply())
```

---

## 6. Health Checks

### 6.1 Health Check Endpoint

```python
# apps/health/views.py
"""
Production health check endpoint.
Returns structured JSON with subsystem status.
Used by: Docker HEALTHCHECK, Nginx upstream checks, uptime monitors.
"""
import time
import logging

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django_redis import get_redis_connection

logger = logging.getLogger(__name__)


def health_check(request):
    """
    GET /api/health/
    Returns 200 if all subsystems are reachable, 503 if any are down.
    No authentication required — this is called by infrastructure.
    """
    checks = {}
    healthy = True

    # ── Database check ────────────────────────────────────────
    db_start = time.monotonic()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = {
            "status": "connected",
            "latency_ms": round((time.monotonic() - db_start) * 1000, 1),
        }
    except Exception as e:
        logger.error("Health check: database unreachable: %s", e)
        checks["database"] = {"status": "unreachable", "error": str(e)}
        healthy = False

    # ── Redis check ───────────────────────────────────────────
    redis_start = time.monotonic()
    try:
        redis_conn = get_redis_connection("default")
        redis_conn.ping()
        checks["redis"] = {
            "status": "connected",
            "latency_ms": round((time.monotonic() - redis_start) * 1000, 1),
        }
    except Exception as e:
        logger.error("Health check: Redis unreachable: %s", e)
        checks["redis"] = {"status": "unreachable", "error": str(e)}
        healthy = False

    # ── Response ──────────────────────────────────────────────
    response_data = {
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": timezone.now().isoformat(),
        "checks": checks,
    }

    status_code = 200 if healthy else 503
    return JsonResponse(response_data, status=status_code)
```

```python
# config/urls.py (add to urlpatterns)
from apps.health.views import health_check

urlpatterns = [
    path("api/health/", health_check, name="health-check"),
    # ... other URLs
]
```

### 6.2 Responses

**Healthy (200):**

```json
{
  "status": "healthy",
  "timestamp": "2026-03-21T10:00:00.000000+00:00",
  "checks": {
    "database": {
      "status": "connected",
      "latency_ms": 1.2
    },
    "redis": {
      "status": "connected",
      "latency_ms": 0.4
    }
  }
}
```

**Unhealthy (503):**

```json
{
  "status": "unhealthy",
  "timestamp": "2026-03-21T10:00:00.000000+00:00",
  "checks": {
    "database": {
      "status": "connected",
      "latency_ms": 1.5
    },
    "redis": {
      "status": "unreachable",
      "error": "Error 111 connecting to redis:6379. Connection refused."
    }
  }
}
```

### 6.3 Using the Health Check

```bash
# Quick check from the Droplet
curl -s http://localhost:8000/api/health/ | python -m json.tool

# From outside (through Nginx)
curl -s -o /dev/null -w "%{http_code}" https://api.hireflow.io/api/health/
# Expected: 200

# Set up UptimeRobot / Pingdom / BetterUptime to poll this every 60s.
# Alert if: response code != 200, or response time > 5000ms.
```

---

## 7. Monitoring

### 7.1 What to Monitor and Alert Thresholds

#### Django (Web)

| Metric | How to Measure | Warning | Critical | Action |
|--------|---------------|---------|----------|--------|
| Response time (p95) | Nginx access log, `$request_time` | > 500ms | > 2s | Profile slow views, check DB query count |
| 5xx error rate | `grep " 5[0-9][0-9] " nginx access.log \| wc -l` | > 1% of requests | > 5% | Check Django error logs, Sentry |
| 4xx error rate | Nginx access log | > 10% | > 25% | Likely a client issue, or auth is broken |
| Gunicorn worker count | `pgrep -c gunicorn` | < 3 (expected) | 0 | Worker crash — check OOM, restart |
| Container restarts | `docker inspect --format='{{.RestartCount}}' hireflow-web-1` | > 2 in 1 hour | > 5 in 1 hour | Crash loop — check logs |

#### Celery

| Metric | How to Measure | Warning | Critical | Action |
|--------|---------------|---------|----------|--------|
| Queue depth | `redis-cli LLEN default` | > 50 | > 200 | Tasks backing up — scale workers or investigate slow tasks |
| Task failure rate | `TaskResult.objects.filter(status='FAILURE').count()` | > 5/hour | > 20/hour | Check failed task tracebacks in DB |
| Worker count | `celery inspect ping` | < expected | 0 | Worker down — restart |
| Task duration | Celery logs or `TaskResult.date_done - date_created` | > 30s | > 240s (soft limit) | Task is hung — check external deps (SMTP) |
| Tasks in STARTED state > 10min | `TaskResult.objects.filter(status='STARTED', date_created__lt=...)` | > 0 | > 5 | Stuck tasks — restart worker |

#### PostgreSQL

| Metric | How to Measure | Warning | Critical | Action |
|--------|---------------|---------|----------|--------|
| Active connections | `SELECT count(*) FROM pg_stat_activity` | > 35 | > 45 (limit 50) | Connection leak — check Django CONN_MAX_AGE |
| Slow queries (> 500ms) | `log_min_duration_statement=500` in PG config | > 10/hour | > 50/hour | Add indexes or optimize queries |
| Database size | `SELECT pg_database_size('hireflow')` | > 5 GB | > 10 GB | Audit data growth, consider archival |
| Dead tuples (bloat) | `SELECT n_dead_tup FROM pg_stat_user_tables` | > 100K on any table | > 500K | Run `VACUUM ANALYZE` |
| Replication lag | N/A (single instance v1) | — | — | Add replica when needed |

#### Redis

| Metric | How to Measure | Warning | Critical | Action |
|--------|---------------|---------|----------|--------|
| Memory usage | `redis-cli INFO memory \| grep used_memory_human` | > 80 MB | > 95 MB | Check for large keys, reduce TTLs |
| Eviction rate | `redis-cli INFO stats \| grep evicted_keys` | > 0 (growing) | > 100/min | Increase maxmemory or reduce cached data |
| Connected clients | `redis-cli INFO clients \| grep connected_clients` | > 30 | > 45 | Connection leak from Django/Celery |
| Keyspace hit ratio | `redis-cli INFO stats \| grep keyspace` | < 80% | < 50% | Cache is ineffective — review TTLs |

### 7.2 Quick Monitoring Script

```bash
#!/bin/bash
# /opt/hireflow/scripts/status.sh
# Run: bash /opt/hireflow/scripts/status.sh
set -euo pipefail
cd /opt/hireflow

echo "=== HireFlow System Status ==="
echo "Time: $(date -u)"
echo ""

echo "── Docker Containers ──"
docker compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "── Health Check ──"
curl -s http://localhost:8000/api/health/ | python3 -m json.tool
echo ""

echo "── Celery Queue Depth ──"
QUEUE_DEPTH=$(docker compose -f docker-compose.prod.yml exec -T redis redis-cli LLEN default)
echo "Tasks in queue: $QUEUE_DEPTH"
if [ "$QUEUE_DEPTH" -gt 50 ]; then echo "⚠ WARNING: Queue is backing up!"; fi
echo ""

echo "── PostgreSQL Connections ──"
docker compose -f docker-compose.prod.yml exec -T db \
  psql -U hireflow -d hireflow -t -c \
  "SELECT count(*) AS active_connections FROM pg_stat_activity WHERE state = 'active';"
echo ""

echo "── Redis Memory ──"
docker compose -f docker-compose.prod.yml exec -T redis \
  redis-cli INFO memory | grep "used_memory_human"
echo ""

echo "── Disk Usage ──"
df -h / | tail -1
echo ""

echo "── Memory ──"
free -h | head -2
echo ""

echo "── Recent Errors (last 20 lines) ──"
docker compose -f docker-compose.prod.yml logs --tail=20 web 2>&1 | grep -i "error\|500\|traceback" || echo "(none)"
```

### 7.3 Cron-Based Alerting (Low-Budget)

```bash
# /etc/cron.d/hireflow-monitor
# Check health every 5 minutes, email on failure

*/5 * * * * root curl -sf http://localhost:8000/api/health/ > /dev/null || \
  echo "HireFlow health check FAILED at $(date)" | \
  mail -s "ALERT: HireFlow DOWN" oncall@hireflow.io

# Check queue depth every 10 minutes
*/10 * * * * root DEPTH=$(docker exec hireflow-redis-1 redis-cli LLEN default 2>/dev/null); \
  [ "$DEPTH" -gt 100 ] && \
  echo "Celery queue depth: $DEPTH" | \
  mail -s "WARNING: HireFlow task queue backing up" oncall@hireflow.io
```

---

## 8. Log Aggregation

### 8.1 Structured JSON Logging Configuration

```python
# config/settings/production.py (add to or replace LOGGING)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "rename_fields": {
                "asctime": "timestamp",
                "name": "logger",
                "levelname": "level",
            },
            "static_fields": {
                "service": "hireflow-api",
            },
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",   # Set to DEBUG to log all SQL queries
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
```

**Add to requirements/production.txt:**

```
python-json-logger==2.0
```

### 8.2 What Each Log Line Contains

```json
{
  "timestamp": "2026-03-21T10:30:00.123Z",
  "logger": "apps.notifications.tasks",
  "level": "ERROR",
  "message": "Invalid task payload for send_application_received_email",
  "service": "hireflow-api",
  "exc_info": "Traceback (most recent call last):\n  ..."
}
```

| Field | Source | Purpose |
|-------|--------|---------|
| `timestamp` | Auto (ISO 8601) | When the event occurred |
| `logger` | Python module name | Which component logged it |
| `level` | DEBUG/INFO/WARNING/ERROR/CRITICAL | Severity filtering |
| `message` | Log message | What happened |
| `service` | Static field | Distinguishes HireFlow from other services if aggregated |
| `exc_info` | Exception traceback | Stack trace for errors |

### 8.3 Request Logging Middleware

```python
# middleware/request_logger.py
import time
import logging
import json

logger = logging.getLogger("apps.middleware.request")


class RequestLoggerMiddleware:
    """Logs every request with method, path, status code, user, and duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Skip health checks to avoid log noise
        if request.path == "/api/health/":
            return response

        user_id = str(request.user.id) if hasattr(request, "user") and request.user.is_authenticated else "anonymous"

        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "user_id": user_id,
                "ip": request.META.get("HTTP_X_REAL_IP", request.META.get("REMOTE_ADDR")),
            },
        )

        return response
```

**Output:**

```json
{
  "timestamp": "2026-03-21T10:30:00.456Z",
  "logger": "apps.middleware.request",
  "level": "INFO",
  "message": "request completed",
  "method": "POST",
  "path": "/api/applications/",
  "status": 201,
  "duration_ms": 87.3,
  "user_id": "a1b2c3d4-e5f6-...",
  "ip": "203.0.113.42",
  "service": "hireflow-api"
}
```

### 8.4 Celery Worker Log Configuration

```python
# config/celery.py (add after app definition)
from celery.signals import setup_logging

@setup_logging.connect
def configure_celery_logging(sender=None, **kwargs):
    """
    Override Celery's default logging to use Django's JSON config.
    Without this, Celery uses its own formatter and ignores LOGGING.
    """
    import logging.config
    from django.conf import settings
    logging.config.dictConfig(settings.LOGGING)
```

### 8.5 Viewing Logs

```bash
# All web logs (last 100 lines)
docker compose -f docker-compose.prod.yml logs --tail=100 web

# Celery logs
docker compose -f docker-compose.prod.yml logs --tail=100 celery

# Follow logs in real-time (all services)
docker compose -f docker-compose.prod.yml logs -f

# Filter for errors only
docker compose -f docker-compose.prod.yml logs web 2>&1 | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        entry = json.loads(line.split('| ', 1)[-1])
        if entry.get('level') in ('ERROR', 'CRITICAL'):
            print(json.dumps(entry, indent=2))
    except (json.JSONDecodeError, IndexError):
        if 'error' in line.lower():
            print(line.strip())
"

# Logs since a specific time
docker compose -f docker-compose.prod.yml logs --since="2026-03-21T10:00:00" web
```

---

## 9. Rollback Procedure

### 9.1 Decision: Do I Need to Roll Back?

```
Deploy just went out. Something is wrong.
│
├── 5xx errors spiking?
│   → YES: Rollback code immediately (9.2)
│
├── Celery tasks failing?
│   → Check if it's a code issue or an external dependency (SMTP down)
│   → Code issue: Rollback (9.2)
│   → External: Fix the external service, tasks will auto-retry
│
├── Database migration failed midway?
│   → See 9.3 (Migration Rollback)
│
├── Performance degraded but not erroring?
│   → Check slow query log
│   → May be a missing index — deploy a fix forward, not a rollback
│
└── Feature bug (not crashing, just wrong behavior)?
    → Fix forward if possible (faster than rollback)
    → Rollback if the fix is complex and users are impacted
```

### 9.2 Rolling Back Code (No Migration Changes)

```bash
cd /opt/hireflow

# ── Step 1: Find the previous commit ─────────────────────────
cat deploy.log | tail -5
# 2026-03-21T10:00:00Z abc1234
# 2026-03-21T10:05:00Z def5678  ← current (broken)

ROLLBACK_TO="abc1234"

# ── Step 2: Checkout the old code ─────────────────────────────
git checkout $ROLLBACK_TO

# ── Step 3: Rebuild and restart ───────────────────────────────
docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml up -d --no-deps web
docker compose -f docker-compose.prod.yml restart celery celery-beat

# ── Step 4: Verify ───────────────────────────────────────────
curl -s https://api.hireflow.io/api/health/
echo ""
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ROLLBACK to $ROLLBACK_TO" >> deploy.log
echo "Rollback complete. Verify manually that the issue is resolved."

# ── Step 5: Return to main branch (after fixing the issue) ───
# git checkout main  ← do this AFTER you've pushed a fix
```

### 9.3 Rolling Back a Database Migration

**Important:** Not all migrations are reversible. Django generates reverse operations automatically for `AddField`, `CreateModel`, etc. But `RunPython` data migrations need an explicit reverse function.

```bash
# ── Step 1: Check which migrations are applied ───────────────
docker compose -f docker-compose.prod.yml exec web \
  python manage.py showmigrations jobs
# Expected output:
# [X] 0001_initial
# [X] 0002_add_search_vector
# [X] 0003_add_is_deleted          ← this is the one we want to undo

# ── Step 2: Reverse to the previous migration ────────────────
docker compose -f docker-compose.prod.yml run --rm web \
  python manage.py migrate jobs 0002_add_search_vector

# Expected: "Unapplying jobs.0003_add_is_deleted... OK"
#
# If you see "IrreversibleError" → the migration has no reverse.
# In that case: fix forward, do NOT try to manually undo SQL.

# ── Step 3: Roll back the code (includes the reversed migration file)
git checkout $ROLLBACK_TO
docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml up -d --no-deps web
```

### 9.4 When You Can't Reverse a Migration

If a migration dropped data (e.g., `RemoveField`, `DeleteModel`) and there's no reverse:

```
1. STOP. Do not panic.
2. Check if you have a backup from BEFORE the deploy (see Section 10).
3. If the data loss is limited to one table/column:
   a. Restore the backup to a TEMPORARY database
   b. Export just the affected data:
      pg_dump -U hireflow -d hireflow_backup -t jobs_job --column-inserts > fix.sql
   c. Selectively import into production
4. If the data loss is catastrophic:
   a. Full restore from backup (see Section 10.3)
   b. This will lose all data written AFTER the backup was taken
5. Post-incident: add a reverse function to every RunPython migration going forward.
```

---

## 10. Backup Strategy

### 10.1 Automated Daily Backups

```bash
#!/bin/bash
# /opt/hireflow/scripts/backup.sh
# Run via cron: 0 3 * * * /opt/hireflow/scripts/backup.sh
set -euo pipefail

BACKUP_DIR="/opt/hireflow/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/hireflow_${TIMESTAMP}.sql.gz"
RETENTION_DAYS=14

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

echo "[$(date -u)] Starting PostgreSQL backup..."

# Dump the database (compressed)
docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  pg_dump -U hireflow -d hireflow \
    --format=custom \
    --compress=6 \
    --verbose \
  > "${BACKUP_DIR}/hireflow_${TIMESTAMP}.dump" 2>/tmp/backup_stderr.log

DUMP_FILE="${BACKUP_DIR}/hireflow_${TIMESTAMP}.dump"
DUMP_SIZE=$(du -h "$DUMP_FILE" | cut -f1)
echo "[$(date -u)] Backup complete: $DUMP_FILE ($DUMP_SIZE)"

# ── Also create a plain SQL backup (useful for single-table restores) ──
docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  pg_dump -U hireflow -d hireflow --format=plain \
  | gzip > "$BACKUP_FILE"
echo "[$(date -u)] SQL backup: $BACKUP_FILE"

# ── Upload to DigitalOcean Spaces (off-site backup) ──────────
# Requires: apt install s3cmd && s3cmd --configure
if command -v s3cmd &> /dev/null; then
  s3cmd put "$DUMP_FILE" s3://hireflow-backups/db/
  echo "[$(date -u)] Uploaded to DigitalOcean Spaces"
else
  echo "[$(date -u)] WARNING: s3cmd not installed, skipping off-site backup"
fi

# ── Clean up old local backups ────────────────────────────────
find "$BACKUP_DIR" -name "hireflow_*.dump" -mtime +${RETENTION_DAYS} -delete
find "$BACKUP_DIR" -name "hireflow_*.sql.gz" -mtime +${RETENTION_DAYS} -delete
REMAINING=$(ls -1 "$BACKUP_DIR"/hireflow_*.dump 2>/dev/null | wc -l)
echo "[$(date -u)] Cleanup done. $REMAINING backups retained (${RETENTION_DAYS}-day window)."
```

### 10.2 Cron Schedule

```bash
# /etc/cron.d/hireflow-backup
# Daily backup at 3:00 AM UTC
0 3 * * * root /opt/hireflow/scripts/backup.sh >> /var/log/hireflow-backup.log 2>&1

# Pre-deploy backup (call manually before risky deploys)
# bash /opt/hireflow/scripts/backup.sh
```

### 10.3 Restore Procedure

#### Full Restore (Disaster Recovery)

```bash
# ── Step 1: Identify the backup to restore ────────────────────
ls -lah /opt/hireflow/backups/
# hireflow_20260320_030000.dump   45M   Mar 20 03:00
# hireflow_20260321_030000.dump   46M   Mar 21 03:00  ← latest

RESTORE_FILE="/opt/hireflow/backups/hireflow_20260321_030000.dump"

# ── Step 2: Stop Django and Celery (prevent writes during restore) ─
cd /opt/hireflow
docker compose -f docker-compose.prod.yml stop web celery celery-beat
# db and redis keep running

# ── Step 3: Drop and recreate the database ────────────────────
docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = 'hireflow' AND pid <> pg_backend_pid();
  "

docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d postgres -c "DROP DATABASE hireflow;"

docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d postgres -c "CREATE DATABASE hireflow OWNER hireflow;"

# ── Step 4: Restore from backup ──────────────────────────────
docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U hireflow -d hireflow --verbose "$RESTORE_FILE"

# Expected: lots of "CREATE TABLE", "COPY", "CREATE INDEX" lines
# If you see errors about "already exists" → the drop didn't work. Re-check step 3.

# ── Step 5: Restart all services ──────────────────────────────
docker compose -f docker-compose.prod.yml up -d web celery celery-beat

# ── Step 6: Verify ───────────────────────────────────────────
curl -s http://localhost:8000/api/health/ | python3 -m json.tool
echo ""
echo "Checking row counts..."
docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d hireflow -c "
    SELECT 'users' AS table_name, count(*) FROM accounts_user
    UNION ALL SELECT 'companies', count(*) FROM companies_company
    UNION ALL SELECT 'jobs', count(*) FROM jobs_job
    UNION ALL SELECT 'applications', count(*) FROM applications_application;
  "
```

#### Single Table Restore (Partial Recovery)

```bash
# Useful when you accidentally deleted data from one table.

RESTORE_FILE="/opt/hireflow/backups/hireflow_20260321_030000.dump"

# Restore ONLY the applications table into a temporary database
docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d postgres -c "CREATE DATABASE hireflow_temp OWNER hireflow;"

docker compose -f docker-compose.prod.yml exec -T db \
  pg_restore -U hireflow -d hireflow_temp --table=applications_application "$RESTORE_FILE"

# Copy the missing data from temp to production
docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d hireflow -c "
    INSERT INTO applications_application
    SELECT * FROM dblink(
      'dbname=hireflow_temp user=hireflow',
      'SELECT * FROM applications_application'
    ) AS t(/* column list matching your schema */)
    ON CONFLICT (id) DO NOTHING;
  "

# Clean up
docker compose -f docker-compose.prod.yml exec db \
  psql -U hireflow -d postgres -c "DROP DATABASE hireflow_temp;"
```

### 10.4 Testing Backups (Monthly)

**A backup you haven't tested is not a backup.** Run this monthly:

```bash
#!/bin/bash
# /opt/hireflow/scripts/test-backup.sh
# Verifies the latest backup can be restored successfully.
set -euo pipefail

LATEST_BACKUP=$(ls -t /opt/hireflow/backups/hireflow_*.dump | head -1)
echo "Testing backup: $LATEST_BACKUP"

# Create a test database
docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  psql -U hireflow -d postgres -c "DROP DATABASE IF EXISTS hireflow_backup_test;"

docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  psql -U hireflow -d postgres -c "CREATE DATABASE hireflow_backup_test OWNER hireflow;"

# Restore into test database
echo "Restoring..."
docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  pg_restore -U hireflow -d hireflow_backup_test --verbose "$LATEST_BACKUP" 2>/dev/null

# Verify row counts
echo ""
echo "Row counts in restored database:"
docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  psql -U hireflow -d hireflow_backup_test -c "
    SELECT 'users' AS tbl, count(*) FROM accounts_user
    UNION ALL SELECT 'companies', count(*) FROM companies_company
    UNION ALL SELECT 'jobs', count(*) FROM jobs_job
    UNION ALL SELECT 'applications', count(*) FROM applications_application
    UNION ALL SELECT 'notifications', count(*) FROM notifications_notification;
  "

# Clean up
docker compose -f /opt/hireflow/docker-compose.prod.yml exec -T db \
  psql -U hireflow -d postgres -c "DROP DATABASE hireflow_backup_test;"

echo ""
echo "Backup test PASSED. Restore completed successfully."
```

Add to cron:

```bash
# /etc/cron.d/hireflow-backup-test
# Test backup integrity on the 1st of every month at 4:00 AM UTC
0 4 1 * * root /opt/hireflow/scripts/test-backup.sh >> /var/log/hireflow-backup-test.log 2>&1
```

---

## Appendix A: Initial Server Setup (One-Time)

```bash
# Run as root on a fresh Ubuntu 22.04 Droplet

# ── System updates ────────────────────────────────────────────
apt update && apt upgrade -y

# ── Install Docker ────────────────────────────────────────────
curl -fsSL https://get.docker.com | sh
systemctl enable docker

# ── Install Docker Compose v2 ─────────────────────────────────
apt install -y docker-compose-plugin
docker compose version  # Expected: Docker Compose version v2.x.x

# ── Create app directory ──────────────────────────────────────
mkdir -p /opt/hireflow/backups
cd /opt/hireflow

# ── Clone repository ──────────────────────────────────────────
git clone https://github.com/yourorg/hireflow.git .

# ── Create .env from example ─────────────────────────────────
cp .env.example .env
# Edit .env with production values (see Section 2)
nano .env
chmod 600 .env

# ── Firewall ──────────────────────────────────────────────────
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (redirect to HTTPS)
ufw allow 443/tcp   # HTTPS
ufw --force enable

# ── Set up swap (2 GB — safety net for RAM spikes) ────────────
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# ── TLS certificate (Let's Encrypt) ──────────────────────────
apt install -y certbot
# Start nginx first without SSL, then:
certbot certonly --webroot -w /opt/hireflow/certbot/www \
  -d api.hireflow.io --non-interactive --agree-tos -m admin@hireflow.io

# Auto-renew
echo "0 0 1 * * root certbot renew --quiet && docker compose -f /opt/hireflow/docker-compose.prod.yml restart nginx" \
  > /etc/cron.d/certbot-renew

# ── First deploy ──────────────────────────────────────────────
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
docker compose -f docker-compose.prod.yml up -d

# ── Set up backup cron ────────────────────────────────────────
chmod +x /opt/hireflow/scripts/backup.sh
# Copy cron entries from Sections 10.2 and 10.4

echo "Server setup complete."
```

---

## Appendix B: Emergency Quick Reference

**Print this. Tape it to your monitor.**

```
╔══════════════════════════════════════════════════════════════════╗
║                  HIREFLOW EMERGENCY RUNBOOK                     ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  SSH:   ssh root@<droplet-ip>                                    ║
║  Dir:   cd /opt/hireflow                                         ║
║                                                                  ║
║  STATUS                                                          ║
║    bash scripts/status.sh                                        ║
║    docker compose -f docker-compose.prod.yml ps                  ║
║    curl localhost:8000/api/health/                                ║
║                                                                  ║
║  LOGS                                                            ║
║    docker compose -f docker-compose.prod.yml logs -f web         ║
║    docker compose -f docker-compose.prod.yml logs -f celery      ║
║                                                                  ║
║  RESTART A SERVICE                                               ║
║    docker compose -f docker-compose.prod.yml restart <service>   ║
║    Services: web, celery, celery-beat, db, redis, nginx          ║
║                                                                  ║
║  RESTART EVERYTHING                                              ║
║    docker compose -f docker-compose.prod.yml down                ║
║    docker compose -f docker-compose.prod.yml up -d               ║
║                                                                  ║
║  ROLLBACK CODE                                                   ║
║    cat deploy.log | tail -5           (find previous commit)     ║
║    git checkout <commit>                                         ║
║    docker compose -f docker-compose.prod.yml build web           ║
║    docker compose -f docker-compose.prod.yml up -d web           ║
║    docker compose -f docker-compose.prod.yml restart celery      ║
║                                                                  ║
║  ROLLBACK MIGRATION                                              ║
║    python manage.py showmigrations <app>                         ║
║    python manage.py migrate <app> <previous_migration_name>      ║
║                                                                  ║
║  CELERY QUEUE STUCK                                              ║
║    redis-cli LLEN default             (check queue depth)        ║
║    celery -A config inspect active    (check running tasks)      ║
║    docker compose restart celery      (restart worker)           ║
║    redis-cli DEL default              (NUCLEAR: flush queue)     ║
║                                                                  ║
║  RESTORE FROM BACKUP                                             ║
║    See Section 10.3                                              ║
║    Backup dir: /opt/hireflow/backups/                            ║
║                                                                  ║
║  TAKE A BACKUP RIGHT NOW                                         ║
║    bash /opt/hireflow/scripts/backup.sh                          ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```
