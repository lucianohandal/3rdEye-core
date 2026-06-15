from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from util.dto.api.LogEventDTO import LogEventDTO
from util.dto.database.DBModel import DBModel


class RawLogDTO(DBModel):
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stack: str | None = None

    # DB Metadata
    signature_id: UUID | None = None

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

    # Custom Metadata
    attributes: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_log_event(cls, log_event: LogEventDTO, org_id: UUID, signature_id: UUID, **overrides: Any) -> "RawLogDTO":
        data = log_event.model_dump()
        data.update(overrides)
        data["id"] = uuid4()
        data["org_id"] = org_id
        data["signature_id"] = signature_id
        return cls.model_validate(data)
