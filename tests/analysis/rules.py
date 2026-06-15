import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from analysis.rules import AnalysisRule, RuleCondition, load_rules
from util.enum.LogWindow import LogWindow
from util.enum.Operator import Operator
from util.enum.RuleConditionType import RuleConditionType
from util.enum.Sensitivity import Sensitivity
from util.enum.Severity import Severity


def threshold_rule(**overrides) -> dict:
    rule = {
        "id": "fatal_logs_present",
        "window": "s",
        "metric": "log_count",
        "filter": {"level": "FATAL"},
        "condition": {"type": "threshold", "operator": ">", "value": 0},
        "severity": 50,
    }
    rule.update(overrides)
    return rule


class RuleConditionTestCase(unittest.TestCase):
    def test_threshold_condition_requires_operator_and_value(self) -> None:
        invalid_conditions = [
            {"type": "threshold", "operator": ">"},
            {"type": "threshold", "value": 0},
            {"type": "threshold"},
        ]

        for payload in invalid_conditions:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    RuleCondition.model_validate(payload)

    def test_threshold_condition_parses_operator_and_value(self) -> None:
        condition = RuleCondition.model_validate(
            {"type": "threshold", "operator": ">=", "value": 5}
        )

        self.assertEqual(condition.type, RuleConditionType.THRESHOLD)
        self.assertEqual(condition.operator, Operator.GREATER_THAN_OR_EQUAL)
        self.assertEqual(condition.value, 5)

    def test_non_threshold_condition_uses_defaults(self) -> None:
        condition = RuleCondition.model_validate({"type": "anomaly"})

        self.assertEqual(condition.type, RuleConditionType.ANOMALY)
        self.assertIsNone(condition.operator)
        self.assertIsNone(condition.value)
        self.assertIsNone(condition.method)
        self.assertEqual(condition.sensitivity, Sensitivity.MEDIUM)
        self.assertEqual(condition.direction, "both")
        self.assertIsNone(condition.z_score_threshold)
        self.assertEqual(condition.min_percent_change, 0)
        self.assertIsNone(condition.distance_threshold)
        self.assertEqual(condition.min_historical_occurrences, 1)
        self.assertEqual(condition.expected_patterns, [])
        self.assertIsNone(condition.schedule)

    def test_condition_custom_fields_parse(self) -> None:
        condition = RuleCondition.model_validate(
            {
                "type": "missing_expected_pattern",
                "method": "source_presence",
                "sensitivity": "high",
                "direction": "down",
                "z_score_threshold": 1.75,
                "min_percent_change": 0.25,
                "distance_threshold": 0.2,
                "min_historical_occurrences": 4,
                "expected_patterns": ["billing-job", "heartbeat"],
                "schedule": "business_hours",
            }
        )

        self.assertEqual(condition.method, "source_presence")
        self.assertEqual(condition.sensitivity, Sensitivity.HIGH)
        self.assertEqual(condition.direction, "down")
        self.assertEqual(condition.z_score_threshold, 1.75)
        self.assertEqual(condition.min_percent_change, 0.25)
        self.assertEqual(condition.distance_threshold, 0.2)
        self.assertEqual(condition.min_historical_occurrences, 4)
        self.assertEqual(condition.expected_patterns, ["billing-job", "heartbeat"])
        self.assertEqual(condition.schedule, "business_hours")

    def test_condition_rejects_invalid_bounds(self) -> None:
        invalid_conditions = [
            {"type": "anomaly", "z_score_threshold": 0},
            {"type": "anomaly", "min_percent_change": -0.01},
            {"type": "distribution_shift", "distance_threshold": 0},
            {"type": "missing_expected_pattern", "min_historical_occurrences": 0},
        ]

        for payload in invalid_conditions:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    RuleCondition.model_validate(payload)


class AnalysisRuleTestCase(unittest.TestCase):
    def test_analysis_rule_parses_required_fields_and_defaults(self) -> None:
        rule = AnalysisRule.model_validate(
            {
                "id": "total_volume_unusual_change",
                "window": "m",
                "metric": "total_log_count",
                "condition": {"type": "anomaly"},
            }
        )

        self.assertEqual(rule.id, "total_volume_unusual_change")
        self.assertEqual(rule.window, LogWindow.m)
        self.assertEqual(rule.metric, "total_log_count")
        self.assertEqual(rule.filter, {})
        self.assertEqual(rule.severity, Severity.MEDIUM)
        self.assertTrue(rule.enabled)
        self.assertIsNone(rule.description)
        self.assertEqual(rule.metadata, {})

    def test_analysis_rule_parses_optional_fields(self) -> None:
        payload = threshold_rule(
            enabled=False,
            description="Fatal logs indicate immediate failure.",
            metadata={"owner": "platform", "runbook": "fatal-logs"},
        )

        rule = AnalysisRule.model_validate(payload)

        self.assertFalse(rule.enabled)
        self.assertEqual(rule.severity, Severity.CRITICAL)
        self.assertEqual(rule.filter, {"level": "FATAL"})
        self.assertEqual(rule.description, "Fatal logs indicate immediate failure.")
        self.assertEqual(rule.metadata["owner"], "platform")

    def test_analysis_rule_rejects_empty_identity_fields(self) -> None:
        invalid_rules = [
            threshold_rule(id=""),
            threshold_rule(metric=""),
        ]

        for payload in invalid_rules:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    AnalysisRule.model_validate(payload)

    def test_analysis_rule_rejects_invalid_enum_values(self) -> None:
        invalid_rules = [
            threshold_rule(window="unknown"),
            threshold_rule(severity=999),
            threshold_rule(condition={"type": "not-real"}),
        ]

        for payload in invalid_rules:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    AnalysisRule.model_validate(payload)


class LoadRulesTestCase(unittest.TestCase):
    def load_from_payload(self, payload) -> list[AnalysisRule]:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.json"
            path.write_text(json.dumps(payload))
            return load_rules(path)

    def test_load_rules_reads_list_payload(self) -> None:
        rules = self.load_from_payload(
            [
                threshold_rule(),
                {
                    "id": "error_volume_anomaly",
                    "window": "s",
                    "metric": "log_count",
                    "filter": {"level": "ERROR"},
                    "condition": {"type": "anomaly", "sensitivity": "low"},
                },
            ]
        )

        self.assertEqual([rule.id for rule in rules], ["fatal_logs_present", "error_volume_anomaly"])
        self.assertEqual(rules[1].condition.sensitivity, Sensitivity.LOW)

    def test_load_rules_reads_wrapped_rules_payload(self) -> None:
        rules = self.load_from_payload({"rules": [threshold_rule(id="wrapped_rule")]})

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].id, "wrapped_rule")

    def test_load_rules_uses_empty_list_when_rules_key_is_missing(self) -> None:
        rules = self.load_from_payload({"metadata": {"version": 1}})

        self.assertEqual(rules, [])

    def test_load_rules_rejects_non_list_payloads(self) -> None:
        invalid_payloads = ["not-a-list", {"rules": {"id": "wrong-shape"}}]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.load_from_payload(payload)

    def test_load_rules_surfaces_rule_validation_errors(self) -> None:
        with self.assertRaises(ValidationError):
            self.load_from_payload([threshold_rule(condition={"type": "threshold"})])


if __name__ == "__main__":
    unittest.main()
