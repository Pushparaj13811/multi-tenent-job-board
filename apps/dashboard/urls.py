from django.urls import path

from .views import CandidateDashboardView, RecruiterDashboardView

urlpatterns = [
    path("recruiter/", RecruiterDashboardView.as_view(), name="recruiter-dashboard"),
    path("candidate/", CandidateDashboardView.as_view(), name="candidate-dashboard"),
]
