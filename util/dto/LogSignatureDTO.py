from datetime import datetime, timezone
from uuid import uuid4, UUID

from util.dto.DBModel import DBModel
from util.dto.RawLogDTO import RawLogDTO
from util.enum.LogLevel import LogLevel


class LogSignatureDTO(DBModel):
    id: UUID
    template: str
    line: int
    file: str
    method: str
    first_appearance_timestamp: datetime
    first_appearance_commit: str | None = None
    log_level: LogLevel

    @classmethod
    def from_raw_logs(cls, log_event: RawLogDTO) -> "LogSignatureDTO":
        return cls(
            id=uuid4(),
            template=log_event.template,
            line=log_event.line,
            file=log_event.file,
            method=log_event.method,
            first_appearance_timestamp=log_event.timestamp or datetime.now(timezone.utc),
            first_appearance_commit=log_event.git_sha,
            log_level=log_event.level,
        )
