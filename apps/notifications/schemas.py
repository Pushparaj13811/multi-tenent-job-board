from uuid import UUID

from pydantic import BaseModel, Field, field_validator

VALID_STATUSES = frozenset({
    "applied", "reviewing", "shortlisted",
    "interview", "offered", "rejected", "withdrawn",
})


class ApplicationEmailPayload(BaseModel):
    """Validates send_application_received_email task payload."""

    application_id: str = Field(..., min_length=36, max_length=36)

    @field_validator("application_id")
    @classmethod
    def must_be_valid_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError as err:
            raise ValueError(f"'{v}' is not a valid UUID.") from err
        return v


class StatusUpdateEmailPayload(BaseModel):
    """Validates send_status_update_email task payload."""

    application_id: str = Field(..., min_length=36, max_length=36)
    old_status: str = Field(...)
    new_status: str = Field(...)

    @field_validator("application_id")
    @classmethod
    def must_be_valid_uuid(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError as err:
            raise ValueError(f"'{v}' is not a valid UUID.") from err
        return v

    @field_validator("old_status", "new_status")
    @classmethod
    def must_be_valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"'{v}' is not a valid application status. "
                f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        return v
