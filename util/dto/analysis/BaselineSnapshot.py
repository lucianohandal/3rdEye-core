from pydantic import BaseModel, Field

from util.dto.analysis.ExpectedPattern import ExpectedPattern
from util.dto.analysis.MetricBaseline import MetricBaseline


class BaselineSnapshot(BaseModel):
    metric_stats: dict[str, MetricBaseline] = Field(default_factory=dict)
    distributions: dict[str, dict[str, float]] = Field(default_factory=dict)
    expected_patterns: dict[str, ExpectedPattern] = Field(default_factory=dict)
