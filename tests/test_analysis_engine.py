from datetime import datetime, timezone

from analysis.engine import AnalysisEngine
from analysis.models import BaselineSnapshot, ExpectedPattern, MetricBaseline
from analysis.rules import AnalysisRule, load_rules
from util.dto.database.LogSummaryDTO import LogSummaryDTO
from util.enum.Severity import Severity


def snapshot(window: str, **overrides) -> LogSummaryDTO:
    values = {
        "window": window,
        "start_time": datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        "log_count": 0,
    }
    values.update(overrides)
    return LogSummaryDTO(**values)


def test_threshold_rule_matches_fatal_logs() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "fatal_logs_present",
            "window": "s",
            "metric": "log_count",
            "filter": {"level": "FATAL"},
            "condition": {"type": "threshold", "operator": ">", "value": 0},
            "severity": 50,
        }
    )

    findings = AnalysisEngine([rule]).evaluate(
        [snapshot("s", log_count=1, counts_by_level={"FATAL": 1})]
    )

    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_anomaly_rule_uses_metric_baseline() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "error_logs_unusually_high",
            "window": "s",
            "metric": "log_count",
            "filter": {"level": "ERROR"},
            "condition": {
                "type": "anomaly",
                "sensitivity": "medium",
                "min_percent_change": 0.25,
            },
            "severity": 40,
        }
    )
    baseline = BaselineSnapshot(
        metric_stats={
            "log_count[level=ERROR]": MetricBaseline(mean=10, stddev=2, sample_count=20)
        }
    )

    findings = AnalysisEngine([rule]).evaluate(
        [snapshot("s", log_count=20, counts_by_level={"ERROR": 16})],
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].details["z_score"] == 3


def test_group_anomaly_checks_each_source_error_rate() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "error_source_rate_unusually_high",
            "window": "s",
            "metric": "source_rate",
            "filter": {"level": "ERROR"},
            "condition": {
                "type": "group_anomaly",
                "sensitivity": "medium",
                "direction": "up",
                "min_percent_change": 0.25,
            },
            "severity": 40,
        }
    )
    baseline = BaselineSnapshot(
        metric_stats={
            "source_rate[level=ERROR,sourceId=api-gateway]": MetricBaseline(
                mean=0.10,
                stddev=0.05,
                sample_count=20,
            ),
            "source_rate[level=ERROR,sourceId=worker]": MetricBaseline(
                mean=0.50,
                stddev=0.10,
                sample_count=20,
            ),
        }
    )

    findings = AnalysisEngine([rule]).evaluate(
        [
            snapshot(
                "s",
                log_count=100,
                counts_by_level={"ERROR": 20},
                counts_by_source_id={
                    "api-gateway": 8,
                    "worker": 10,
                    "scheduler": 2,
                    "info-service": 80,
                },
                source_id_by_log_level={
                    "ERROR": {"api-gateway", "worker", "scheduler"},
                    "INFO": {"info-service"},
                },
            )
        ],
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].details["group_key"] == "api-gateway"
    assert findings[0].details["sourceId"] == "api-gateway"
    assert findings[0].observed_value == 0.4


def test_distribution_shift_rule_reports_top_changes() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "level_distribution_unusual_change",
            "window": "m",
            "metric": "level_distribution",
            "condition": {"type": "distribution_shift", "distance_threshold": 0.2},
        }
    )
    baseline = BaselineSnapshot(distributions={"level_distribution": {"INFO": 0.9, "ERROR": 0.1}})

    findings = AnalysisEngine([rule]).evaluate(
        [snapshot("m", log_count=100, counts_by_level={"INFO": 50, "ERROR": 50})],
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].observed_value == 0.4
    assert findings[0].details["top_changes"][0]["key"] in {"INFO", "ERROR"}


def test_missing_expected_pattern_uses_baseline_sources() -> None:
    rule = AnalysisRule.model_validate(
        {
            "id": "missing_expected_logs",
            "window": "l",
            "metric": "source_presence",
            "condition": {
                "type": "missing_expected_pattern",
                "min_historical_occurrences": 5,
            },
            "severity": 40,
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
        [snapshot("l", counts_by_source_id={"other-source": 1})],
        baseline,
    )

    assert len(findings) == 1
    assert findings[0].details["missing_source_ids"] == ["daily-job-finished"]


def test_default_rules_load() -> None:
    rules = load_rules("analysis/default_rules.json")

    assert {rule.id for rule in rules} >= {
        "fatal_logs_present",
        "total_volume_unusual_change",
        "missing_expected_logs",
    }
