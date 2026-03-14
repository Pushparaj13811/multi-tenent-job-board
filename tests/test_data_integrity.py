"""
Section 6 — Data Integrity & Edge Cases.

6.1  Resume upload validation (MIME, size limits)
6.2  Slug uniqueness (company, job)
6.3  Cascade deletes (User, Company, Job)
6.4  views_count atomicity (concurrent requests)
"""

import threading

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.applications.models import Application
from apps.jobs.models import Job
from apps.notifications.models import Notification
from common.validators import MAX_RESUME_SIZE_BYTES, validate_resume
from tests.factories import (
    ApplicationFactory,
    CompanyFactory,
    CompanyMemberFactory,
    JobFactory,
    NotificationFactory,
)

# ═══════════════════════════════════════════════════════════════════════════
# 6.1  Resume upload validation
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestResumeUploadValidation:
    """Validate resume MIME, extension, and size limits."""

    def test_correct_extension_wrong_mime_rejected(self):
        """A .pdf with image/png MIME type is rejected."""
        f = SimpleUploadedFile(
            "resume.pdf", b"%PNG fake image", content_type="image/png"
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_resume(f)
        assert "content type" in str(exc_info.value).lower() or "PDF" in str(exc_info.value)

    def test_file_exactly_at_size_limit_accepted(self):
        """A file exactly at 5MB passes validation."""
        content = b"x" * MAX_RESUME_SIZE_BYTES
        f = SimpleUploadedFile(
            "resume.pdf", content, content_type="application/pdf"
        )
        # Should not raise
        validate_resume(f)

    def test_file_one_byte_over_limit_rejected(self):
        """A file 1 byte over 5MB is rejected."""
        content = b"x" * (MAX_RESUME_SIZE_BYTES + 1)
        f = SimpleUploadedFile(
            "resume.pdf", content, content_type="application/pdf"
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_resume(f)
        assert "5MB" in str(exc_info.value) or "size" in str(exc_info.value).lower()

    def test_file_with_no_content_type_does_not_crash(self):
        """A file with no content_type attribute does not crash the validator.

        The validator skips MIME check when content_type is None.
        This documents that the file passes if extension and size are OK.
        """
        f = SimpleUploadedFile("resume.pdf", b"%PDF-1.4 content")
        f.content_type = None  # explicitly unset
        # Should not raise — extension and size are valid
        validate_resume(f)


# ═══════════════════════════════════════════════════════════════════════════
# 6.2  Slug uniqueness
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSlugUniqueness:
    """Company and job slug uniqueness constraints."""

    def test_duplicate_company_slug_returns_400(self):
        """Creating a second company with the same slug is rejected."""
        membership = CompanyMemberFactory(role="owner")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        # First company
        resp = client.post(
            "/api/companies/",
            {
                "name": "First Co",
                "slug": "unique-slug-test",
                "description": "test",
                "industry": "Tech",
                "location": "NYC",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        # Second company with same slug
        resp = client.post(
            "/api/companies/",
            {
                "name": "Second Co",
                "slug": "unique-slug-test",
                "description": "test",
                "industry": "Tech",
                "location": "NYC",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_job_slug_returns_400(self):
        """Creating a second job with the same slug is rejected (slug is globally unique)."""
        membership = CompanyMemberFactory(role="owner")
        client = APIClient()
        client.force_authenticate(user=membership.user)
        base_data = {
            "company": str(membership.company.id),
            "title": "Engineer",
            "description": "Build stuff",
            "requirements": "Python",
            "job_type": "full_time",
            "experience_level": "mid",
        }
        resp = client.post(
            "/api/jobs/",
            {**base_data, "slug": "unique-job-slug"},
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        resp = client.post(
            "/api/jobs/",
            {**base_data, "slug": "unique-job-slug", "title": "Engineer 2"},
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_job_slug_is_globally_unique(self):
        """Two different companies cannot have jobs with the same slug.

        The Job model has slug as unique (not scoped to company).
        This documents the actual behaviour: slug is globally unique.
        """
        company_a = CompanyFactory()
        company_b = CompanyFactory()
        JobFactory(company=company_a, slug="shared-slug")
        # Second job with same slug in different company should fail
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            JobFactory(company=company_b, slug="shared-slug")


# ═══════════════════════════════════════════════════════════════════════════
# 6.3  Cascade deletes
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCascadeDeletes:
    """Verify cascade and SET_NULL behaviour across related models."""

    def test_deleting_user_cascades_to_applications(self):
        """Deleting a User cascades to their Applications."""
        app = ApplicationFactory()
        app_id = app.id
        user = app.applicant
        user.delete()
        assert not Application.objects.filter(id=app_id).exists()

    def test_deleting_user_cascades_to_notifications(self):
        """Deleting a User cascades to their Notifications."""
        notif = NotificationFactory()
        notif_id = notif.id
        user = notif.user
        user.delete()
        assert not Notification.objects.filter(id=notif_id).exists()

    def test_deleting_user_sets_null_on_job_posted_by(self):
        """Deleting a User sets posted_by=NULL on their Jobs (SET_NULL)."""
        job = JobFactory()
        user = job.posted_by
        user.delete()
        job.refresh_from_db()
        assert job.posted_by is None

    def test_deleting_company_cascades_to_jobs(self):
        """Deleting a Company cascades to all its Jobs."""
        job = JobFactory()
        job_id = job.id
        company = job.company
        company.delete()
        assert not Job.objects.filter(id=job_id).exists()

    def test_deleting_company_cascades_to_applications_via_jobs(self):
        """Deleting a Company cascades through Jobs to Applications."""
        app = ApplicationFactory()
        app_id = app.id
        company = app.job.company
        company.delete()
        assert not Application.objects.filter(id=app_id).exists()

    def test_deleting_job_cascades_to_applications(self):
        """Deleting a Job cascades to its Applications."""
        app = ApplicationFactory()
        app_id = app.id
        job = app.job
        job.delete()
        assert not Application.objects.filter(id=app_id).exists()

    def test_orphaned_notifications_after_job_cascade(self):
        """Notifications referencing deleted applications are allowed to remain.

        Notifications store application_id in metadata (JSONField), not a FK.
        After cascading delete, the Notification still exists but references
        a non-existent application. This documents the accepted behaviour.
        """
        app = ApplicationFactory()
        notif = NotificationFactory(
            user=app.applicant,
            metadata={"application_id": str(app.id)},
        )
        notif_id = notif.id
        app.job.delete()
        # Notification survives because it links to user, not application
        assert Notification.objects.filter(id=notif_id).exists()


# ═══════════════════════════════════════════════════════════════════════════
# 6.4  views_count atomicity
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestResumeExtensionValidation:
    """Additional resume extension tests: .exe rejected, .doc/.docx accepted."""

    def test_exe_extension_rejected(self):
        """A .exe file is rejected regardless of content type."""
        f = SimpleUploadedFile(
            "malware.exe", b"MZ fake", content_type="application/x-msdownload"
        )
        with pytest.raises(ValidationError):
            validate_resume(f)

    def test_doc_extension_accepted(self):
        """A .doc file with correct MIME type passes validation."""
        f = SimpleUploadedFile(
            "resume.doc", b"fake doc content", content_type="application/msword"
        )
        validate_resume(f)

    def test_docx_extension_accepted(self):
        """A .docx file with correct MIME type passes validation."""
        f = SimpleUploadedFile(
            "resume.docx",
            b"fake docx content",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        validate_resume(f)

    def test_txt_extension_rejected(self):
        """A .txt file is rejected."""
        f = SimpleUploadedFile(
            "notes.txt", b"plain text", content_type="text/plain"
        )
        with pytest.raises(ValidationError):
            validate_resume(f)


@pytest.mark.django_db
class TestUniqueConstraints:
    """DB-level unique constraints for CompanyMember and Application."""

    def test_company_member_unique_together(self):
        """Same user + company pair cannot exist twice in CompanyMember."""
        from django.db import IntegrityError

        from apps.companies.models import CompanyMember

        membership = CompanyMemberFactory(role="owner")
        with pytest.raises(IntegrityError):
            CompanyMember.objects.create(
                user=membership.user,
                company=membership.company,
                role="recruiter",
            )

    def test_application_unique_together(self):
        """Same job + applicant pair cannot exist twice in Application."""
        from django.db import IntegrityError

        app = ApplicationFactory()
        with pytest.raises(IntegrityError):
            Application.objects.create(
                job=app.job,
                applicant=app.applicant,
                resume="resumes/dupe.pdf",
            )


@pytest.mark.django_db(transaction=True)
class TestViewsCountAtomicity:
    """Concurrent GET requests must each increment views_count via F() expression."""

    def test_concurrent_views_increment_correctly(self):
        """10 concurrent GET requests result in views_count == 10."""
        job = JobFactory(status="published", views_count=0)
        url = f"/api/jobs/{job.slug}/"

        errors = []

        def fetch():
            try:
                c = APIClient()
                resp = c.get(url)
                if resp.status_code != 200:
                    errors.append(f"Got {resp.status_code}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=fetch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent requests: {errors}"
        job.refresh_from_db()
        assert job.views_count == 10, (
            f"Expected views_count=10 but got {job.views_count}. "
            f"F() expression may not be working correctly."
        )
