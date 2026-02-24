"""
Section 2 — State-Machine & Workflow Integrity tests.

Covers:
  2.1  Every edge in VALID_TRANSITIONS (valid + invalid)
  2.2  Application boundary conditions (deadline, job status, duplicates)
  2.3  Withdraw semantics (WITHDRAWABLE_STATUSES, non-withdrawable, soft delete)
  2.4  Signal integrity (email fires exactly once per event, never spuriously)
"""

import datetime

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.applications.models import Application
from tests.factories import (
    ApplicationFactory,
    CompanyMemberFactory,
    JobFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

ALL_STATUSES = {s.value for s in Application.Status}
TERMINAL_STATUSES = {"rejected", "withdrawn"}


def _status_url(app_id):
    return f"/api/applications/{app_id}/status/"


def _make_recruiter_and_application(initial_status="applied"):
    """Create a company owner + published job + application at given status."""
    membership = CompanyMemberFactory(role="owner")
    job = JobFactory(status="published", company=membership.company)
    app = ApplicationFactory(job=job, status=initial_status)
    client = APIClient()
    client.force_authenticate(user=membership.user)
    return client, app


def _make_candidate_client_and_application(initial_status="applied"):
    """Create a candidate + published job + application at given status."""
    membership = CompanyMemberFactory(role="owner")
    job = JobFactory(status="published", company=membership.company)
    candidate = UserFactory(role="candidate")
    app = ApplicationFactory(job=job, applicant=candidate, status=initial_status)
    client = APIClient()
    client.force_authenticate(user=candidate)
    return client, app


# ═══════════════════════════════════════════════════════════════════════════
# 2.1  VALID_TRANSITIONS — one test per edge
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestValidTransitions:
    """Every allowed source→target edge returns 200 and persists."""

    @pytest.mark.parametrize(
        "source,target",
        [
            ("applied", "reviewing"),
            ("applied", "rejected"),
            ("reviewing", "shortlisted"),
            ("reviewing", "rejected"),
            ("shortlisted", "interview"),
            ("shortlisted", "rejected"),
            ("interview", "offered"),
            ("interview", "rejected"),
            ("offered", "rejected"),
        ],
    )
    def test_valid_transition_succeeds(self, source, target):
        client, app = _make_recruiter_and_application(initial_status=source)
        resp = client.patch(
            _status_url(app.id), {"status": target}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == target


@pytest.mark.django_db
class TestInvalidTransitions:
    """Every disallowed source→target pair returns 400 with informative error."""

    @pytest.mark.parametrize(
        "source,target",
        [
            # applied → cannot skip ahead
            ("applied", "shortlisted"),
            ("applied", "interview"),
            ("applied", "offered"),
            ("applied", "applied"),
            ("applied", "withdrawn"),
            # reviewing → cannot skip or regress
            ("reviewing", "applied"),
            ("reviewing", "interview"),
            ("reviewing", "offered"),
            ("reviewing", "reviewing"),
            ("reviewing", "withdrawn"),
            # shortlisted → cannot skip or regress
            ("shortlisted", "applied"),
            ("shortlisted", "reviewing"),
            ("shortlisted", "offered"),
            ("shortlisted", "shortlisted"),
            ("shortlisted", "withdrawn"),
            # interview → cannot regress
            ("interview", "applied"),
            ("interview", "reviewing"),
            ("interview", "shortlisted"),
            ("interview", "interview"),
            ("interview", "withdrawn"),
            # offered → only rejected is allowed
            ("offered", "applied"),
            ("offered", "reviewing"),
            ("offered", "shortlisted"),
            ("offered", "interview"),
            ("offered", "offered"),
            ("offered", "withdrawn"),
            # terminal states have NO outgoing edges
            ("rejected", "applied"),
            ("rejected", "reviewing"),
            ("rejected", "shortlisted"),
            ("rejected", "interview"),
            ("rejected", "offered"),
            ("rejected", "rejected"),
            ("rejected", "withdrawn"),
            ("withdrawn", "applied"),
            ("withdrawn", "reviewing"),
            ("withdrawn", "shortlisted"),
            ("withdrawn", "interview"),
            ("withdrawn", "offered"),
            ("withdrawn", "rejected"),
            ("withdrawn", "withdrawn"),
        ],
    )
    def test_invalid_transition_returns_400(self, source, target):
        client, app = _make_recruiter_and_application(initial_status=source)
        resp = client.patch(
            _status_url(app.id), {"status": target}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        # DB should be unchanged
        app.refresh_from_db()
        assert app.status == source


# ═══════════════════════════════════════════════════════════════════════════
# 2.2  Boundary conditions
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestApplicationBoundaryConditions:
    """Deadline, job status, and duplicate constraints."""

    def _apply(self, client, job_id):
        resume = SimpleUploadedFile(
            "resume.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        return client.post(
            "/api/applications/",
            {"job": str(job_id), "resume": resume},
            format="multipart",
        )

    def test_apply_deadline_today_allowed(self):
        """Deadline == today means the job is still open."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(
            status="published",
            company=membership.company,
            deadline=timezone.now().date(),
        )
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = self._apply(client, job.id)
        assert resp.status_code == status.HTTP_201_CREATED

    def test_apply_deadline_yesterday_rejected(self):
        """Deadline == yesterday → 400."""
        membership = CompanyMemberFactory(role="owner")
        yesterday = timezone.now().date() - datetime.timedelta(days=1)
        job = JobFactory(
            status="published",
            company=membership.company,
            deadline=yesterday,
        )
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = self._apply(client, job.id)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_apply_to_closed_job_rejected(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="closed", company=membership.company)
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = self._apply(client, job.id)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_apply_to_draft_job_rejected(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="draft", company=membership.company)
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = self._apply(client, job.id)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_application_rejected(self):
        """Boundary audit: same candidate + same job → 400.

        Layered coverage: apps/applications/tests/test_views.py::TestCreateApplication
        has a unit version that tests via sequential HTTP POSTs. This version
        pre-creates via factory to isolate the constraint check.
        """
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        candidate = UserFactory(role="candidate")
        ApplicationFactory(job=job, applicant=candidate)
        client = APIClient()
        client.force_authenticate(user=candidate)
        resp = self._apply(client, job.id)
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ═══════════════════════════════════════════════════════════════════════════
# 2.3  Withdraw semantics
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWithdrawSemantics:
    """Withdraw is a soft-delete (status → withdrawn), not a hard delete."""

    @pytest.mark.parametrize("withdrawable_status", sorted(Application.WITHDRAWABLE_STATUSES))
    def test_can_withdraw_from_withdrawable_status(self, withdrawable_status):
        client, app = _make_candidate_client_and_application(
            initial_status=withdrawable_status,
        )
        resp = client.delete(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == "withdrawn"

    @pytest.mark.parametrize(
        "non_withdrawable_status",
        sorted(ALL_STATUSES - Application.WITHDRAWABLE_STATUSES),
    )
    def test_cannot_withdraw_from_non_withdrawable_status(self, non_withdrawable_status):
        client, app = _make_candidate_client_and_application(
            initial_status=non_withdrawable_status,
        )
        resp = client.delete(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        app.refresh_from_db()
        assert app.status == non_withdrawable_status  # unchanged

    def test_withdraw_is_soft_delete_record_persists(self):
        """After withdrawal the Application row still exists in DB."""
        client, app = _make_candidate_client_and_application(initial_status="applied")
        resp = client.delete(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_200_OK
        assert Application.objects.filter(pk=app.pk).exists()
        app.refresh_from_db()
        assert app.status == "withdrawn"


# ═══════════════════════════════════════════════════════════════════════════
# 2.4  Signal integrity
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSignalIntegrity:
    """
    Signals must fire exactly once for the right event:
      - creation email on POST /api/applications/ only
      - status-change email on PATCH status only
      - no email when save does not change status
    """

    def test_creation_email_fires_once_on_apply(self):
        """POST /api/applications/ → exactly 1 "Application received" email."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        mail.outbox.clear()
        resume = SimpleUploadedFile(
            "resume.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        resp = client.post(
            "/api/applications/",
            {"job": str(job.id), "resume": resume},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        received_emails = [
            e for e in mail.outbox if "Application received" in e.subject
        ]
        assert len(received_emails) == 1

    def test_status_change_email_fires_once_per_transition(self):
        """PATCH status → exactly 1 "status has been updated" email."""
        client, app = _make_recruiter_and_application(initial_status="applied")
        mail.outbox.clear()
        resp = client.patch(
            _status_url(app.id), {"status": "reviewing"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        status_emails = [
            e for e in mail.outbox if "status has been updated" in e.subject
        ]
        assert len(status_emails) == 1

    def test_creation_does_not_fire_status_change_email(self):
        """POST /api/applications/ must NOT produce a status-change email."""
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        mail.outbox.clear()
        resume = SimpleUploadedFile(
            "resume.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        client.post(
            "/api/applications/",
            {"job": str(job.id), "resume": resume},
            format="multipart",
        )
        status_emails = [
            e for e in mail.outbox if "status has been updated" in e.subject
        ]
        assert len(status_emails) == 0

    def test_save_without_status_change_fires_no_email(self):
        """Saving recruiter_notes without changing status → 0 emails."""
        client, app = _make_recruiter_and_application(initial_status="applied")
        mail.outbox.clear()
        # Save via status endpoint with the SAME status should be rejected,
        # so instead we test a model-level save that does NOT change status.
        app.recruiter_notes = "Internal note updated"
        app.save(update_fields=["recruiter_notes", "updated_at"])
        status_emails = [
            e for e in mail.outbox if "status has been updated" in e.subject
        ]
        assert len(status_emails) == 0
        received_emails = [
            e for e in mail.outbox if "Application received" in e.subject
        ]
        assert len(received_emails) == 0

    def test_withdraw_fires_status_change_email(self):
        """Withdrawing an application fires a status-change email (applied → withdrawn)."""
        client, app = _make_candidate_client_and_application(initial_status="applied")
        mail.outbox.clear()
        resp = client.delete(f"/api/applications/{app.id}/")
        assert resp.status_code == status.HTTP_200_OK
        status_emails = [
            e for e in mail.outbox if "status has been updated" in e.subject
        ]
        assert len(status_emails) == 1

    def test_two_consecutive_transitions_fire_two_emails(self):
        """applied → reviewing → shortlisted produces 2 separate status-change emails."""
        client, app = _make_recruiter_and_application(initial_status="applied")
        mail.outbox.clear()
        client.patch(_status_url(app.id), {"status": "reviewing"}, format="json")
        client.patch(_status_url(app.id), {"status": "shortlisted"}, format="json")
        status_emails = [
            e for e in mail.outbox if "status has been updated" in e.subject
        ]
        assert len(status_emails) == 2

    def test_rejected_is_terminal_no_outgoing_edges(self):
        """Rejected status has no entries in VALID_TRANSITIONS."""
        assert "rejected" not in Application.VALID_TRANSITIONS

    def test_withdrawn_is_terminal_no_outgoing_edges(self):
        """Withdrawn status has no entries in VALID_TRANSITIONS."""
        assert "withdrawn" not in Application.VALID_TRANSITIONS
