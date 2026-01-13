import datetime

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.applications.models import Application
from apps.companies.models import Company, CompanyMember
from apps.jobs.models import Job


class Command(BaseCommand):
    help = "Seed the database with sample data for development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all non-superuser data before seeding.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write("Flushing existing data...")
            Application.objects.all().delete()
            Job.objects.all().delete()
            CompanyMember.objects.all().delete()
            Company.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()

        # ── Users ──
        recruiters = []
        recruiter_data = [
            ("Alice", "Johnson", "recruiter@acme.com"),
            ("Bob", "Smith", "recruiter@globex.com"),
        ]
        for first, last, email in recruiter_data:
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email.replace("@", "_at_").replace(".", "_"),
                    "first_name": first,
                    "last_name": last,
                    "role": "recruiter",
                    "is_email_verified": True,
                },
            )
            user.set_password("testpass123")
            user.save()
            recruiters.append(user)

        candidates = []
        for i in range(1, 6):
            user, _ = User.objects.get_or_create(
                email=f"candidate{i}@example.com",
                defaults={
                    "username": f"candidate{i}",
                    "first_name": "Candidate",
                    "last_name": f"#{i}",
                    "role": "candidate",
                    "is_email_verified": True,
                },
            )
            user.set_password("testpass123")
            user.save()
            candidates.append(user)

        # ── Companies ──
        acme, _ = Company.objects.get_or_create(
            slug="acme-corp",
            defaults={
                "name": "Acme Corp",
                "description": "Leading technology company.",
                "location": "San Francisco, CA",
                "industry": "Technology",
                "domain_verified": True,
                "verification_status": "verified",
            },
        )
        CompanyMember.objects.get_or_create(
            user=recruiters[0], company=acme, defaults={"role": "owner"}
        )

        globex, _ = Company.objects.get_or_create(
            slug="globex-corp",
            defaults={
                "name": "Globex Corporation",
                "description": "Global engineering solutions.",
                "location": "New York, NY",
                "industry": "Engineering",
                "domain_verified": True,
                "verification_status": "verified",
            },
        )
        CompanyMember.objects.get_or_create(
            user=recruiters[1], company=globex, defaults={"role": "owner"}
        )

        # ── Jobs ──
        deadline = timezone.now().date() + datetime.timedelta(days=30)
        job_data = [
            ("Senior Django Developer", "senior-django-dev", acme, recruiters[0], "full_time", "senior", 150000, 200000),
            ("Frontend React Engineer", "frontend-react", acme, recruiters[0], "full_time", "mid", 120000, 160000),
            ("DevOps Engineer", "devops-eng", acme, recruiters[0], "contract", "senior", 140000, 180000),
            ("Junior Python Developer", "junior-python", globex, recruiters[1], "full_time", "junior", 70000, 90000),
            ("Data Analyst", "data-analyst", globex, recruiters[1], "full_time", "mid", 100000, 130000),
            ("QA Engineer", "qa-engineer", globex, recruiters[1], "part_time", "mid", 80000, 110000),
        ]
        jobs = []
        for title, slug, company, posted_by, job_type, exp, sal_min, sal_max in job_data:
            job, _ = Job.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "company": company,
                    "posted_by": posted_by,
                    "description": f"We are looking for a {title}.",
                    "requirements": f"Experience as a {title}.",
                    "responsibilities": f"Responsibilities of a {title}.",
                    "skills": ["Python", "Django"],
                    "job_type": job_type,
                    "experience_level": exp,
                    "location": company.location,
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "status": "published",
                    "deadline": deadline,
                },
            )
            jobs.append(job)

        # ── Applications ──
        statuses = ["applied", "reviewing", "shortlisted", "interview", "offered"]
        status_idx = 0
        app_count = 0
        for candidate in candidates:
            for job in jobs[:3]:
                _, created = Application.objects.get_or_create(
                    job=job,
                    applicant=candidate,
                    defaults={
                        "resume": ContentFile(
                            b"%PDF-1.4 fake resume", name="resume.pdf"
                        ),
                        "cover_letter": f"I am interested in {job.title}.",
                        "status": statuses[status_idx % len(statuses)],
                    },
                )
                if created:
                    app_count += 1
                    status_idx += 1

        user_count = User.objects.filter(is_superuser=False).count()
        company_count = Company.objects.count()
        job_count = Job.objects.count()
        total_apps = Application.objects.count()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeed complete:\n"
                f"  Users:        {user_count}\n"
                f"  Companies:    {company_count}\n"
                f"  Jobs:         {job_count}\n"
                f"  Applications: {total_apps}\n"
            )
        )
