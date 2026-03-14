"""
Tests for Part B — Missing CRUD endpoints:
- B2: Member list/remove
- B3: ?mine=true job filter
- B4: GET/PATCH /api/auth/me/
- B5: POST /api/auth/change-password/
- B6: POST /api/auth/avatar/
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job
from tests.factories import UserFactory

COMPANIES_URL = "/api/companies/"
JOBS_URL = "/api/jobs/"
ME_URL = "/api/auth/me/"
CHANGE_PASSWORD_URL = "/api/auth/change-password/"
AVATAR_URL = "/api/auth/avatar/"


def _make_image():
    """Create a minimal valid PNG image."""
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile("avatar.png", buf.read(), content_type="image/png")


# ──────────────────────────────────────────────────────────────
# B2 — Member List & Remove
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMemberList:
    def _setup(self):
        owner = User.objects.create_user(
            email="owner@acme.com", username="owner", password="pass123!", role="recruiter",
        )
        company = Company.objects.create(
            name="Acme", slug="acme",
            domain_verified=True, verification_status="verified",
        )
        CompanyMember.objects.create(user=owner, company=company, role="owner")
        member = User.objects.create_user(
            email="member@acme.com", username="member", password="pass123!", role="recruiter",
        )
        CompanyMember.objects.create(user=member, company=company, role="recruiter")
        client = APIClient()
        client.force_authenticate(user=owner)
        return client, owner, company, member

    def test_list_members_returns_200(self):
        client, owner, company, member = self._setup()
        response = client.get(f"{COMPANIES_URL}{company.slug}/members/")
        assert response.status_code == 200

    def test_list_members_returns_all_members(self):
        client, owner, company, member = self._setup()
        response = client.get(f"{COMPANIES_URL}{company.slug}/members/")
        emails = [m["email"] for m in response.json()]
        assert owner.email in emails
        assert member.email in emails

    def test_non_member_cannot_list(self):
        _, _, company, _ = self._setup()
        outsider = User.objects.create_user(
            email="outsider@test.com", username="outsider", password="pass123!", role="recruiter",
        )
        client = APIClient()
        client.force_authenticate(user=outsider)
        response = client.get(f"{COMPANIES_URL}{company.slug}/members/")
        assert response.status_code == 403


@pytest.mark.django_db
class TestMemberRemove:
    def _setup(self):
        owner = User.objects.create_user(
            email="owner@acme.com", username="owner", password="pass123!", role="recruiter",
        )
        company = Company.objects.create(
            name="Acme", slug="acme",
            domain_verified=True, verification_status="verified",
        )
        CompanyMember.objects.create(user=owner, company=company, role="owner")
        member = User.objects.create_user(
            email="member@acme.com", username="member", password="pass123!", role="recruiter",
        )
        membership = CompanyMember.objects.create(user=member, company=company, role="recruiter")
        client = APIClient()
        client.force_authenticate(user=owner)
        return client, owner, company, member, membership

    def test_owner_can_remove_member(self):
        client, owner, company, member, membership = self._setup()
        response = client.delete(
            f"{COMPANIES_URL}{company.slug}/members/{membership.id}/"
        )
        assert response.status_code == 204
        assert not CompanyMember.objects.filter(id=membership.id).exists()

    def test_non_owner_cannot_remove_member(self):
        _, _, company, member, membership = self._setup()
        member_client = APIClient()
        member_client.force_authenticate(user=member)
        response = member_client.delete(
            f"{COMPANIES_URL}{company.slug}/members/{membership.id}/"
        )
        assert response.status_code == 403

    def test_cannot_remove_owner(self):
        client, owner, company, member, _ = self._setup()
        owner_membership = CompanyMember.objects.get(user=owner, company=company)
        response = client.delete(
            f"{COMPANIES_URL}{company.slug}/members/{owner_membership.id}/"
        )
        assert response.status_code == 400


# ──────────────────────────────────────────────────────────────
# B3 — Recruiter's Own Jobs (?mine=true)
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMineJobsFilter:
    def _setup(self):
        recruiter = User.objects.create_user(
            email="rec@acme.com", username="rec", password="pass123!", role="recruiter",
        )
        company = Company.objects.create(
            name="Acme", slug="acme",
            domain_verified=True, verification_status="verified",
        )
        CompanyMember.objects.create(user=recruiter, company=company, role="owner")
        my_job = Job.objects.create(
            title="My Job", slug="my-job", company=company,
            posted_by=recruiter, status="published",
            description="desc", job_type="full_time", experience_level="mid",
        )
        other_recruiter = User.objects.create_user(
            email="other@test.com", username="other", password="pass123!", role="recruiter",
        )
        other_company = Company.objects.create(
            name="Other", slug="other",
            domain_verified=True, verification_status="verified",
        )
        CompanyMember.objects.create(user=other_recruiter, company=other_company, role="owner")
        other_job = Job.objects.create(
            title="Other Job", slug="other-job", company=other_company,
            posted_by=other_recruiter, status="published",
            description="desc", job_type="full_time", experience_level="mid",
        )
        client = APIClient()
        client.force_authenticate(user=recruiter)
        return client, recruiter, my_job, other_job

    def test_mine_true_returns_only_own_company_jobs(self):
        client, recruiter, my_job, other_job = self._setup()
        response = client.get(f"{JOBS_URL}?mine=true")
        assert response.status_code == 200
        slugs = [j["slug"] for j in response.json()["results"]]
        assert "my-job" in slugs
        assert "other-job" not in slugs

    def test_mine_false_returns_all_published(self):
        client, recruiter, my_job, other_job = self._setup()
        response = client.get(JOBS_URL)
        slugs = [j["slug"] for j in response.json()["results"]]
        assert "my-job" in slugs
        assert "other-job" in slugs

    def test_mine_includes_draft_jobs(self):
        client, recruiter, my_job, _ = self._setup()
        my_job.status = "draft"
        my_job.save()
        response = client.get(f"{JOBS_URL}?mine=true")
        slugs = [j["slug"] for j in response.json()["results"]]
        assert "my-job" in slugs


# ──────────────────────────────────────────────────────────────
# B4 — GET/PATCH /api/auth/me/
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCurrentUserProfile:
    def test_get_me_returns_user_data(self):
        user = UserFactory(role="candidate", email="me@test.com")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(ME_URL)
        assert response.status_code == 200
        assert response.json()["email"] == "me@test.com"

    def test_get_me_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(ME_URL)
        assert response.status_code == 401

    def test_patch_me_updates_fields(self):
        user = UserFactory(role="candidate", email="me@test.com")
        client = APIClient()
        client.force_authenticate(user=user)
        response = client.patch(ME_URL, {"first_name": "Updated"})
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.first_name == "Updated"

    def test_patch_me_cannot_change_email(self):
        user = UserFactory(role="candidate", email="me@test.com")
        client = APIClient()
        client.force_authenticate(user=user)
        client.patch(ME_URL, {"email": "hacked@test.com"})
        user.refresh_from_db()
        assert user.email == "me@test.com"

    def test_patch_me_cannot_change_role(self):
        user = UserFactory(role="candidate", email="me@test.com")
        client = APIClient()
        client.force_authenticate(user=user)
        client.patch(ME_URL, {"role": "recruiter"})
        user.refresh_from_db()
        assert user.role == "candidate"


# ──────────────────────────────────────────────────────────────
# B5 — POST /api/auth/change-password/
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestChangePassword:
    def _setup(self):
        user = User.objects.create_user(
            email="user@test.com", username="user", password="OldPass123!",
        )
        client = APIClient()
        client.force_authenticate(user=user)
        return client, user

    def test_change_password_success(self):
        client, user = self._setup()
        response = client.post(CHANGE_PASSWORD_URL, {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        })
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.check_password("NewPass456!")

    def test_wrong_old_password_returns_400(self):
        client, user = self._setup()
        response = client.post(CHANGE_PASSWORD_URL, {
            "old_password": "WrongPass!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        })
        assert response.status_code == 400

    def test_mismatched_new_passwords_returns_400(self):
        client, user = self._setup()
        response = client.post(CHANGE_PASSWORD_URL, {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "Different789!",
        })
        assert response.status_code == 400

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.post(CHANGE_PASSWORD_URL, {
            "old_password": "OldPass123!",
            "new_password": "NewPass456!",
            "new_password_confirm": "NewPass456!",
        })
        assert response.status_code == 401


# ──────────────────────────────────────────────────────────────
# B6 — POST /api/auth/avatar/
# ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAvatarUpload:
    def test_upload_avatar(self):
        user = UserFactory(role="candidate", email="avatar@test.com")
        client = APIClient()
        client.force_authenticate(user=user)
        image = _make_image()
        response = client.post(AVATAR_URL, {"avatar": image}, format="multipart")
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.avatar is not None
        assert "avatar" in user.avatar.name

    def test_upload_avatar_unauthenticated_returns_401(self):
        client = APIClient()
        image = _make_image()
        response = client.post(AVATAR_URL, {"avatar": image}, format="multipart")
        assert response.status_code == 401

    def test_upload_non_image_returns_400(self):
        user = UserFactory(role="candidate", email="avatar@test.com")
        client = APIClient()
        client.force_authenticate(user=user)
        bad_file = SimpleUploadedFile("test.txt", b"not an image", content_type="text/plain")
        response = client.post(AVATAR_URL, {"avatar": bad_file}, format="multipart")
        assert response.status_code == 400
