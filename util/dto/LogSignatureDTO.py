from datetime import datetime
from uuid import uuid4, UUID

from util.dto import RawLogDTO
from util.dto.DBModel import DBModel
from util.dto.LogEventDTO import LogEventDTO
from util.enum.LogLevel import LogLevel


class LogSignatureDTO(DBModel):
    id: UUID
    template: str
    line: int
    file: str
    method: str
    first_appearance_timestamp: datetime
    first_appearance_commit: str
    log_level: LogLevel

    @classmethod
    def from_log_event(cls, log_event: LogEventDTO) -> "LogSignatureDTO":
        return cls.model_validate({
            **log_event.model_dump(include=cls.model_fields.keys(), exclude="id"),
            "id": uuid4(),
            "first_appearance_timestamp": log_event.timestamp,
            "first_appearance_commit": log_event.git_sha,
        })