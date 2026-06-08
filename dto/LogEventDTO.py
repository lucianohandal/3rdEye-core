from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from dto.LogLevel import LogLevel


class LogEventDTO(BaseModel):
    level: LogLevel
    message: str = Field(min_length=1, max_length=10_000)

    # Default Metadata
    service: str | None = Field(default=None, max_length=255)
    environment: str | None = Field(default=None, max_length=100)
    version: str | None = Field(default=None, max_length=100)
    git_sha: str | None = Field(default=None, max_length=100)

    # Custom Metadata
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")