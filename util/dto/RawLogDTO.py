from util.dto.DBModel import DBModel
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4
from pydantic import Field

from util.dto.LogEventDTO import LogEventDTO


class RawLogDTO(DBModel):
    id: UUID

    org_id: UUID | None = None
    signature_id: UUID  | None = None

    message: str
    timestamp: datetime | None = None
    stack: str | None = None

    # Environment Metadata
    service: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=100)
    version: str | None = Field(default=None, max_length=100)
    git_sha: str | None = Field(default=None, max_length=100)

    # Correlation Metadata
    trace_id: str | None = Field(default=None, max_length=255)
    span_id: str | None = Field(default=None, max_length=255)
    request_id: str | None = Field(default=None, max_length=255)
    user_id: str | None = Field(default=None, max_length=255)

    attributes: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_log_event(cls, signature_id, log_event: LogEventDTO) -> "RawLogDTO":
        return cls.model_validate({
            **log_event.model_dump(include=cls.model_fields.keys()),
            "id": signature_id,
        })