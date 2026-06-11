from typing import Any

from pydantic import BaseModel, Field


class MetricBaseline(BaseModel):
    mean: float
    stddev: float = Field(default=0, ge=0)
    sample_count: int = Field(default=0, ge=0)


class ExpectedPattern(BaseModel):
    key: str
    historical_occurrences: int = Field(default=0, ge=0)
    schedule: str | None = None


class BaselineSnapshot(BaseModel):
    metric_stats: dict[str, MetricBaseline] = Field(default_factory=dict)
    distributions: dict[str, dict[str, float]] = Field(default_factory=dict)
    expected_patterns: dict[str, ExpectedPattern] = Field(default_factory=dict)


class AnalysisFinding(BaseModel):
    rule_id: str
    window: str
    severity: str
    message: str
    observed_value: float | None = None
    expected_value: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
