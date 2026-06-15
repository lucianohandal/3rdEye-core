import asyncio
from datetime import datetime, timezone
from math import sqrt
import unittest
from uuid import uuid4

from analysis.service import AnalysisService
from db.AnalysisDB import (
    _baseline_from_rows,
    _metric_values_for_summary,
    _seasonality_key,
    _welford_next,
)
from util.dto.analysis.BaselineSnapshot import BaselineSnapshot
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.dto.analysis.MetricBaseline import MetricBaseline
from util.dto.database.AlertDTO import AlertDTO
from util.enum.LogWindow import LogWindow
from util.enum.Severity import Severity


def snapshot(**overrides) -> LogSummaryDTO:
    values = {
        "id": uuid4(),
        "org_id": uuid4(),
        "time_window": "s",
        "start_time": datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return LogSummaryDTO(**values)


class AnalysisBaselinesTestCase(unittest.TestCase):
    def test_seasonality_key_is_stable(self) -> None:
        self.assertEqual(_seasonality_key(None), "none")
        self.assertEqual(_seasonality_key([]), "none")
        self.assertEqual(_seasonality_key(["weekend", "Christmas"]), "Christmas|weekend")
        self.assertEqual(
            _seasonality_key(["business_hours", "Christmas", "business_hours"]),
            "Christmas|business_hours|business_hours",
        )

    def test_welford_next_tracks_population_variance(self) -> None:
        self.assertEqual(_welford_next(0, 0, 0, 10), (1, 10, 0))

        sample_count = 0
        mean = 0
        m2 = 0
        for value in [2, 4, 4]:
            sample_count, mean, m2 = _welford_next(sample_count, mean, m2, value)

        self.assertEqual(sample_count, 3)
        self.assertAlmostEqual(mean, 10 / 3)
        self.assertAlmostEqual(sqrt(m2 / sample_count), sqrt(8 / 9))

    def test_metric_values_for_summary(self) -> None:
        summary = snapshot()
        summary.counts_by_level.update({"ERROR": 4, "INFO": 6})
        summary.counts_by_source_id.update({"api": 4, "worker": 6})
        summary.source_id_by_log_level.update({"ERROR": {"api"}, "INFO": {"worker"}})

        values = _metric_values_for_summary(summary)

        self.assertEqual(values["total_log_count"], 10)
        self.assertEqual(values["log_count"], 10)
        self.assertEqual(values["log_count[level=ERROR]"], 4)
        self.assertEqual(values["log_count[sourceId=api]"], 4)
        self.assertEqual(values["source_rate[level=ERROR,sourceId=api]"], 1)
        self.assertEqual(values["level_distribution[key=ERROR]"], 0.4)
        self.assertEqual(values["source_distribution[sourceId=worker]"], 0.6)
        self.assertEqual(values["source_presence[sourceId=api]"], 1)

    def test_metric_values_for_summary_omits_zero_denominator_rates(self) -> None:
        summary = snapshot()
        summary.counts_by_level.update({"ERROR": 0})
        summary.counts_by_source_id.update({"api": 0})
        summary.source_id_by_log_level.update({"ERROR": {"api"}})

        values = _metric_values_for_summary(summary)

        self.assertEqual(values["total_log_count"], 0)
        self.assertNotIn("source_rate[level=ERROR,sourceId=api]", values)
        self.assertNotIn("source_presence[sourceId=api]", values)

    def test_baseline_from_rows_splits_metric_shapes(self) -> None:
        baseline = _baseline_from_rows(
            [
                {
                    "metric_key": "log_count[level=ERROR]",
                    "sample_count": 4,
                    "mean": 3.0,
                    "m2": 16.0,
                },
                {
                    "metric_key": "level_distribution[key=ERROR]",
                    "sample_count": 4,
                    "mean": 0.25,
                    "m2": 0.0,
                },
                {
                    "metric_key": "source_presence[sourceId=api]",
                    "sample_count": 4,
                    "mean": 0.5,
                    "m2": 1.0,
                },
            ]
        )

        self.assertEqual(baseline.metric_stats["log_count[level=ERROR]"].mean, 3)
        self.assertEqual(baseline.metric_stats["log_count[level=ERROR]"].stddev, 2)
        self.assertEqual(baseline.distributions["level_distribution"]["ERROR"], 0.25)
        self.assertEqual(baseline.expected_patterns["api"].historical_occurrences, 2)

    def test_baseline_from_rows_skips_empty_samples_and_source_distribution(self) -> None:
        baseline = _baseline_from_rows(
            [
                {
                    "metric_key": "log_count",
                    "sample_count": 0,
                    "mean": 99.0,
                    "m2": 0.0,
                },
                {
                    "metric_key": "source_distribution[sourceId=api]",
                    "sample_count": 5,
                    "mean": 0.7,
                    "m2": 0.0,
                },
            ]
        )

        self.assertNotIn("log_count", baseline.metric_stats)
        self.assertEqual(baseline.distributions["source_distribution"]["api"], 0.7)

    def test_analysis_service_uses_persisted_baseline_before_completion(self) -> None:
        events = []
        summary = snapshot(seasonality=["business_hours"])

        class FakeDB:
            async def get_log_summaries(self, window):
                events.append(("claim", window))
                return [summary]

            async def get_baseline(self, window, org_id, seasonality):
                events.append(("baseline", window, org_id, seasonality))
                return BaselineSnapshot(
                    metric_stats={
                        "total_log_count": MetricBaseline(mean=1, sample_count=1),
                    }
                )

            async def complete_analysis(self, summaries, alerts):
                events.append(("complete", summaries, alerts))

        class FakeEngine:
            def evaluate(self, summaries, baseline):
                events.append(("evaluate", baseline.metric_stats["total_log_count"].mean))
                return [
                    AlertDTO(
                        org_id=summaries[0].org_id,
                        rule_id="test",
                        severity=Severity.INFO,
                        message="test",
                    )
                ]

        service = AnalysisService.__new__(AnalysisService)
        service.db = FakeDB()
        service.engine = FakeEngine()

        alerts = asyncio.run(service.evaluate_window(LogWindow.s))

        self.assertEqual(len(alerts), 1)
        self.assertEqual(events[0], ("claim", LogWindow.s))
        self.assertEqual(events[1], ("baseline", LogWindow.s, str(summary.org_id), ["business_hours"]))
        self.assertEqual(events[2], ("evaluate", 1))
        self.assertEqual(events[3][0], "complete")


if __name__ == "__main__":
    unittest.main()
