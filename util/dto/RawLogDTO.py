from util.dto.DBModel import DBModel
from datetime import datetime
from uuid import UUID
from pydantic import Field

from util.enum.LogLevel import LogLevel


class RawLogDTO(DBModel):
    message: str
    timestamp: datetime | None = None
    stack: str | None = None

    # DB Metadata
    id: UUID | None = None
    org_id: UUID | None = None
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
    attributes: dict[str, str] = Field(default_factory=dict)

    # Log Signature
    level: LogLevel
    template: str = Field(min_length=1, max_length=10_000)
    file: str | None = Field(default=None, max_length=1_000)
    line: int | None = Field(default=None, ge=1)
    method: str | None = Field(default=None, max_length=255)