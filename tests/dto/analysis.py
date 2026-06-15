from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from util.dto.analysis.BaselineSnapshot import BaselineSnapshot
from util.dto.analysis.ExpectedPattern import ExpectedPattern
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.dto.analysis.MetricBaseline import MetricBaseline

from tests.dto.database import (
    assert_db_model_contract,
    nullable_field_names,
    random_model_data,
)


class AnalysisDTOInitializationTestCase(unittest.TestCase):
    def test_analysis_dtos_init_with_all_values(self) -> None:
        for model_class in [ExpectedPattern, MetricBaseline, BaselineSnapshot, LogSummaryDTO]:
            with self.subTest(model_class=model_class.__name__):
                data = random_model_data(model_class)
                dto = model_class.model_validate(data)

                for field, value in data.items():
                    self.assertEqual(getattr(dto, field), value)

    def test_analysis_dtos_init_with_nullable_values(self) -> None:
        for model_class in [ExpectedPattern, MetricBaseline, BaselineSnapshot, LogSummaryDTO]:
            with self.subTest(model_class=model_class.__name__):
                data = random_model_data(model_class, nullable=True)
                dto = model_class.model_validate(data)

                self.assertIsInstance(dto, model_class)
                for field in nullable_field_names(model_class):
                    self.assertIsNone(getattr(dto, field))

    def test_expected_pattern_json_samples_parse(self) -> None:
        samples = [
            {"key": "billing-job-finished", "historical_occurrences": 12, "schedule": "business_days"},
            {"key": "worker-heartbeat", "historical_occurrences": 240, "schedule": None},
        ]

        for sample in samples:
            with self.subTest(key=sample["key"]):
                dto = ExpectedPattern.model_validate_json(json.dumps(sample))
                self.assertEqual(dto.key, sample["key"])
                self.assertEqual(dto.schedule, sample["schedule"])

    def test_metric_baseline_json_samples_parse(self) -> None:
        samples = [
            {"mean": 81.5, "stddev": 12.3, "sample_count": 30},
            {"mean": 0.37, "stddev": 0.08, "sample_count": 14},
        ]

        for sample in samples:
            with self.subTest(mean=sample["mean"]):
                dto = MetricBaseline.model_validate_json(json.dumps(sample))
                self.assertEqual(dto.mean, sample["mean"])
                self.assertEqual(dto.sample_count, sample["sample_count"])

    def test_baseline_snapshot_json_samples_parse(self) -> None:
        samples = [
            {
                "metric_stats": {
                    "log_count[level=ERROR]": {"mean": 12.0, "stddev": 3.1, "sample_count": 20}
                },
                "distributions": {"level_distribution": {"INFO": 0.9, "ERROR": 0.1}},
                "expected_patterns": {
                    "billing-job-finished": {
                        "key": "billing-job-finished",
                        "historical_occurrences": 10,
                        "schedule": "business_days",
                    }
                },
            },
            {
                "metric_stats": {
                    "source_rate[level=ERROR,sourceId=api]": {"mean": 0.18, "stddev": 0.05, "sample_count": 12}
                },
                "distributions": {"source_distribution": {"api": 0.6, "worker": 0.4}},
                "expected_patterns": {},
            },
        ]

        for sample in samples:
            with self.subTest(keys=list(sample["metric_stats"])):
                dto = BaselineSnapshot.model_validate_json(json.dumps(sample))
                self.assertEqual(set(dto.metric_stats), set(sample["metric_stats"]))
                self.assertEqual(set(dto.distributions), set(sample["distributions"]))

    def test_log_summary_json_samples_parse(self) -> None:
        samples = [
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "time_window": "s",
                "start_time": "2026-06-10T12:00:00Z",
                "seasonality": ["business_hours"],
                "processed_at": None,
            },
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "time_window": "m",
                "start_time": "2026-12-25T09:00:00Z",
                "seasonality": ["Christmas", "business_hours"],
                "processed_at": "2026-12-25T09:30:00Z",
            },
        ]

        for sample in samples:
            with self.subTest(window=sample["time_window"]):
                dto = LogSummaryDTO.model_validate_json(json.dumps(sample))
                self.assertEqual(str(dto.id), sample["id"])
                self.assertEqual(dto.time_window.value, sample["time_window"])
                self.assertEqual(dto.seasonality, sample["seasonality"])


class LogSummaryDTOBehaviorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = LogSummaryDTO(
            id=uuid4(),
            org_id=uuid4(),
            time_window="s",
            start_time=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
            seasonality=["business_hours"],
        )
        self.summary.counts_by_level.update({"ERROR": 4, "INFO": 6})
        self.summary.counts_by_source_id.update({"api": 4, "worker": 6})
        self.summary.source_id_by_log_level.update({"ERROR": {"api"}, "INFO": {"worker"}})

    def test_log_summary_follows_db_model_contract(self) -> None:
        assert_db_model_contract(
            self,
            LogSummaryDTO,
            self.summary,
            "log_summarys",
        )

    def test_log_count_and_metric_value(self) -> None:
        self.assertEqual(self.summary.log_count, 10)
        self.assertEqual(self.summary.metric_value("total_log_count"), 10)
        self.assertEqual(self.summary.metric_value("log_count"), 10)
        self.assertEqual(self.summary.metric_value("log_count", {"level": "ERROR"}), 4)
        self.assertEqual(self.summary.metric_value("log_count", {"sourceId": "api"}), 4)
        self.assertEqual(self.summary.metric_value("log_count", {"level": "ERROR", "sourceId": "api"}), 4)
        self.assertEqual(self.summary.metric_value("log_count", {"level": "INFO", "sourceId": "api"}), 0)
        self.assertEqual(self.summary.metric_value("source_presence"), 2)
        self.assertEqual(self.summary.metric_value("source_presence", {"sourceId": "worker"}), 6)

        with self.assertRaises(ValueError):
            self.summary.metric_value("unsupported")

    def test_metric_series(self) -> None:
        self.assertEqual(self.summary.metric_series("source_rate"), {"api": 0.4, "worker": 0.6})
        self.assertEqual(self.summary.metric_series("source_rate", {"level": "ERROR"}), {"api": 1.0})

        empty = LogSummaryDTO(
            id=uuid4(),
            org_id=uuid4(),
            time_window="s",
            start_time=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(empty.metric_series("source_rate"), {})

        with self.assertRaises(ValueError):
            self.summary.metric_series("unsupported")

    def test_distribution(self) -> None:
        self.assertEqual(self.summary.distribution("level_distribution"), {"ERROR": 0.4, "INFO": 0.6})
        self.assertEqual(self.summary.distribution("source_distribution"), {"api": 0.4, "worker": 0.6})

        with self.assertRaises(ValueError):
            self.summary.distribution("unsupported")

    def test_source_matches_level(self) -> None:
        self.assertTrue(self.summary._source_matches_level("api", "error"))
        self.assertFalse(self.summary._source_matches_level("api", "info"))


if __name__ == "__main__":
    unittest.main()
