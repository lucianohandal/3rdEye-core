from datetime import datetime, timezone
import unittest
from uuid import uuid4

from analysis.engine import AnalysisEngine
from analysis.rules import AnalysisRule, load_rules
from util.dto.analysis.BaselineSnapshot import BaselineSnapshot
from util.dto.analysis.ExpectedPattern import ExpectedPattern
from util.dto.analysis.MetricBaseline import MetricBaseline
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.enum.Severity import Severity


def snapshot(window: str, **overrides) -> LogSummaryDTO:
    counts_by_level = overrides.pop("counts_by_level", {})
    counts_by_source_id = overrides.pop("counts_by_source_id", {})
    source_id_by_log_level = overrides.pop("source_id_by_log_level", {})
    values = {
        "id": uuid4(),
        "org_id": uuid4(),
        "time_window": window,
        "start_time": datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        "log_count": 0,
    }
    values.update(overrides)
    summary = LogSummaryDTO(**values)
    summary.counts_by_level.update(counts_by_level)
    summary.counts_by_source_id.update(counts_by_source_id)
    summary.source_id_by_log_level.update(source_id_by_log_level)
    return summary


class AnalysisEngineTestCase(unittest.TestCase):
    def test_disabled_rules_are_not_evaluated(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "disabled_rule",
                "window": "s",
                "metric": "log_count",
                "condition": {"type": "threshold", "operator": ">", "value": 0},
                "enabled": False,
            }
        )

        findings = AnalysisEngine([rule]).evaluate([snapshot("s", log_count=5)])

        self.assertEqual(findings, [])

    def test_threshold_rule_matches_fatal_logs(self) -> None:
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

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, Severity.CRITICAL)

    def test_threshold_rule_ignores_non_matching_snapshot(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "too_many_errors",
                "window": "s",
                "metric": "log_count",
                "filter": {"level": "ERROR"},
                "condition": {"type": "threshold", "operator": ">", "value": 10},
            }
        )

        findings = AnalysisEngine([rule]).evaluate(
            [snapshot("s", counts_by_level={"ERROR": 2})]
        )

        self.assertEqual(findings, [])

    def test_anomaly_rule_uses_metric_baseline(self) -> None:
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

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details["z_score"], 3)

    def test_anomaly_rule_requires_baseline(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "error_logs_unusually_high",
                "window": "s",
                "metric": "log_count",
                "filter": {"level": "ERROR"},
                "condition": {"type": "anomaly"},
            }
        )

        findings = AnalysisEngine([rule]).evaluate(
            [snapshot("s", counts_by_level={"ERROR": 16})]
        )

        self.assertEqual(findings, [])

    def test_anomaly_rule_handles_zero_variance_baseline(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "total_volume_changed",
                "window": "s",
                "metric": "total_log_count",
                "condition": {"type": "anomaly", "min_percent_change": 0.25},
            }
        )
        baseline = BaselineSnapshot(
            metric_stats={
                "total_log_count": MetricBaseline(mean=10, stddev=0, sample_count=5)
            }
        )

        findings = AnalysisEngine([rule]).evaluate(
            [snapshot("s", counts_by_level={"INFO": 20})],
            baseline,
        )

        self.assertEqual(len(findings), 1)
        self.assertNotIn("z_score", findings[0].details)
        self.assertEqual(findings[0].observed_value, 20)

    def test_anomaly_rule_respects_direction(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "total_volume_dropped",
                "window": "s",
                "metric": "total_log_count",
                "condition": {"type": "anomaly", "direction": "down"},
            }
        )
        baseline = BaselineSnapshot(
            metric_stats={
                "total_log_count": MetricBaseline(mean=10, stddev=1, sample_count=5)
            }
        )

        upward_findings = AnalysisEngine([rule]).evaluate(
            [snapshot("s", counts_by_level={"INFO": 20})],
            baseline,
        )
        downward_findings = AnalysisEngine([rule]).evaluate(
            [snapshot("s", counts_by_level={"INFO": 5})],
            baseline,
        )

        self.assertEqual(upward_findings, [])
        self.assertEqual(len(downward_findings), 1)

    def test_group_anomaly_checks_each_source_error_rate(self) -> None:
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

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details["group_key"], "api-gateway")
        self.assertEqual(findings[0].details["sourceId"], "api-gateway")
        self.assertEqual(findings[0].observed_value, 0.4)

    def test_group_anomaly_skips_groups_without_baselines(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "error_source_rate_unusually_high",
                "window": "s",
                "metric": "source_rate",
                "filter": {"level": "ERROR"},
                "condition": {"type": "group_anomaly"},
            }
        )
        baseline = BaselineSnapshot(
            metric_stats={
                "source_rate[level=ERROR,sourceId=worker]": MetricBaseline(
                    mean=0.5,
                    stddev=0.1,
                    sample_count=10,
                )
            }
        )

        findings = AnalysisEngine([rule]).evaluate(
            [
                snapshot(
                    "s",
                    counts_by_level={"ERROR": 10},
                    counts_by_source_id={"api-gateway": 10},
                    source_id_by_log_level={"ERROR": {"api-gateway"}},
                )
            ],
            baseline,
        )

        self.assertEqual(findings, [])

    def test_distribution_shift_rule_reports_top_changes(self) -> None:
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

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].observed_value, 0.4)
        self.assertIn(findings[0].details["top_changes"][0]["key"], {"INFO", "ERROR"})

    def test_distribution_shift_requires_observed_and_expected_distribution(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "level_distribution_unusual_change",
                "window": "m",
                "metric": "level_distribution",
                "condition": {"type": "distribution_shift"},
            }
        )

        missing_observed = AnalysisEngine([rule]).evaluate(
            [snapshot("m")],
            BaselineSnapshot(distributions={"level_distribution": {"INFO": 1.0}}),
        )
        missing_expected = AnalysisEngine([rule]).evaluate(
            [snapshot("m", counts_by_level={"INFO": 1})],
            BaselineSnapshot(),
        )

        self.assertEqual(missing_observed, [])
        self.assertEqual(missing_expected, [])

    def test_missing_expected_pattern_uses_baseline_sources(self) -> None:
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

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details["missing_source_ids"], ["daily-job-finished"])

    def test_missing_expected_pattern_uses_explicit_condition_patterns(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "missing_expected_logs",
                "window": "l",
                "metric": "source_presence",
                "condition": {
                    "type": "missing_expected_pattern",
                    "expected_patterns": ["heartbeat", "billing-job"],
                    "schedule": "business_hours",
                },
            }
        )

        findings = AnalysisEngine([rule]).evaluate(
            [snapshot("l", counts_by_source_id={"heartbeat": 3})],
            BaselineSnapshot(),
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details["missing_source_ids"], ["billing-job"])
        self.assertEqual(findings[0].details["schedule"], "business_hours")

    def test_default_rules_load(self) -> None:
        rules = load_rules("analysis/default_rules.json")

        self.assertGreaterEqual(
            {rule.id for rule in rules},
            {
                "fatal_logs_present",
                "total_volume_unusual_change",
                "missing_expected_logs",
            },
        )


if __name__ == "__main__":
    unittest.main()
