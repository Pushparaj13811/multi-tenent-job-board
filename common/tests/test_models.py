"""
Tests for TimeStampedModel abstract base model.
Since it's abstract, we test it through a concrete proxy model created for testing.
"""

import uuid

import pytest
from django.db import connection, models
from django.utils import timezone

from common.models import TimeStampedModel


# Concrete model for testing the abstract TimeStampedModel
class ConcreteTimeStampedModel(TimeStampedModel):
    """Concrete model to test abstract TimeStampedModel."""

    name = models.CharField(max_length=100, default="test")

    class Meta:
        app_label = "common"


@pytest.fixture(scope="session")
def concrete_model_table(django_db_setup, django_db_blocker):
    """Create the test table once per session."""
    import contextlib

    with django_db_blocker.unblock(), connection.schema_editor() as schema_editor, contextlib.suppress(Exception):
        schema_editor.create_model(ConcreteTimeStampedModel)


@pytest.mark.django_db
class TestTimeStampedModel:
    def test_model_is_abstract(self):
        """TimeStampedModel cannot be instantiated directly (it's abstract)."""
        assert TimeStampedModel._meta.abstract is True

    def test_uuid_pk_is_generated(self, concrete_model_table):
        """Primary key is auto-generated UUID4."""
        obj = ConcreteTimeStampedModel.objects.create(name="test-uuid")
        assert isinstance(obj.pk, uuid.UUID)
        assert obj.pk.version == 4

    def test_created_at_is_auto_set(self, concrete_model_table):
        """created_at is automatically set on first save."""
        before = timezone.now()
        obj = ConcreteTimeStampedModel.objects.create(name="test-created")
        after = timezone.now()
        assert before <= obj.created_at <= after

    def test_updated_at_changes_on_save(self, concrete_model_table):
        """updated_at changes when the object is saved again."""
        obj = ConcreteTimeStampedModel.objects.create(name="test-updated")
        original_updated = obj.updated_at
        obj.name = "modified"
        obj.save()
        obj.refresh_from_db()
        assert obj.updated_at > original_updated
