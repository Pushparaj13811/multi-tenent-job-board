from rest_framework import serializers

from .models import Job


class JobListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "title", "slug", "company", "company_name", "location",
            "is_remote", "job_type", "experience_level", "salary_min",
            "salary_max", "currency", "status", "deadline", "created_at",
        ]
        read_only_fields = fields


class JobDetailSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "title", "slug", "company", "company_name", "posted_by",
            "description", "requirements", "responsibilities", "skills",
            "job_type", "experience_level", "location", "is_remote",
            "salary_min", "salary_max", "currency", "status", "deadline",
            "views_count", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "views_count", "created_at", "updated_at",
        ]


class JobCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id", "company", "title", "slug", "description", "requirements",
            "responsibilities", "skills", "job_type", "experience_level",
            "location", "is_remote", "salary_min", "salary_max", "currency",
            "status", "deadline", "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate(self, attrs):
        salary_min = attrs.get("salary_min")
        salary_max = attrs.get("salary_max")
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise serializers.ValidationError(
                {"salary_max": "salary_max must be greater than or equal to salary_min."}
            )
        return attrs

    def create(self, validated_data):
        validated_data["posted_by"] = self.context["request"].user
        return super().create(validated_data)
