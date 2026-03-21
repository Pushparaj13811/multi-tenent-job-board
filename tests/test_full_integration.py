"""Full end-to-end integration test — exercises the entire HireFlow system."""

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestFullWorkflow:
    def _register_and_login(self, client, email, username, first, last, role):
        """Register a user, then login to get JWT tokens."""
        password = "StrongPass123!"
        resp = client.post(
            "/api/auth/register/",
            {
                "email": email,
                "username": username,
                "first_name": first,
                "last_name": last,
                "password": password,
                "password_confirm": password,
                "role": role,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        resp = client.post(
            "/api/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        return resp.data

    def test_complete_happy_path(self):
        client = APIClient()

        # 1. Register + login recruiter
        recruiter_tokens = self._register_and_login(
            client, "recruiter@integ.com", "integ_recruiter", "Integ", "Recruiter", "recruiter"
        )

        # 2. Register + login candidate
        candidate_tokens = self._register_and_login(
            client, "candidate@integ.com", "integ_candidate", "Integ", "Candidate", "candidate"
        )

        # 3. Recruiter creates company
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {recruiter_tokens['access']}"
        )
        resp = client.post(
            "/api/companies/",
            {
                "name": "Integration Corp",
                "slug": "integration-corp",
                "description": "A test company.",
                "industry": "Tech",
                "location": "Remote",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        company_id = resp.data["id"]

        # 4. Recruiter creates job
        resp = client.post(
            "/api/jobs/",
            {
                "title": "Integration Engineer",
                "slug": "integ-engineer",
                "description": "Build integrations.",
                "requirements": "Python experience.",
                "responsibilities": "Write code.",
                "skills": ["Python"],
                "job_type": "full_time",
                "experience_level": "mid",
                "location": "Remote",
                "salary_min": 100000,
                "salary_max": 150000,
                "company": company_id,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        job_id = resp.data["id"]
        job_slug = resp.data["slug"]

        # 5. Recruiter publishes job
        resp = client.post(f"/api/jobs/{job_slug}/publish/")
        assert resp.status_code == status.HTTP_200_OK

        # 6. Candidate applies
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {candidate_tokens['access']}"
        )
        mail.outbox.clear()
        resume = SimpleUploadedFile(
            "resume.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        resp = client.post(
            "/api/applications/",
            {"job": job_id, "resume": resume},
            format="multipart",
        )
        assert resp.status_code == status.HTTP_201_CREATED
        app_id = resp.data["id"]
        # Verify application-received email
        assert any("Application received" in e.subject for e in mail.outbox)

        # 7. Recruiter advances status through pipeline
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {recruiter_tokens['access']}"
        )
        for next_status in ["reviewing", "shortlisted", "interview", "offered"]:
            mail.outbox.clear()
            resp = client.patch(
                f"/api/applications/{app_id}/status/",
                {"status": next_status},
                format="json",
            )
            assert resp.status_code == status.HTTP_200_OK
            assert any("status has been updated" in e.subject for e in mail.outbox)

        # 8. Recruiter checks dashboard
        resp = client.get("/api/dashboard/recruiter/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_jobs"] == 1
        assert resp.data["total_applications"] == 1

        # 9. Candidate checks dashboard
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {candidate_tokens['access']}"
        )
        resp = client.get("/api/dashboard/candidate/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["total_applications"] == 1

        # 10. Candidate checks notifications
        resp = client.get("/api/notifications/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["unread_count"] >= 1
