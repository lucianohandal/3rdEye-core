from datetime import datetime
from typing import Any

from pydantic import Field, BaseModel

from util.enum.LogLevel import LogLevel


class LogEventDTO(BaseModel):
    message: str
    timestamp: datetime
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
    attributes: dict[str, Any] = Field(default_factory=dict)

    # Log Signature
    level: LogLevel
    template: str = Field(min_length=1, max_length=10_000)
    file: str = Field(max_length=1_000)
    line: int = Field(ge=1)
    method: str = Field(max_length=255)

    def signature_key(self) -> tuple[str, str, str, int]:
        return (
            self.file,
            self.template,
            self.method,
            self.line,
        )
