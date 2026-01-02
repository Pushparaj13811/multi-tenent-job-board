"""
factory_boy factories for all HireFlow models.
Populated incrementally as models are added in each phase.
"""

import factory
from factory.django import DjangoModelFactory


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "accounts.User"
        django_get_or_create = ("email",)

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.LazyAttribute(
        lambda obj: f"{obj.first_name.lower()}.{obj.last_name.lower()}@example.com"
    )
    username = factory.LazyAttribute(
        lambda obj: f"{obj.first_name.lower()}_{obj.last_name.lower()}"
    )
    role = "candidate"
    phone = factory.Faker("numerify", text="+1##########")
    is_email_verified = True
    is_active = True
    password = factory.PostGenerationMethodCall("set_password", "testpass123!")


class CompanyFactory(DjangoModelFactory):
    class Meta:
        model = "companies.Company"

    name = factory.Faker("company")
    slug = factory.Sequence(lambda n: f"company-{n}")
    description = factory.Faker("paragraph")
    website = factory.Faker("url")
    industry = factory.Faker("bs")
    location = factory.Faker("city")
    domain = factory.Sequence(lambda n: f"company-{n}.com")
    domain_verified = True
    verification_status = "verified"


class CompanyMemberFactory(DjangoModelFactory):
    class Meta:
        model = "companies.CompanyMember"

    user = factory.SubFactory(UserFactory, role="recruiter")
    company = factory.SubFactory(CompanyFactory)
    role = "owner"


class JobFactory(DjangoModelFactory):
    class Meta:
        model = "jobs.Job"

    company = factory.SubFactory(CompanyFactory)
    posted_by = factory.SubFactory(UserFactory, role="recruiter")
    title = factory.Faker("sentence", nb_words=4)
    slug = factory.Sequence(lambda n: f"job-{n}")
    description = factory.Faker("text", max_nb_chars=500)
    requirements = factory.Faker("text", max_nb_chars=300)
    responsibilities = factory.Faker("text", max_nb_chars=300)
    skills = factory.LazyFunction(lambda: ["Python", "Django"])
    job_type = "full_time"
    experience_level = "mid"
    location = factory.Faker("city")
    is_remote = False
    salary_min = 50000
    salary_max = 100000
    currency = "USD"
    status = "draft"
    views_count = 0


class ApplicationFactory(DjangoModelFactory):
    class Meta:
        model = "applications.Application"

    job = factory.SubFactory(JobFactory, status="published")
    applicant = factory.SubFactory(UserFactory, role="candidate")
    resume = factory.django.FileField(
        filename="resume.pdf",
        data=b"%PDF-1.4 fake resume content",
    )
    cover_letter = factory.Faker("paragraph", nb_sentences=3)
    status = "applied"
    expected_salary = 100000
    available_from = factory.Faker("future_date", end_date="+60d")


class NotificationFactory(DjangoModelFactory):
    class Meta:
        model = "notifications.Notification"

    user = factory.SubFactory(UserFactory)
    type = "application_received"
    title = factory.Faker("sentence", nb_words=4)
    message = factory.Faker("paragraph", nb_sentences=2)
    is_read = False
    metadata = factory.LazyFunction(dict)
