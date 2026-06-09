from typing import Any
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from dto.LogLevel import LogLevel


class LogEventDTO(BaseModel):
    level: LogLevel
    message: str = Field(min_length=1, max_length=10_000)
    args: list[Any]
    template: str = Field(min_length=1, max_length=10_000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Default Metadata
    service: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=100)
    version: str | None = Field(default=None, max_length=100)
    git_sha: str | None = Field(default=None, max_length=100)

    # Correlation Metadata
    trace_id: str | None = Field(default=None, max_length=255)
    span_id: str | None = Field(default=None, max_length=255)
    request_id: str | None = Field(default=None, max_length=255)
    user_id: str | None = Field(default=None, max_length=255)

    # Source Metadata
    file: str | None = Field(default=None, max_length=1_000)
    line: int | None = Field(default=None, ge=1)
    function: str | None = Field(default=None, max_length=255)
    stack: str | None = None

    # Custom Metadata
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
