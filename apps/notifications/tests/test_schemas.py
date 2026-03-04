"""Tests for Pydantic payload schemas."""

import uuid

import pytest
from pydantic import ValidationError

from apps.notifications.schemas import (
    VALID_STATUSES,
    ApplicationEmailPayload,
    StatusUpdateEmailPayload,
)


class TestApplicationEmailPayload:
    def test_valid_uuid_passes(self):
        uid = str(uuid.uuid4())
        payload = ApplicationEmailPayload(application_id=uid)
        assert payload.application_id == uid

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationError):
            ApplicationEmailPayload(application_id="not-a-valid-uuid-at-all-really!!")

    def test_empty_string_raises(self):
        with pytest.raises(ValidationError):
            ApplicationEmailPayload(application_id="")

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            ApplicationEmailPayload()


class TestStatusUpdateEmailPayload:
    def test_valid_input_passes(self):
        uid = str(uuid.uuid4())
        payload = StatusUpdateEmailPayload(
            application_id=uid, old_status="applied", new_status="reviewing"
        )
        assert payload.application_id == uid
        assert payload.old_status == "applied"
        assert payload.new_status == "reviewing"

    def test_invalid_uuid_raises(self):
        with pytest.raises(ValidationError):
            StatusUpdateEmailPayload(
                application_id="bad-uuid-value-that-is-36-chars!!!",
                old_status="applied",
                new_status="reviewing",
            )

    @pytest.mark.parametrize("bad_status", ["pending", "hired", "unknown", ""])
    def test_invalid_status_raises(self, bad_status):
        uid = str(uuid.uuid4())
        with pytest.raises(ValidationError):
            StatusUpdateEmailPayload(
                application_id=uid, old_status="applied", new_status=bad_status
            )

    @pytest.mark.parametrize("valid_status", sorted(VALID_STATUSES))
    def test_all_valid_statuses_accepted(self, valid_status):
        uid = str(uuid.uuid4())
        payload = StatusUpdateEmailPayload(
            application_id=uid, old_status=valid_status, new_status=valid_status
        )
        assert payload.old_status == valid_status

    def test_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            StatusUpdateEmailPayload()
