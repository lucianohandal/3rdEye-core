from typing import Any

from pydantic import Field
from util.dto.DBModel import DBModel
from util.enum.LogWindow import LogWindow
from util.enum.Severity import Severity


class AlertDTO(DBModel):
    rule_id: str
    window: LogWindow
    severity: Severity
    message: str
    observed_value: float | None = None
    expected_value: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
