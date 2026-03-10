from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job
from common.permissions import IsCandidate, IsRecruiter


class RecruiterDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsRecruiter]

    def get(self, request):
        company_ids = CompanyMember.objects.filter(
            user=request.user
        ).values_list("company_id", flat=True)

        jobs = Job.objects.filter(company_id__in=company_ids)

        jobs_by_status = {}
        for row in jobs.values("status").annotate(count=Count("id")):
            jobs_by_status[row["status"]] = row["count"]

        applications = Application.objects.filter(job__company_id__in=company_ids)

        apps_by_status = {}
        for row in applications.values("status").annotate(count=Count("id")):
            apps_by_status[row["status"]] = row["count"]

        recent = applications.select_related(
            "applicant", "job"
        ).order_by("-created_at")[:5]

        recent_data = [
            {
                "id": str(app.id),
                "applicant": {
                    "id": str(app.applicant.id),
                    "first_name": app.applicant.first_name,
                    "last_name": app.applicant.last_name,
                    "email": app.applicant.email,
                },
                "job": {
                    "id": str(app.job.id),
                    "title": app.job.title,
                },
                "status": app.status,
                "created_at": app.created_at.isoformat(),
            }
            for app in recent
        ]

        # Company verification statuses
        companies = Company.objects.filter(id__in=company_ids)
        companies_data = [
            {
                "id": str(c.id),
                "name": c.name,
                "slug": c.slug,
                "verification_status": c.verification_status,
                "is_verified": c.is_verified,
            }
            for c in companies
        ]

        # Top jobs by application count
        top_jobs = (
            jobs.filter(status="published")
            .annotate(application_count=Count("applications"))
            .order_by("-application_count")[:5]
        )
        top_jobs_data = [
            {
                "id": str(job.id),
                "title": job.title,
                "slug": job.slug,
                "application_count": job.application_count,
            }
            for job in top_jobs
        ]

        return Response({
            "total_jobs": jobs.count(),
            "jobs_by_status": jobs_by_status,
            "total_applications": applications.count(),
            "applications_by_status": apps_by_status,
            "recent_applications": recent_data,
            "companies": companies_data,
            "top_jobs": top_jobs_data,
        })


class CandidateDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsCandidate]

    def get(self, request):
        applications = Application.objects.filter(applicant=request.user)

        apps_by_status = {}
        for row in applications.values("status").annotate(count=Count("id")):
            apps_by_status[row["status"]] = row["count"]

        recent = applications.select_related(
            "job__company"
        ).order_by("-created_at")[:5]

        recent_data = [
            {
                "id": str(app.id),
                "job": {
                    "id": str(app.job.id),
                    "title": app.job.title,
                    "company": {
                        "name": app.job.company.name,
                        "slug": app.job.company.slug,
                    },
                },
                "status": app.status,
                "created_at": app.created_at.isoformat(),
                "updated_at": app.updated_at.isoformat(),
            }
            for app in recent
        ]

        return Response({
            "total_applications": applications.count(),
            "applications_by_status": apps_by_status,
            "recent_applications": recent_data,
        })
