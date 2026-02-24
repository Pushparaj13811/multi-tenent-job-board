"""Tests for the Application model."""

import pytest
from django.db import IntegrityError

from apps.applications.models import Application
from tests.factories import ApplicationFactory, JobFactory, UserFactory


@pytest.mark.django_db
class TestApplicationModel:
    def test_create_application(self):
        app = ApplicationFactory()
        assert Application.objects.filter(pk=app.pk).exists()

    def test_unique_together_job_applicant(self):
        job = JobFactory(status="published")
        user = UserFactory(role="candidate")
        ApplicationFactory(job=job, applicant=user)
        with pytest.raises(IntegrityError):
            ApplicationFactory(job=job, applicant=user)

    def test_default_status_is_applied(self):
        app = ApplicationFactory()
        assert app.status == "applied"

    def test_cascade_on_job_delete(self):
        app = ApplicationFactory()
        app_pk = app.pk
        app.job.delete()
        assert not Application.objects.filter(pk=app_pk).exists()

    def test_cascade_on_user_delete(self):
        app = ApplicationFactory()
        app_pk = app.pk
        app.applicant.delete()
        assert not Application.objects.filter(pk=app_pk).exists()

    def test_str_representation(self):
        app = ApplicationFactory()
        result = str(app)
        assert "→" in result

    def test_status_choices(self):
        choices = {c[0] for c in Application.Status.choices}
        assert choices == {
            "applied", "reviewing", "shortlisted", "interview",
            "offered", "rejected", "withdrawn",
        }
