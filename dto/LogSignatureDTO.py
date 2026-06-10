from dataclasses import dataclass
from datetime import datetime

from dto.LogLevel import LogLevel


@dataclass(frozen=True, slots=True)
class LogSignatureDTO:
    id: str
    template: str
    line: int
    file: str
    stack: str
    method: str
    first_appearance_timestamp: datetime
    first_appearance_commit: str
    log_level: LogLevel
