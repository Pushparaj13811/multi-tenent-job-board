from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsRecruiter

from .models import Company, CompanyMember
from .serializers import (
    CompanyCreateSerializer,
    CompanyDetailSerializer,
    CompanyListSerializer,
    InviteMemberSerializer,
)
from .tokens import (
    generate_domain_verification_token,
    is_domain_token_expired,
    is_resend_on_cooldown,
)


class CompanyViewSet(viewsets.ModelViewSet):
    """CRUD for companies. Lookup by slug."""

    lookup_field = "slug"

    def get_queryset(self):
        if self.action == "list":
            return Company.objects.filter(
                domain_verified=True,
                verification_status="verified",
            ).order_by("-created_at")
        return Company.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return CompanyCreateSerializer
        if self.action == "list":
            return CompanyListSerializer
        return CompanyDetailSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        if self.action == "create":
            return [IsAuthenticated(), IsRecruiter()]
        # update/partial_update — must be company owner
        return [IsAuthenticated()]

    def update(self, request, *args, **kwargs):
        company = self.get_object()
        if not CompanyMember.objects.filter(
            user=request.user, company=company, role="owner"
        ).exists():
            return Response(
                {"error": "Only the company owner can update.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        company = self.get_object()
        if not CompanyMember.objects.filter(
            user=request.user, company=company, role="owner"
        ).exists():
            return Response(
                {"error": "Only the company owner can update.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        company = self.get_object()
        if not CompanyMember.objects.filter(
            user=request.user, company=company, role="owner"
        ).exists():
            return Response(
                {"error": "Only the company owner can delete.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    # ── Verification Actions ──

    @action(detail=True, methods=["post"], url_path="verify-domain")
    def verify_domain(self, request, slug=None):
        """POST /api/companies/{slug}/verify-domain/ — Verify domain ownership."""
        company = self.get_object()
        if not CompanyMember.objects.filter(
            user=request.user, company=company,
        ).exists():
            return Response(
                {"error": "Only company members can verify domain.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )

        token = request.data.get("token", "")
        if not token or token != company.domain_verification_token:
            return Response(
                {"error": "Invalid verification token.", "code": "invalid_token", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if is_domain_token_expired(company.domain_verification_token_generated_at):
            return Response(
                {"error": "Verification token has expired.", "code": "token_expired", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company.domain_verified = True
        company.save(update_fields=["domain_verified", "updated_at"])
        return Response({"detail": "Domain verified successfully."})

    @action(detail=True, methods=["post"], url_path="resend-domain-verification")
    def resend_domain_verification(self, request, slug=None):
        """POST /api/companies/{slug}/resend-domain-verification/ — Resend token."""
        company = self.get_object()
        if not CompanyMember.objects.filter(
            user=request.user, company=company,
        ).exists():
            return Response(
                {"error": "Only company members can resend.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )

        if company.domain_verified:
            return Response(
                {"error": "Domain is already verified.", "code": "already_verified", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if is_resend_on_cooldown(company.domain_verification_token_generated_at):
            return Response(
                {"error": "Please wait before requesting a new token.", "code": "cooldown", "details": {}},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        company.domain_verification_token = generate_domain_verification_token()
        company.domain_verification_token_generated_at = timezone.now()
        company.save(update_fields=[
            "domain_verification_token",
            "domain_verification_token_generated_at",
            "updated_at",
        ])
        return Response({"detail": "New verification token sent."})

    @action(detail=True, methods=["post"], url_path="submit-verification")
    def submit_verification(self, request, slug=None):
        """POST /api/companies/{slug}/submit-verification/ — Submit for admin review."""
        company = self.get_object()
        if not CompanyMember.objects.filter(
            user=request.user, company=company, role="owner",
        ).exists():
            return Response(
                {"error": "Only company owners can submit verification.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not company.domain_verified:
            return Response(
                {"error": "Domain must be verified first.", "code": "domain_not_verified", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if company.verification_status in ("verified", "pending"):
            return Response(
                {"error": "Company is already verified or pending review.", "code": "invalid_status", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        registration_number = request.data.get("registration_number", "")
        company.registration_number = registration_number
        company.verification_status = "pending"
        company.save(update_fields=["registration_number", "verification_status", "updated_at"])
        return Response({"detail": "Verification submitted for review."})


class MemberView(APIView):
    """
    GET  /api/companies/{slug}/members/           — List members
    POST /api/companies/{slug}/members/           — Invite a recruiter
    DELETE /api/companies/{slug}/members/{id}/     — Remove a member
    """

    permission_classes = [IsAuthenticated]

    def _get_company(self):
        return Company.objects.get(slug=self.kwargs["slug"])

    def _check_membership(self, request, company):
        return CompanyMember.objects.filter(user=request.user, company=company).exists()

    def _check_owner(self, request, company):
        return CompanyMember.objects.filter(user=request.user, company=company, role="owner").exists()

    def get(self, request, slug, pk=None):
        """List all members of the company."""
        company = self._get_company()
        if not self._check_membership(request, company):
            return Response(
                {"error": "Only company members can view members.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        members = CompanyMember.objects.filter(company=company).select_related("user")
        data = [
            {
                "id": str(m.id),
                "email": m.user.email,
                "first_name": m.user.first_name,
                "last_name": m.user.last_name,
                "role": m.role,
                "created_at": m.created_at.isoformat(),
            }
            for m in members
        ]
        return Response(data)

    def post(self, request, slug, pk=None):
        """Invite a recruiter to the company."""
        company = self._get_company()
        if not self._check_owner(request, company):
            return Response(
                {"error": "Only the company owner can invite.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = InviteMemberSerializer(data=request.data)
        serializer.context["company"] = company
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, slug, pk=None):
        """Remove a member from the company."""
        company = self._get_company()
        if not self._check_owner(request, company):
            return Response(
                {"error": "Only the company owner can remove members.", "code": "permission_denied", "details": {}},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            membership = CompanyMember.objects.get(id=pk, company=company)
        except CompanyMember.DoesNotExist:
            return Response(
                {"error": "Member not found.", "code": "not_found", "details": {}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if membership.role == "owner":
            return Response(
                {"error": "Cannot remove the company owner.", "code": "invalid_operation", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
