import asyncio
from datetime import datetime, timezone
from math import sqrt
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


def test_seasonality_key_is_stable() -> None:
    assert _seasonality_key(None) == "none"
    assert _seasonality_key([]) == "none"
    assert _seasonality_key(["weekend", "Christmas"]) == "Christmas|weekend"


def test_welford_next_tracks_population_variance() -> None:
    assert _welford_next(0, 0, 0, 10) == (1, 10, 0)

    sample_count = 0
    mean = 0
    m2 = 0
    for value in [2, 4, 4]:
        sample_count, mean, m2 = _welford_next(sample_count, mean, m2, value)

    assert sample_count == 3
    assert abs(mean - (10 / 3)) < 1e-9
    assert abs(sqrt(m2 / sample_count) - sqrt(8 / 9)) < 1e-9


def test_metric_values_for_summary() -> None:
    summary = snapshot()
    summary.counts_by_level.update({"ERROR": 4, "INFO": 6})
    summary.counts_by_source_id.update({"api": 4, "worker": 6})
    summary.source_id_by_log_level.update({"ERROR": {"api"}, "INFO": {"worker"}})

    values = _metric_values_for_summary(summary)

    assert values["total_log_count"] == 10
    assert values["log_count"] == 10
    assert values["log_count[level=ERROR]"] == 4
    assert values["log_count[sourceId=api]"] == 4
    assert values["source_rate[level=ERROR,sourceId=api]"] == 1
    assert values["level_distribution[key=ERROR]"] == 0.4
    assert values["source_distribution[sourceId=worker]"] == 0.6
    assert values["source_presence[sourceId=api]"] == 1


def test_baseline_from_rows_splits_metric_shapes() -> None:
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

    assert baseline.metric_stats["log_count[level=ERROR]"].mean == 3
    assert baseline.metric_stats["log_count[level=ERROR]"].stddev == 2
    assert baseline.distributions["level_distribution"]["ERROR"] == 0.25
    assert baseline.expected_patterns["api"].historical_occurrences == 2


def test_analysis_service_uses_persisted_baseline_before_completion() -> None:
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

    assert len(alerts) == 1
    assert events[0] == ("claim", LogWindow.s)
    assert events[1] == ("baseline", LogWindow.s, str(summary.org_id), ["business_hours"])
    assert events[2] == ("evaluate", 1)
    assert events[3][0] == "complete"
