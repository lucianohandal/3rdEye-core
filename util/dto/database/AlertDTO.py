from datetime import datetime, timezone
from typing import Any

from pydantic import Field
from util.dto.database.DBModel import DBModel
from util.enum.Severity import Severity


class AlertDTO(DBModel):
    rule_id: str
    severity: Severity
    message: str
    observed_value: float | None = None
    expected_value: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
