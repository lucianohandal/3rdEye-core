from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from util.dto.api.LogEventDTO import LogEventDTO
from util.dto.database.DBModel import DBModel
from util.enum.LogLevel import LogLevel


class LogSignatureDTO(DBModel):
    template: str
    line: int
    file: str
    method: str
    first_appearance_timestamp: datetime
    first_appearance_commit: str | None = None
    log_level: LogLevel

    @classmethod
    def from_log_event(cls, log_event: LogEventDTO, org_id: UUID, **overrides: Any) -> "LogSignatureDTO":
        data = log_event.model_dump()
        data.update(overrides)
        data["id"] = uuid4()
        data["org_id"] = org_id
        data["first_appearance_timestamp"] = log_event.timestamp
        data["first_appearance_commit"] = log_event.git_sha
        data["log_level"] = log_event.level
        return cls.model_validate(data)
