"""Tests for seed_data management command."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.applications.models import Application
from apps.companies.models import Company
from apps.jobs.models import Job


@pytest.mark.django_db
class TestSeedDataCommand:
    def test_seed_creates_users(self):
        call_command("seed_data")
        assert User.objects.filter(role="recruiter").count() == 2
        assert User.objects.filter(role="candidate").count() == 5

    def test_seed_creates_companies_and_jobs(self):
        call_command("seed_data")
        assert Company.objects.count() == 2
        assert Job.objects.count() == 6

    def test_seed_creates_applications(self):
        call_command("seed_data")
        assert Application.objects.count() == 15

    def test_seed_flush_wipes_and_recreates(self):
        call_command("seed_data")
        assert Application.objects.count() == 15
        call_command("seed_data", flush=True)
        assert User.objects.filter(role="recruiter").count() == 2
        assert User.objects.filter(role="candidate").count() == 5
        assert Company.objects.count() == 2
        assert Job.objects.count() == 6
        assert Application.objects.count() == 15
