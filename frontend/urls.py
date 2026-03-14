from django.urls import path

from . import views

app_name = "frontend"

urlpatterns = [
    # Public
    path("", views.landing_page, name="landing"),
    path("jobs/", views.job_board, name="job-board"),
    path("jobs/new/", views.post_job, name="post-job"),
    path("jobs/<slug:slug>/", views.job_detail, name="job-detail"),
    path("jobs/<slug:slug>/edit/", views.edit_job, name="edit-job"),
    path("companies/new/", views.create_company, name="create-company"),
    path("companies/<slug:slug>/", views.company_profile, name="company-profile"),
    # Auth
    path("login/", views.login_page, name="login"),
    path("register/", views.register_page, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("verify-email/", views.verify_email_page, name="verify-email"),
    # Dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
    # Applications
    path("applications/", views.my_applications, name="applications"),
    path("applications/<uuid:pk>/", views.application_detail, name="application-detail"),
    path("pipeline/", views.pipeline, name="pipeline"),
    # Notifications
    path("notifications/", views.notifications_page, name="notifications"),
    # Settings
    path("settings/", views.settings_page, name="settings"),
    # PWA
    path("offline/", views.offline_page, name="offline"),
]
