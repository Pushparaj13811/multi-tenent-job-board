from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.companies.models import CompanyMember
from common.permissions import IsRecruiter

from .filters import JobFilter
from .models import Job
from .serializers import JobCreateSerializer, JobDetailSerializer, JobListSerializer


class JobViewSet(viewsets.ModelViewSet):
    """CRUD for jobs. Lookup by slug. Includes publish, close, and search actions."""

    lookup_field = "slug"
    filterset_class = JobFilter

    def get_queryset(self):
        if self.action == "list":
            if self.request.query_params.get("mine") == "true" and self.request.user.is_authenticated:
                company_ids = CompanyMember.objects.filter(
                    user=self.request.user,
                ).values_list("company_id", flat=True)
                return Job.objects.filter(company_id__in=company_ids).order_by("-created_at")
            return Job.objects.published().order_by("-created_at")
        if self.action == "search":
            return Job.objects.none()
        return Job.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return JobCreateSerializer
        if self.action == "list":
            return JobListSerializer
        return JobDetailSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve", "search"):
            return [AllowAny()]
        if self.action == "create":
            return [IsAuthenticated(), IsRecruiter()]
        return [IsAuthenticated()]

    def _check_company_member(self, request, job):
        """Check if user is a member of the job's company."""
        if not CompanyMember.objects.filter(
            user=request.user, company=job.company
        ).exists():
            return Response(
                {
                    "error": "Only company members can perform this action.",
                    "code": "permission_denied",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = serializer.validated_data.get("company")
        if not CompanyMember.objects.filter(
            user=request.user, company=company
        ).exists():
            return Response(
                {
                    "error": "You must be a member of this company.",
                    "code": "permission_denied",
                    "details": {},
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        Job.objects.filter(pk=instance.pk).update(views_count=F("views_count") + 1)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def update(self, request, *args, **kwargs):
        job = self.get_object()
        denied = self._check_company_member(request, job)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        job = self.get_object()
        denied = self._check_company_member(request, job)
        if denied:
            return denied
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        denied = self._check_company_member(request, job)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, slug=None):
        job = self.get_object()
        denied = self._check_company_member(request, job)
        if denied:
            return denied
        if job.status != Job.Status.DRAFT:
            return Response(
                {
                    "error": "Only draft jobs can be published.",
                    "code": "invalid_status_transition",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.status = Job.Status.PUBLISHED
        job.save(update_fields=["status", "updated_at"])
        return Response(
            {"id": str(job.id), "status": job.status, "message": "Job published successfully."}
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, slug=None):
        job = self.get_object()
        denied = self._check_company_member(request, job)
        if denied:
            return denied
        if job.status != Job.Status.PUBLISHED:
            return Response(
                {
                    "error": "Only published jobs can be closed.",
                    "code": "invalid_status_transition",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        job.status = Job.Status.CLOSED
        job.save(update_fields=["status", "updated_at"])
        return Response(
            {"id": str(job.id), "status": job.status, "message": "Job closed successfully."}
        )

    @action(detail=False, methods=["get"], url_path="search", pagination_class=None)
    def search(self, request):
        q = request.query_params.get("q")
        if not q:
            return Response(
                {
                    "error": "Missing 'q' query parameter.",
                    "code": "missing_query",
                    "details": {},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = Job.objects.search(q)
        serializer = JobListSerializer(queryset, many=True)
        return Response({"results": serializer.data})
