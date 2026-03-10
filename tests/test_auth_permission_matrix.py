"""
Section 3 — Authentication & Permission Matrix.

Parametrized matrix covering every endpoint × HTTP method × actor combination.
Actors: anonymous, candidate, recruiter (non-member), recruiter (member/owner), admin.

Any deviation from the expected status code is a potential security gap.
"""

import pytest
from rest_framework.test import APIClient

from tests.factories import (
    ApplicationFactory,
    CompanyMemberFactory,
    JobFactory,
    NotificationFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Fixtures — set up the full object graph once per class
# ---------------------------------------------------------------------------


@pytest.fixture()
def world():
    """Build the complete object graph needed by all permission tests."""
    # Owner recruiter + company
    owner_membership = CompanyMemberFactory(role="owner")
    owner = owner_membership.user
    company = owner_membership.company

    # Member recruiter (invited, not owner)
    member = UserFactory(role="recruiter")
    from apps.companies.models import CompanyMember

    CompanyMember.objects.create(user=member, company=company, role="recruiter")

    # Outsider recruiter (no membership in this company)
    outsider_recruiter = UserFactory(role="recruiter")

    # Candidate
    candidate = UserFactory(role="candidate")

    # Admin
    admin = UserFactory(role="admin")

    # Published job owned by the company
    job = JobFactory(status="published", company=company, posted_by=owner)

    # Draft job for publish tests
    draft_job = JobFactory(status="draft", company=company, posted_by=owner)

    # Application by the candidate on the published job
    application = ApplicationFactory(job=job, applicant=candidate)

    # Notification for the candidate
    notification = NotificationFactory(user=candidate)

    return {
        "owner": owner,
        "member": member,
        "outsider_recruiter": outsider_recruiter,
        "candidate": candidate,
        "admin": admin,
        "company": company,
        "job": job,
        "draft_job": draft_job,
        "application": application,
        "notification": notification,
    }


def _client_for(user=None):
    """Return an APIClient, optionally authenticated."""
    c = APIClient()
    if user is not None:
        c.force_authenticate(user=user)
    return c


# ---------------------------------------------------------------------------
# The matrix: (endpoint_key, method, url_func, actors→expected_status)
# ---------------------------------------------------------------------------
# actor keys: anon, candidate, outsider, member, owner, admin

# We use callables so URLs can reference the world fixture at runtime.


def _url_companies_list(_w):
    return "/api/companies/"


def _url_company_detail(w):
    return f"/api/companies/{w['company'].slug}/"


def _url_company_invite(w):
    return f"/api/companies/{w['company'].slug}/members/"


def _url_jobs_list(_w):
    return "/api/jobs/"


def _url_job_detail(w):
    return f"/api/jobs/{w['job'].slug}/"


def _url_job_publish(w):
    return f"/api/jobs/{w['draft_job'].slug}/publish/"


def _url_job_close(w):
    return f"/api/jobs/{w['job'].slug}/close/"


def _url_job_search(_w):
    return "/api/jobs/search/?q=python"


def _url_applications_list(_w):
    return "/api/applications/"


def _url_application_delete(w):
    return f"/api/applications/{w['application'].id}/"


def _url_application_status(w):
    return f"/api/applications/{w['application'].id}/status/"


def _url_notifications_list(_w):
    return "/api/notifications/"


def _url_notification_mark_read(w):
    return f"/api/notifications/{w['notification'].id}/read/"


def _url_notification_mark_all_read(_w):
    return "/api/notifications/mark-all-read/"


def _url_dashboard_recruiter(_w):
    return "/api/dashboard/recruiter/"


def _url_dashboard_candidate(_w):
    return "/api/dashboard/candidate/"


# Expectations:
# 401 = unauthenticated
# 403 = authenticated but wrong role / not authorized
# 200/201/204 = success
# 400 = valid auth but bad request data (still "authorized")
# 404 = authorized but object not found / scoped away

# We mark expected codes per actor.
# For POST endpoints that require data, we use minimal valid data or expect
# 400 for auth'd users who pass permission checks but submit incomplete data.

MATRIX = [
    # ── Companies ──
    {
        "id": "GET /api/companies/",
        "method": "get",
        "url": _url_companies_list,
        "anon": 200,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    {
        "id": "POST /api/companies/",
        "method": "post",
        "url": _url_companies_list,
        "data": {
            "name": "Matrix Corp",
            "slug": "matrix-corp-perm",
            "description": "Test",
            "industry": "Tech",
            "location": "Remote",
        },
        "anon": 401,
        "candidate": 403,
        "outsider": 201,  # any recruiter can create
        "member": 201,
        "owner": 201,
        "admin": 403,  # admin role is not recruiter
    },
    {
        "id": "GET /api/companies/{slug}/",
        "method": "get",
        "url": _url_company_detail,
        "anon": 200,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    {
        "id": "PATCH /api/companies/{slug}/",
        "method": "patch",
        "url": _url_company_detail,
        "data": {"description": "Updated"},
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 403,  # only owner can update
        "owner": 200,
        "admin": 403,
    },
    {
        "id": "POST /api/companies/{slug}/members/",
        "method": "post",
        "url": _url_company_invite,
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 403,  # only owner can invite
        "owner": 400,  # owner is authorized but no valid email data sent
        "admin": 403,
    },
    # ── Jobs ──
    {
        "id": "GET /api/jobs/",
        "method": "get",
        "url": _url_jobs_list,
        "anon": 200,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    {
        "id": "POST /api/jobs/",
        "method": "post",
        "url": _url_jobs_list,
        "anon": 401,
        "candidate": 403,
        "outsider": 400,  # recruiter passes perm, but no data → validation error
        "member": 400,
        "owner": 400,
        "admin": 403,
    },
    {
        "id": "GET /api/jobs/{slug}/",
        "method": "get",
        "url": _url_job_detail,
        "anon": 200,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    {
        "id": "PATCH /api/jobs/{slug}/",
        "method": "patch",
        "url": _url_job_detail,
        "data": {"description": "Updated job desc"},
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 200,
        "owner": 200,
        "admin": 403,
    },
    {
        "id": "POST /api/jobs/{slug}/publish/",
        "method": "post",
        "url": _url_job_publish,
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 200,
        "owner": 200,
        "admin": 403,
    },
    {
        "id": "POST /api/jobs/{slug}/close/",
        "method": "post",
        "url": _url_job_close,
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 200,
        "owner": 200,
        "admin": 403,
    },
    {
        "id": "GET /api/jobs/search/?q=python",
        "method": "get",
        "url": _url_job_search,
        "anon": 200,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    # ── Applications ──
    {
        "id": "GET /api/applications/",
        "method": "get",
        "url": _url_applications_list,
        "anon": 401,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    {
        "id": "POST /api/applications/",
        "method": "post",
        "url": _url_applications_list,
        "anon": 401,
        "candidate": 400,  # passes perm but no data
        "outsider": 403,
        "member": 403,
        "owner": 403,
        "admin": 403,
    },
    {
        "id": "DELETE /api/applications/{id}/ (candidate owner)",
        "method": "delete",
        "url": _url_application_delete,
        "anon": 401,
        "candidate": 200,  # owns the application
        "outsider": 404,  # scoped queryset returns nothing
        "member": 403,  # recruiter sees it (company's job) but isn't the applicant
        "owner": 403,  # same: sees it but can't withdraw for someone else
        "admin": 404,  # not candidate, not recruiter → empty queryset
    },
    {
        "id": "PATCH /api/applications/{id}/status/",
        "method": "patch",
        "url": _url_application_status,
        "data": {"status": "reviewing"},
        "anon": 401,
        "candidate": 404,
        "outsider": 404,
        "member": 200,
        "owner": 200,
        "admin": 404,
    },
    # ── Notifications ──
    {
        "id": "GET /api/notifications/",
        "method": "get",
        "url": _url_notifications_list,
        "anon": 401,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    {
        "id": "PATCH /api/notifications/{id}/read/",
        "method": "patch",
        "url": _url_notification_mark_read,
        "anon": 401,
        "candidate": 200,  # owns the notification
        "outsider": 404,  # scoped queryset
        "member": 404,
        "owner": 404,
        "admin": 404,
    },
    {
        "id": "POST /api/notifications/mark-all-read/",
        "method": "post",
        "url": _url_notification_mark_all_read,
        "anon": 401,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    # ── Dashboard ──
    {
        "id": "GET /api/dashboard/recruiter/",
        "method": "get",
        "url": _url_dashboard_recruiter,
        "anon": 401,
        "candidate": 403,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 403,
    },
    {
        "id": "GET /api/dashboard/candidate/",
        "method": "get",
        "url": _url_dashboard_candidate,
        "anon": 401,
        "candidate": 200,
        "outsider": 403,
        "member": 403,
        "owner": 403,
        "admin": 403,
    },
]


def _build_test_params():
    """Yield (endpoint_id, actor_name, method, url_fn, data, expected) tuples."""
    actors = ["anon", "candidate", "outsider", "member", "owner", "admin"]
    for spec in MATRIX:
        for actor in actors:
            yield pytest.param(
                spec["id"],
                actor,
                spec["method"],
                spec["url"],
                spec.get("data"),
                spec[actor],
                id=f"{spec['id']} [{actor}]",
            )


@pytest.mark.django_db
class TestPermissionMatrix:
    """Exhaustive permission matrix: every endpoint × every actor."""

    @pytest.mark.parametrize(
        "endpoint_id,actor,method,url_fn,data,expected",
        list(_build_test_params()),
    )
    def test_permission(self, world, endpoint_id, actor, method, url_fn, data, expected):
        """Assert exact HTTP status code for endpoint={endpoint_id}, actor={actor}."""
        user_map = {
            "anon": None,
            "candidate": world["candidate"],
            "outsider": world["outsider_recruiter"],
            "member": world["member"],
            "owner": world["owner"],
            "admin": world["admin"],
        }
        client = _client_for(user_map[actor])
        url = url_fn(world)

        # Slug uniqueness: POST /api/companies/ with duplicate slug across actors
        # Give each actor a unique slug to avoid collisions
        if data and "slug" in data:
            data = {**data, "slug": f"{data['slug']}-{actor}"}

        kwargs = {"format": "json"}
        if data is not None:
            kwargs["data"] = data

        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == expected, (
            f"\n  Endpoint: {endpoint_id}"
            f"\n  Actor:    {actor}"
            f"\n  Expected: {expected}"
            f"\n  Got:      {response.status_code}"
            f"\n  Body:     {response.data if hasattr(response, 'data') else ''}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Gap coverage: additional endpoint permissions
# ═══════════════════════════════════════════════════════════════════════════


def _url_company_delete(w):
    return f"/api/companies/{w['company'].slug}/"


def _url_company_members_list(w):
    return f"/api/companies/{w['company'].slug}/members/"


def _url_auth_current_user(_w):
    return "/api/auth/me/"


def _url_health(_w):
    return "/api/health/"


EXTRA_MATRIX = [
    # ── Company delete ──
    {
        "id": "DELETE /api/companies/{slug}/",
        "method": "delete",
        "url": _url_company_delete,
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 403,  # only owner
        "owner": 204,
        "admin": 403,
    },
    # ── Member listing ──
    {
        "id": "GET /api/companies/{slug}/members/",
        "method": "get",
        "url": _url_company_members_list,
        "anon": 401,
        "candidate": 403,
        "outsider": 403,
        "member": 200,
        "owner": 200,
        "admin": 403,
    },
    # ── Health (public) ──
    {
        "id": "GET /api/health/",
        "method": "get",
        "url": _url_health,
        "anon": 200,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
    # ── Current user ──
    {
        "id": "GET /api/auth/me/",
        "method": "get",
        "url": _url_auth_current_user,
        "anon": 401,
        "candidate": 200,
        "outsider": 200,
        "member": 200,
        "owner": 200,
        "admin": 200,
    },
]


def _build_extra_params():
    actors = ["anon", "candidate", "outsider", "member", "owner", "admin"]
    for spec in EXTRA_MATRIX:
        for actor in actors:
            yield pytest.param(
                spec["id"],
                actor,
                spec["method"],
                spec["url"],
                spec.get("data"),
                spec[actor],
                id=f"{spec['id']} [{actor}]",
            )


@pytest.mark.django_db
class TestExtraPermissions:
    """Additional endpoint permission coverage not in the main matrix."""

    @pytest.mark.parametrize(
        "endpoint_id,actor,method,url_fn,data,expected",
        list(_build_extra_params()),
    )
    def test_extra_permission(
        self, world, endpoint_id, actor, method, url_fn, data, expected
    ):
        """Assert exact HTTP status code for extra endpoints."""
        user_map = {
            "anon": None,
            "candidate": world["candidate"],
            "outsider": world["outsider_recruiter"],
            "member": world["member"],
            "owner": world["owner"],
            "admin": world["admin"],
        }
        client = _client_for(user_map[actor])
        url = url_fn(world)

        kwargs = {"format": "json"}
        if data is not None:
            kwargs["data"] = data

        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == expected, (
            f"\n  Endpoint: {endpoint_id}"
            f"\n  Actor:    {actor}"
            f"\n  Expected: {expected}"
            f"\n  Got:      {response.status_code}"
            f"\n  Body:     {response.data if hasattr(response, 'data') else ''}"
        )
