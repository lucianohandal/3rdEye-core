from datetime import datetime
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


class AggregateSnapshot(BaseModel):
    window: str
    start: datetime
    end: datetime
    total_logs: int = Field(default=0, ge=0)
    counts_by_level: dict[str, int] = Field(default_factory=dict)
    counts_by_template: dict[str, int] = Field(default_factory=dict)

    def metric_value(self, metric: str, filters: dict[str, Any] | None = None) -> float:
        filters = filters or {}

        if metric == "total_log_count":
            return float(self.total_logs)

        if metric == "log_count":
            level = filters.get("level")
            if level is None:
                return float(self.total_logs)
            return float(self.counts_by_level.get(str(level).upper(), 0))

        if metric == "template_presence":
            template = filters.get("template")
            if template is None:
                return float(len([count for count in self.counts_by_template.values() if count > 0]))
            return float(self.counts_by_template.get(str(template), 0))

        raise ValueError(f"Unsupported metric: {metric}")

    def distribution(self, metric: str) -> dict[str, float]:
        if metric == "level_distribution":
            return _normalize_counts(self.counts_by_level)
        if metric == "template_distribution":
            return _normalize_counts(self.counts_by_template)
        raise ValueError(f"Unsupported distribution metric: {metric}")


class AnalysisFinding(BaseModel):
    rule_id: str
    window: str
    severity: str
    message: str
    observed_value: float | None = None
    expected_value: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


def _normalize_counts(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {key: count / total for key, count in counts.items()}
