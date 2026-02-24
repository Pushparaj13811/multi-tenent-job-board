from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Application(TimeStampedModel):
    """A candidate's application to a job listing."""

    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        REVIEWING = "reviewing", "Reviewing"
        SHORTLISTED = "shortlisted", "Shortlisted"
        INTERVIEW = "interview", "Interview"
        OFFERED = "offered", "Offered"
        REJECTED = "rejected", "Rejected"
        WITHDRAWN = "withdrawn", "Withdrawn"

    VALID_TRANSITIONS = {
        "applied": {"reviewing", "rejected"},
        "reviewing": {"shortlisted", "rejected"},
        "shortlisted": {"interview", "rejected"},
        "interview": {"offered", "rejected"},
        "offered": {"rejected"},
    }

    WITHDRAWABLE_STATUSES = {"applied", "reviewing", "shortlisted", "interview"}

    job = models.ForeignKey(
        "jobs.Job", on_delete=models.CASCADE, related_name="applications"
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications"
    )
    resume = models.FileField(upload_to="resumes/%Y/%m/")
    cover_letter = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.APPLIED
    )
    recruiter_notes = models.TextField(blank=True)
    expected_salary = models.PositiveIntegerField(null=True, blank=True)
    available_from = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("job", "applicant")
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_app_status_created"),
            models.Index(fields=["job", "status"], name="idx_app_job_status"),
        ]

    def __str__(self):
        return f"{self.applicant} → {self.job}"
