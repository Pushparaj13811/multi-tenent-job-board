from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Company(TimeStampedModel):
    """A company that posts jobs. Two-tier verification: domain + document."""

    class Size(models.TextChoices):
        TINY = "1-10", "1-10"
        SMALL = "11-50", "11-50"
        MEDIUM = "51-200", "51-200"
        LARGE = "201-500", "201-500"
        LARGE_PLUS = "501-1000", "501-1000"
        ENTERPRISE = "1000+", "1000+"

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        PENDING = "pending", "Pending Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    # ── Basic Info ──
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="logos/", null=True, blank=True)
    size = models.CharField(max_length=20, choices=Size.choices, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True)

    # ── Domain Verification (Tier 1) ──
    domain = models.CharField(max_length=255, blank=True, default="")
    domain_verified = models.BooleanField(default=False)
    domain_verification_token = models.CharField(max_length=255, blank=True, default="")
    domain_verification_token_generated_at = models.DateTimeField(null=True, blank=True)

    # ── Document Verification (Tier 2) ──
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    registration_number = models.CharField(max_length=100, blank=True, default="")
    registration_document = models.FileField(
        upload_to="verification_docs/", null=True, blank=True,
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_companies",
    )
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name

    @property
    def is_verified(self):
        """Company is verified only when both domain AND document verification pass."""
        return self.domain_verified and self.verification_status == self.VerificationStatus.VERIFIED

    @property
    def verification_badge(self):
        """Return the current verification badge level."""
        if self.is_verified:
            return "verified"
        if self.domain_verified:
            return "domain_verified"
        return "unverified"


class CompanyMember(TimeStampedModel):
    """Through model linking users to companies with a role."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        RECRUITER = "recruiter", "Recruiter"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_memberships"
    )
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RECRUITER)

    class Meta:
        unique_together = ("user", "company")
        indexes = [
            models.Index(fields=["company"], name="idx_member_company"),
            models.Index(fields=["user"], name="idx_member_user"),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.company.name} ({self.role})"
