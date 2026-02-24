from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.companies.models import CompanyMember
from common.permissions import IsCandidate

from .models import Application
from .serializers import (
    ApplicationCreateSerializer,
    ApplicationListSerializer,
    ApplicationRecruiterSerializer,
    StatusUpdateSerializer,
)


class ApplicationViewSet(viewsets.ModelViewSet):
    """CRUD for applications."""

    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if user.role == "candidate":
            return Application.objects.filter(applicant=user).order_by("-created_at")
        if user.role == "recruiter":
            company_ids = CompanyMember.objects.filter(
                user=user
            ).values_list("company_id", flat=True)
            return Application.objects.filter(
                job__company_id__in=company_ids
            ).order_by("-created_at")
        return Application.objects.none()

    def get_serializer_class(self):
        if self.action == "create":
            return ApplicationCreateSerializer
        if self.request.user.role == "recruiter":
            return ApplicationRecruiterSerializer
        return ApplicationListSerializer

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), IsCandidate()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        """Withdraw an application (sets status to withdrawn)."""
        application = self.get_object()
        if application.applicant != request.user:
            return Response(
                {
                    "error": "Only the applicant can withdraw.",
                    "code": "permission_denied",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        if application.status not in Application.WITHDRAWABLE_STATUSES:
            return Response(
                {
                    "error": "Cannot withdraw from this status.",
                    "code": "invalid_status_transition",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        application.status = Application.Status.WITHDRAWN
        application.save(update_fields=["status", "updated_at"])
        return Response({"id": str(application.id), "status": "withdrawn"})


class ApplicationStatusUpdateView(generics.GenericAPIView):
    """PATCH /api/applications/{id}/status/ — recruiter updates application status."""

    serializer_class = StatusUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_application(self, user):
        """Return the application only if the user is a member of its company."""
        company_ids = CompanyMember.objects.filter(
            user=user
        ).values_list("company_id", flat=True)
        return Application.objects.select_related("job__company").get(
            pk=self.kwargs["pk"],
            job__company_id__in=company_ids,
        )

    def patch(self, request, *args, **kwargs):
        try:
            application = self.get_application(request.user)
        except Application.DoesNotExist:
            return Response(
                {"error": "Application not found.", "code": "not_found", "details": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(
            data=request.data, context={"application": application}
        )
        serializer.is_valid(raise_exception=True)

        application.status = serializer.validated_data["status"]
        if "recruiter_notes" in serializer.validated_data:
            application.recruiter_notes = serializer.validated_data["recruiter_notes"]
        application.save(update_fields=["status", "recruiter_notes", "updated_at"])

        return Response({
            "id": str(application.id),
            "status": application.status,
            "recruiter_notes": application.recruiter_notes,
            "updated_at": application.updated_at,
        })
