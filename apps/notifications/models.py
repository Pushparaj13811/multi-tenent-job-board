from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Notification(TimeStampedModel):
    """In-app notification for a user."""

    class Type(models.TextChoices):
        APPLICATION_RECEIVED = "application_received", "Application Received"
        STATUS_CHANGED = "status_changed", "Status Changed"
        JOB_EXPIRING = "job_expiring", "Job Expiring"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=50, choices=Type.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user"], name="idx_notif_user"),
            models.Index(fields=["-created_at"], name="idx_notif_created"),
        ]

    def __str__(self):
        return f"{self.type}: {self.title}"
