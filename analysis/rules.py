import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


RuleConditionType = Literal[
    "threshold",
    "anomaly",
    "group_anomaly",
    "distribution_shift",
    "missing_expected_pattern",
]


class RuleCondition(BaseModel):
    type: RuleConditionType
    operator: Literal[">", ">=", "<", "<=", "==", "!="] | None = None
    value: float | None = None
    method: str | None = None
    sensitivity: Literal["low", "medium", "high"] = "medium"
    direction: Literal["up", "down", "both"] = "both"
    z_score_threshold: float | None = Field(default=None, gt=0)
    min_percent_change: float = Field(default=0, ge=0)
    distance_threshold: float | None = Field(default=None, gt=0)
    min_historical_occurrences: int = Field(default=1, ge=1)
    expected_patterns: list[str] = Field(default_factory=list)
    schedule: str | None = None

    @model_validator(mode="after")
    def validate_condition(self) -> "RuleCondition":
        if self.type == "threshold" and (self.operator is None or self.value is None):
            raise ValueError("threshold conditions require operator and value")
        return self


class AnalysisRule(BaseModel):
    id: str = Field(min_length=1)
    window: str = Field(pattern=r"^\d+[mhd]$")
    metric: str = Field(min_length=1)
    condition: RuleCondition
    filter: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["info", "low", "medium", "high", "critical"] = "medium"
    enabled: bool = True
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def load_rules(path: str | Path) -> list[AnalysisRule]:
    rule_path = Path(path)
    data = json.loads(rule_path.read_text())
    if isinstance(data, dict):
        data = data.get("rules", [])
    if not isinstance(data, list):
        raise ValueError("Rules file must contain a list or an object with a 'rules' list")
    return [AnalysisRule.model_validate(item) for item in data]
