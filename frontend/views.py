"""Frontend views — Django template-based pages that consume the DRF API."""

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User


def _login_and_bridge(request, user, next_url="/dashboard/"):
    """Log user in (session) and render a bridge page that stores JWT tokens."""
    login(request, user)
    refresh = RefreshToken.for_user(user)
    return render(request, "frontend/pages/auth/token_bridge.html", {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "next_url": next_url,
    })

# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------


def landing_page(request):
    if request.user.is_authenticated:
        return redirect("frontend:dashboard")

    stats = cache.get("landing_stats")
    if not stats:
        from apps.companies.models import Company
        from apps.jobs.models import Job

        stats = {
            "total_jobs": Job.objects.filter(status="published").count(),
            "total_companies": Company.objects.filter(
                domain_verified=True,
                verification_status=Company.VerificationStatus.VERIFIED,
            ).count(),
        }
        cache.set("landing_stats", stats, 300)  # 5 min cache

    ctx = {**stats, "current_year": timezone.now().year}
    return render(request, "frontend/pages/landing.html", ctx)


def job_board(request):
    return render(request, "frontend/pages/jobs/job_board.html")


def job_detail(request, slug):
    return render(request, "frontend/pages/jobs/job_detail.html", {"job_slug": slug})


def company_profile(request, slug):
    return render(request, "frontend/pages/companies/profile.html", {"company_slug": slug})


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------


def login_page(request):
    if request.user.is_authenticated:
        return redirect("frontend:dashboard")
    next_url = request.GET.get("next") or request.POST.get("next") or "/dashboard/"
    ctx = {"error": None, "next": next_url}
    if request.method == "POST":
        email = request.POST.get("email", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            return _login_and_bridge(request, user, next_url)
        ctx["error"] = "Invalid email or password."
        ctx["email"] = email
    return render(request, "frontend/pages/auth/login.html", ctx)


def register_page(request):
    if request.user.is_authenticated:
        return redirect("frontend:dashboard")
    ctx = {"errors": {}, "form_data": {}}
    if request.method == "POST":
        data = request.POST
        ctx["form_data"] = data
        errors = {}
        if not data.get("email"):
            errors["email"] = "Email is required."
        if not data.get("username"):
            errors["username"] = "Username is required."
        if not data.get("password"):
            errors["password"] = "Password is required."
        elif data.get("password") != data.get("password_confirm"):
            errors["password_confirm"] = "Passwords do not match."
        if User.objects.filter(email=data.get("email", "")).exists():
            errors["email"] = "An account with this email already exists."

        if not errors:
            role = data.get("role", "candidate")
            user = User(
                email=data["email"],
                username=data["username"],
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                role=role,
            )
            user.set_password(data["password"])
            user.save()
            return _login_and_bridge(request, user)
        ctx["errors"] = errors
    return render(request, "frontend/pages/auth/register.html", ctx)


def logout_view(request):
    logout(request)
    return render(request, "frontend/pages/auth/token_bridge.html", {
        "access_token": "",
        "refresh_token": "",
        "next_url": "/login/",
    })


def verify_email_page(request):
    return render(request, "frontend/pages/auth/verify_email.html")


# ---------------------------------------------------------------------------
# Dashboard (role-based redirect)
# ---------------------------------------------------------------------------


@login_required(login_url="/login/")
def dashboard(request):
    if request.user.role == "recruiter":
        return render(request, "frontend/pages/dashboard/recruiter.html")
    return render(request, "frontend/pages/dashboard/candidate.html")


# ---------------------------------------------------------------------------
# Candidate pages
# ---------------------------------------------------------------------------


@login_required(login_url="/login/")
def my_applications(request):
    return render(request, "frontend/pages/applications/list.html")


@login_required(login_url="/login/")
def application_detail(request, pk):
    return render(request, "frontend/pages/applications/detail.html", {"application_id": str(pk)})


# ---------------------------------------------------------------------------
# Recruiter pages
# ---------------------------------------------------------------------------


@login_required(login_url="/login/")
def pipeline(request):
    return render(request, "frontend/pages/applications/pipeline.html")


@login_required(login_url="/login/")
def post_job(request):
    return render(request, "frontend/pages/jobs/post_job.html")


@login_required(login_url="/login/")
def edit_job(request, slug):
    return render(request, "frontend/pages/jobs/edit_job.html", {"job_slug": slug})


@login_required(login_url="/login/")
def create_company(request):
    return render(request, "frontend/pages/companies/create.html")


# ---------------------------------------------------------------------------
# Shared authenticated pages
# ---------------------------------------------------------------------------


@login_required(login_url="/login/")
def notifications_page(request):
    return render(request, "frontend/pages/notifications/list.html")


@login_required(login_url="/login/")
def settings_page(request):
    return render(request, "frontend/pages/settings.html")


# ---------------------------------------------------------------------------
# PWA / Utility
# ---------------------------------------------------------------------------


def offline_page(request):
    return render(request, "frontend/pages/offline.html")
