from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models

from common.models import TimeStampedModel

from .managers import JobManager


class Job(TimeStampedModel):
    """A job listing posted by a company recruiter."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CLOSED = "closed", "Closed"

    class JobType(models.TextChoices):
        FULL_TIME = "full_time", "Full Time"
        PART_TIME = "part_time", "Part Time"
        CONTRACT = "contract", "Contract"
        INTERNSHIP = "internship", "Internship"
        REMOTE = "remote", "Remote"

    class ExperienceLevel(models.TextChoices):
        JUNIOR = "junior", "Junior"
        MID = "mid", "Mid"
        SENIOR = "senior", "Senior"
        LEAD = "lead", "Lead"

    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, related_name="jobs"
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="posted_jobs"
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField()
    requirements = models.TextField()
    responsibilities = models.TextField(blank=True)
    skills = models.JSONField(default=list)
    job_type = models.CharField(max_length=20, choices=JobType.choices)
    experience_level = models.CharField(max_length=20, choices=ExperienceLevel.choices)
    location = models.CharField(max_length=255, blank=True)
    is_remote = models.BooleanField(default=False)
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=10, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    deadline = models.DateField(null=True, blank=True)
    views_count = models.PositiveIntegerField(default=0)
    search_vector = SearchVectorField(null=True)

    objects = JobManager()

    class Meta:
        indexes = [
            GinIndex(fields=["search_vector"], name="idx_job_search_vector"),
            models.Index(fields=["status", "created_at"], name="idx_job_status_created"),
            models.Index(fields=["company", "status"], name="idx_job_company_status"),
        ]

    def __str__(self):
        return self.title
