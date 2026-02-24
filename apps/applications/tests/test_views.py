"""Tests for Application API endpoints."""

import datetime

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from tests.factories import (
    ApplicationFactory,
    CompanyMemberFactory,
    JobFactory,
    UserFactory,
)


def _applications_url():
    return "/api/applications/"


def _status_url(app_id):
    return f"/api/applications/{app_id}/status/"


def _withdraw_url(app_id):
    return f"/api/applications/{app_id}/"


def _make_resume():
    return SimpleUploadedFile(
        "resume.pdf",
        b"%PDF-1.4 fake content",
        content_type="application/pdf",
    )


@pytest.fixture
def published_job(db):
    """A published job with a company and owner recruiter."""
    membership = CompanyMemberFactory(role="owner")
    job = JobFactory(
        status="published",
        company=membership.company,
        posted_by=membership.user,
    )
    return job, membership


@pytest.mark.django_db
class TestCreateApplication:
    def test_candidate_can_apply(self, published_job):
        job, _ = published_job
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        data = {"job": str(job.id), "resume": _make_resume()}
        response = client.post(_applications_url(), data, format="multipart")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == "applied"

    def test_signal_fires_email_on_create(self, published_job):
        job, _ = published_job
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        mail.outbox.clear()
        data = {"job": str(job.id), "resume": _make_resume()}
        client.post(_applications_url(), data, format="multipart")
        assert len(mail.outbox) == 1
        assert "Application received" in mail.outbox[0].subject

    def test_unauthenticated_gets_401(self, api_client, published_job):
        job, _ = published_job
        data = {"job": str(job.id), "resume": _make_resume()}
        response = api_client.post(_applications_url(), data, format="multipart")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_recruiter_cannot_apply(self, published_job):
        job, membership = published_job
        client = APIClient()
        client.force_authenticate(user=membership.user)
        data = {"job": str(job.id), "resume": _make_resume()}
        response = client.post(_applications_url(), data, format="multipart")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_application_rejected(self, published_job):
        """Unit test: sequential duplicate POST returns 400.

        Layered coverage: tests/test_state_machine.py::TestApplicationBoundaryConditions
        has a boundary-audit version that pre-creates via factory. Both must coexist:
        this tests the HTTP flow, the other tests the constraint in isolation.
        """
        job, _ = published_job
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        data = {"job": str(job.id), "resume": _make_resume()}
        client.post(_applications_url(), data, format="multipart")
        data2 = {"job": str(job.id), "resume": _make_resume()}
        response = client.post(_applications_url(), data2, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_apply_to_draft_job(self):
        job = JobFactory(status="draft")
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        data = {"job": str(job.id), "resume": _make_resume()}
        response = client.post(_applications_url(), data, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_apply_to_expired_job(self):
        yesterday = timezone.now().date() - datetime.timedelta(days=1)
        job = JobFactory(status="published", deadline=yesterday)
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        data = {"job": str(job.id), "resume": _make_resume()}
        response = client.post(_applications_url(), data, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_resume_rejected(self):
        job = JobFactory(status="published")
        candidate = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=candidate)
        bad_file = SimpleUploadedFile(
            "virus.exe", b"MZ fake exe", content_type="application/x-msdownload"
        )
        data = {"job": str(job.id), "resume": bad_file}
        response = client.post(_applications_url(), data, format="multipart")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUpdateApplicationStatus:
    def test_valid_transition(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        app = ApplicationFactory(job=job)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.patch(
            _status_url(app.id), {"status": "reviewing"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == "reviewing"

    def test_invalid_transition_returns_400(self):
        """Unit test: single invalid transition (applied→offered) returns 400.

        Layered coverage: tests/test_state_machine.py::TestInvalidTransitions
        is a comprehensive parametrized matrix covering all 34 invalid pairs.
        This spot-checks one case as a unit-level regression guard.
        """
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        app = ApplicationFactory(job=job)
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.patch(
            _status_url(app.id), {"status": "offered"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_member_denied(self):
        app = ApplicationFactory()
        outsider = UserFactory(role="recruiter")
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.patch(
            _status_url(app.id), {"status": "reviewing"}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_candidate_cannot_update_status(self):
        app = ApplicationFactory()
        client = APIClient()
        client.force_authenticate(user=app.applicant)
        response = client.patch(
            _status_url(app.id), {"status": "reviewing"}, format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_status_change_triggers_email(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        app = ApplicationFactory(job=job)
        mail.outbox.clear()
        client = APIClient()
        client.force_authenticate(user=membership.user)
        client.patch(_status_url(app.id), {"status": "reviewing"}, format="json")
        status_emails = [e for e in mail.outbox if "status has been updated" in e.subject]
        assert len(status_emails) == 1


@pytest.mark.django_db
class TestListApplications:
    def test_candidate_sees_own(self):
        candidate = UserFactory(role="candidate")
        ApplicationFactory(applicant=candidate)
        ApplicationFactory()  # other user's application
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_applications_url())
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_recruiter_sees_company_applications(self):
        membership = CompanyMemberFactory(role="owner")
        job = JobFactory(status="published", company=membership.company)
        ApplicationFactory(job=job)
        ApplicationFactory()  # different company's application
        client = APIClient()
        client.force_authenticate(user=membership.user)
        response = client.get(_applications_url())
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_recruiter_notes_hidden_from_candidate(self):
        candidate = UserFactory(role="candidate")
        ApplicationFactory(applicant=candidate, recruiter_notes="Internal note")
        client = APIClient()
        client.force_authenticate(user=candidate)
        response = client.get(_applications_url())
        assert response.status_code == status.HTTP_200_OK
        result = response.data["results"][0]
        assert "recruiter_notes" not in result


@pytest.mark.django_db
class TestWithdrawApplication:
    def test_can_withdraw_applied(self):
        app = ApplicationFactory(status="applied")
        client = APIClient()
        client.force_authenticate(user=app.applicant)
        response = client.delete(_withdraw_url(app.id))
        assert response.status_code == status.HTTP_200_OK
        app.refresh_from_db()
        assert app.status == "withdrawn"

    def test_cannot_withdraw_rejected(self):
        app = ApplicationFactory(status="rejected")
        client = APIClient()
        client.force_authenticate(user=app.applicant)
        response = client.delete(_withdraw_url(app.id))
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_owner_denied(self):
        app = ApplicationFactory(status="applied")
        other = UserFactory(role="candidate")
        client = APIClient()
        client.force_authenticate(user=other)
        response = client.delete(_withdraw_url(app.id))
        # Returns 404 (not 403) — queryset scoped to own apps prevents IDOR
        assert response.status_code == status.HTTP_404_NOT_FOUND
