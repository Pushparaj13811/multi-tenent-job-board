from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Company, CompanyMember
from .tokens import generate_domain_verification_token
from .validators import extract_email_domain


class CompanyListSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    verification_badge = serializers.CharField(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "description", "website", "logo",
            "size", "industry", "location", "is_verified",
            "verification_badge", "created_at",
        ]
        read_only_fields = fields


class CompanyDetailSerializer(serializers.ModelSerializer):
    is_verified = serializers.BooleanField(read_only=True)
    verification_badge = serializers.CharField(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "description", "website", "logo",
            "size", "industry", "location", "domain", "domain_verified",
            "verification_status", "is_verified", "verification_badge",
            "created_at",
        ]
        read_only_fields = [
            "id", "domain", "domain_verified", "verification_status",
            "is_verified", "verification_badge", "created_at",
        ]


class CompanyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "description", "website", "logo",
            "size", "industry", "location", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        domain = extract_email_domain(user.email)
        token = generate_domain_verification_token()
        with transaction.atomic():
            company = Company.objects.create(
                **validated_data,
                domain=domain,
                domain_verification_token=token,
                domain_verification_token_generated_at=timezone.now(),
            )
            CompanyMember.objects.create(user=user, company=company, role="owner")
        return company


class InviteMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        from apps.accounts.models import User

        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("No recruiter found with this email.") from None
        if user.role != "recruiter":
            raise serializers.ValidationError("Only recruiters can be invited.")
        self._invited_user = user
        return value

    def validate(self, attrs):
        company = self.context["company"]
        if CompanyMember.objects.filter(user=self._invited_user, company=company).exists():
            raise serializers.ValidationError({"email": "User is already a member."})
        return attrs

    def create(self, validated_data):
        company = self.context["company"]
        member = CompanyMember.objects.create(
            user=self._invited_user, company=company, role="recruiter"
        )
        return member

    def to_representation(self, instance):
        return {
            "email": instance.user.email,
            "role": instance.role,
            "company": str(instance.company),
        }
