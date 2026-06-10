from datetime import datetime, timezone

from analysis.engine import AnalysisEngine
from analysis.models import AggregateSnapshot, BaselineSnapshot, ExpectedPattern, MetricBaseline
from analysis.rules import AnalysisRule, load_rules


def snapshot(window: str, **overrides) -> AggregateSnapshot:
    values = {
        "window": window,
        "start": datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc),
        "total_logs": 0,
    }
    values.update(overrides)
    return AggregateSnapshot(**values)


def test_threshold_rule_matches_fatal_logs() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "fatal_logs_present",
            "window": "5m",
            "metric": "log_count",
            "filter": {"level": "FATAL"},
            "condition": {"type": "threshold", "operator": ">", "value": 0},
            "severity": "critical",
        }
    )

    findings = AnalysisEngine([rule]).evaluate(
        snapshot("5m", total_logs=1, counts_by_level={"FATAL": 1})
    )

    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_anomaly_rule_uses_metric_baseline() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "error_logs_unusually_high",
            "window": "5m",
            "metric": "log_count",
            "filter": {"level": "ERROR"},
            "condition": {
                "type": "anomaly",
                "sensitivity": "medium",
                "min_percent_change": 0.25,
            },
            "severity": "high",
        }
    )
    baseline = BaselineSnapshot(
        metric_stats={
            "log_count[level=ERROR]": MetricBaseline(mean=10, stddev=2, sample_count=20)
        }
    )

    findings = AnalysisEngine([rule]).evaluate(
        snapshot("5m", total_logs=20, counts_by_level={"ERROR": 16}),
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].details["z_score"] == 3


def test_distribution_shift_rule_reports_top_changes() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "level_distribution_unusual_change",
            "window": "30m",
            "metric": "level_distribution",
            "condition": {"type": "distribution_shift", "distance_threshold": 0.2},
        }
    )
    baseline = BaselineSnapshot(distributions={"level_distribution": {"INFO": 0.9, "ERROR": 0.1}})

    findings = AnalysisEngine([rule]).evaluate(
        snapshot("30m", total_logs=100, counts_by_level={"INFO": 50, "ERROR": 50}),
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].observed_value == 0.4
    assert findings[0].details["top_changes"][0]["key"] in {"INFO", "ERROR"}


def test_missing_expected_pattern_uses_baseline_patterns() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "missing_expected_logs",
            "window": "3h",
            "metric": "template_presence",
            "condition": {
                "type": "missing_expected_pattern",
                "min_historical_occurrences": 5,
            },
            "severity": "high",
        }
    )
    baseline = BaselineSnapshot(
        expected_patterns={
            "daily-job-finished": ExpectedPattern(
                key="daily-job-finished",
                historical_occurrences=10,
                schedule="business_days",
            )
        }
    )

    findings = AnalysisEngine([rule]).evaluate(
        snapshot("3h", counts_by_template={"other-template": 1}),
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].details["missing_patterns"] == ["daily-job-finished"]


def test_default_rules_load() -> None:
    rules = load_rules("analysis/default_rules.json")

    assert {rule.id for rule in rules} >= {
        "fatal_logs_present",
        "total_volume_unusual_change",
        "missing_expected_logs",
    }
