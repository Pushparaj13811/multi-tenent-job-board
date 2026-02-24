from django.utils import timezone
from rest_framework import serializers

from apps.jobs.models import Job
from common.validators import validate_resume

from .models import Application


class ApplicationCreateSerializer(serializers.ModelSerializer):
    resume = serializers.FileField(validators=[validate_resume])

    class Meta:
        model = Application
        fields = [
            "id", "job", "resume", "cover_letter",
            "expected_salary", "available_from", "status", "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate_job(self, job):
        if job.status != Job.Status.PUBLISHED:
            raise serializers.ValidationError("This job is not accepting applications.")
        if job.deadline and job.deadline < timezone.now().date():
            raise serializers.ValidationError(
                "The application deadline for this job has passed."
            )
        return job

    def validate(self, attrs):
        user = self.context["request"].user
        if Application.objects.filter(job=attrs["job"], applicant=user).exists():
            raise serializers.ValidationError(
                {"job": "You have already applied to this job."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["applicant"] = self.context["request"].user
        return super().create(validated_data)


class ApplicationListSerializer(serializers.ModelSerializer):
    """For candidates — excludes recruiter_notes."""

    class Meta:
        model = Application
        fields = [
            "id", "job", "status", "resume", "cover_letter",
            "expected_salary", "available_from", "created_at", "updated_at",
        ]
        read_only_fields = fields


class ApplicationRecruiterSerializer(serializers.ModelSerializer):
    """For recruiters — includes recruiter_notes."""

    class Meta:
        model = Application
        fields = [
            "id", "job", "applicant", "status", "resume", "cover_letter",
            "expected_salary", "available_from", "recruiter_notes",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class StatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Application.Status.choices)
    recruiter_notes = serializers.CharField(required=False, allow_blank=True)

    def validate_status(self, value):
        application = self.context["application"]
        valid = Application.VALID_TRANSITIONS.get(application.status, set())
        if value not in valid:
            raise serializers.ValidationError(
                f"Cannot transition from '{application.status}' to '{value}'."
            )
        return value
