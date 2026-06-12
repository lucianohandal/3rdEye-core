from typing import Any
from datetime import datetime, timezone
from pydantic import ConfigDict, Field

from util.dto.DBModel import DBModel
from util.enum.LogLevel import LogLevel

class LogEventDTO(DBModel):
    template: str = Field(min_length=1, max_length=10_000)

    message: str = Field(min_length=1, max_length=10_000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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

    # Custom Metadata
    attributes: dict[str, str] = Field(default_factory=dict)

    # Log Signature
    level: LogLevel
    file: str | None = Field(default=None, max_length=1_000)
    line: int | None = Field(default=None, ge=1)
    method: str | None = Field(default=None, max_length=255)


    model_config = ConfigDict(extra="forbid")
