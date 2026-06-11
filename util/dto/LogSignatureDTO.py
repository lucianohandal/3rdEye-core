from datetime import datetime
from pydantic import BaseModel

from util.Enum.LogLevel import LogLevel


class LogSignatureDTO(BaseModel):
    id: str
    template: str
    line: int
    file: str
    stack: str
    method: str
    first_appearance_timestamp: datetime
    first_appearance_commit: str
    log_level: LogLevel
