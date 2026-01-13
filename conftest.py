"""
Root conftest — shared fixtures for all tests.
"""

import pytest
from rest_framework.test import APIClient

from tests.factories import CompanyFactory, CompanyMemberFactory, UserFactory


@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def candidate(db):
    """A candidate user."""
    return UserFactory(role="candidate")


@pytest.fixture
def recruiter(db):
    """A recruiter user."""
    return UserFactory(role="recruiter")


@pytest.fixture
def candidate_client(api_client, candidate):
    """Authenticated API client for a candidate user."""
    api_client.force_authenticate(user=candidate)
    return api_client


@pytest.fixture
def recruiter_client(recruiter):
    """Authenticated API client for a recruiter user."""
    client = APIClient()
    client.force_authenticate(user=recruiter)
    return client


@pytest.fixture
def verified_company(db):
    """A fully verified company (domain + document)."""
    return CompanyFactory(
        domain_verified=True,
        verification_status="verified",
    )


@pytest.fixture
def pending_verification_company(db):
    """A company with domain verified but pending document review."""
    return CompanyFactory(
        domain_verified=True,
        verification_status="pending",
    )


@pytest.fixture
def recruiter_with_company(db):
    """A recruiter who owns a verified company. Returns (recruiter, company, client)."""
    membership = CompanyMemberFactory(role="owner")
    client = APIClient()
    client.force_authenticate(user=membership.user)
    return membership.user, membership.company, client
