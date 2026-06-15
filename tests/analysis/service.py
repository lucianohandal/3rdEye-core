import asyncio
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
from uuid import uuid4

from analysis.rules import AnalysisRule
from analysis.service import DEFAULT_RULES_PATH, AnalysisService
from util.dto.analysis.BaselineSnapshot import BaselineSnapshot
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.dto.analysis.MetricBaseline import MetricBaseline
from util.dto.database.AlertDTO import AlertDTO
from util.enum.LogWindow import LogWindow
from util.enum.Severity import Severity


def make_rule(rule_id: str = "test_rule") -> AnalysisRule:
    return AnalysisRule.model_validate(
        {
            "id": rule_id,
            "window": "s",
            "metric": "log_count",
            "condition": {"type": "threshold", "operator": ">", "value": 0},
        }
    )


def make_summary(**overrides) -> LogSummaryDTO:
    counts_by_level = overrides.pop("counts_by_level", {})
    counts_by_source_id = overrides.pop("counts_by_source_id", {})
    source_id_by_log_level = overrides.pop("source_id_by_log_level", {})
    values = {
        "id": uuid4(),
        "org_id": uuid4(),
        "time_window": "s",
        "start_time": datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        "seasonality": None,
    }
    values.update(overrides)
    summary = LogSummaryDTO(**values)
    summary.counts_by_level.update(counts_by_level)
    summary.counts_by_source_id.update(counts_by_source_id)
    summary.source_id_by_log_level.update(source_id_by_log_level)
    return summary


class StubAnalysisDB:
    def __init__(
        self,
        summaries: list[LogSummaryDTO],
        events: list[tuple] | None = None,
    ) -> None:
        self.summaries = summaries
        self.events = events if events is not None else []
        self.calls: list[tuple] = []
        self.baseline_calls: list[tuple] = []
        self.completed_summaries: list[LogSummaryDTO] | None = None
        self.completed_alerts: list[AlertDTO] | None = None

    async def get_log_summaries(self, window: LogWindow) -> list[LogSummaryDTO]:
        event = ("claim", window)
        self.calls.append(event)
        self.events.append(event)
        return self.summaries

    async def get_baseline(
        self,
        window: LogWindow,
        org_id: str | None = None,
        seasonality: list[str] | None = None,
    ) -> BaselineSnapshot:
        event = ("baseline", window, org_id, seasonality)
        self.calls.append(event)
        self.events.append(event)
        self.baseline_calls.append(event[1:])
        return BaselineSnapshot(
            metric_stats={
                "total_log_count": MetricBaseline(
                    mean=float(len(self.baseline_calls)),
                    sample_count=10,
                )
            }
        )

    async def complete_analysis(
        self,
        summaries: list[LogSummaryDTO],
        alerts: list[AlertDTO],
    ) -> None:
        event = ("complete", summaries, alerts)
        self.calls.append(event)
        self.events.append(event)
        self.completed_summaries = summaries
        self.completed_alerts = alerts


class RecordingEngine:
    def __init__(self, events: list[tuple] | None = None) -> None:
        self.events = events if events is not None else []
        self.calls: list[tuple[list[LogSummaryDTO], BaselineSnapshot]] = []

    def evaluate(
        self,
        summaries: list[LogSummaryDTO],
        baseline: BaselineSnapshot,
    ) -> list[AlertDTO]:
        self.calls.append((summaries, baseline))
        self.events.append(("evaluate", summaries, baseline))
        if not summaries:
            return []
        return [
            AlertDTO(
                org_id=summaries[0].org_id,
                rule_id=f"rule-{len(self.calls)}",
                severity=Severity.INFO,
                message="matched",
                observed_value=baseline.metric_stats.get(
                    "total_log_count",
                    MetricBaseline(mean=0),
                ).mean,
            )
        ]


def make_service(db: StubAnalysisDB, engine: RecordingEngine) -> AnalysisService:
    service = AnalysisService.__new__(AnalysisService)
    service.org_id = "org-under-test"
    service.db = db
    service.engine = engine
    return service


class AnalysisServiceInitializationTestCase(unittest.TestCase):
    def test_init_with_explicit_rules_uses_given_rules_and_db(self) -> None:
        rules = [make_rule("explicit_rule")]
        db = object()

        with patch("analysis.service.load_rules") as load_rules:
            with patch("analysis.service.get_analysis_db", return_value=db) as get_analysis_db:
                service = AnalysisService("org-1", rules)

        load_rules.assert_not_called()
        get_analysis_db.assert_called_once_with()
        self.assertEqual(service.org_id, "org-1")
        self.assertIs(service.db, db)
        self.assertEqual(service.engine.rules, rules)

    def test_init_without_rules_loads_default_rules(self) -> None:
        rules = [make_rule("default_rule")]
        db = object()

        with patch("analysis.service.load_rules", return_value=rules) as load_rules:
            with patch("analysis.service.get_analysis_db", return_value=db):
                service = AnalysisService("org-1")

        load_rules.assert_called_once_with(DEFAULT_RULES_PATH)
        self.assertIs(service.db, db)
        self.assertEqual(service.engine.rules, rules)


class AnalysisServiceEvaluateWindowTestCase(unittest.TestCase):
    def test_evaluate_window_loads_baseline_before_each_summary_evaluation(self) -> None:
        summary_one = make_summary(seasonality=["business_hours"], counts_by_level={"INFO": 5})
        summary_two = make_summary(seasonality=["Christmas"], counts_by_level={"ERROR": 2})
        events: list[tuple] = []
        db = StubAnalysisDB([summary_one, summary_two], events)
        engine = RecordingEngine(events)
        service = make_service(db, engine)

        alerts = asyncio.run(service.evaluate_window(LogWindow.s))

        self.assertEqual(len(alerts), 2)
        self.assertEqual(db.calls[0], ("claim", LogWindow.s))
        self.assertEqual(
            db.baseline_calls,
            [
                (summary_one.time_window, str(summary_one.org_id), ["business_hours"]),
                (summary_two.time_window, str(summary_two.org_id), ["Christmas"]),
            ],
        )
        self.assertEqual(len(engine.calls), 2)
        self.assertIs(engine.calls[0][0][0], summary_one)
        self.assertEqual(engine.calls[0][1].metric_stats["total_log_count"].mean, 1)
        self.assertIs(engine.calls[1][0][0], summary_two)
        self.assertEqual(engine.calls[1][1].metric_stats["total_log_count"].mean, 2)
        self.assertEqual(db.calls[-1][0], "complete")
        self.assertIs(db.completed_summaries, db.summaries)
        self.assertEqual(db.completed_alerts, alerts)
        self.assertEqual(
            [event[0] for event in events],
            ["claim", "baseline", "evaluate", "baseline", "evaluate", "complete"],
        )

    def test_evaluate_window_uses_supplied_baseline_without_db_lookup(self) -> None:
        summary = make_summary(seasonality=["weekend"], counts_by_level={"INFO": 3})
        db = StubAnalysisDB([summary])
        engine = RecordingEngine()
        service = make_service(db, engine)
        baseline = BaselineSnapshot(
            metric_stats={
                "total_log_count": MetricBaseline(mean=99, sample_count=5),
            }
        )

        alerts = asyncio.run(service.evaluate_window(LogWindow.s, baseline=baseline))

        self.assertEqual(len(alerts), 1)
        self.assertEqual(db.baseline_calls, [])
        self.assertEqual(db.calls[0], ("claim", LogWindow.s))
        self.assertEqual(db.calls[-1][0], "complete")
        self.assertIs(engine.calls[0][1], baseline)
        self.assertEqual(alerts[0].observed_value, 99)

    def test_evaluate_window_completes_even_when_no_summaries_are_claimed(self) -> None:
        db = StubAnalysisDB([])
        engine = RecordingEngine()
        service = make_service(db, engine)

        alerts = asyncio.run(service.evaluate_window(LogWindow.m))

        self.assertEqual(alerts, [])
        self.assertEqual(engine.calls, [])
        self.assertEqual(db.calls[0], ("claim", LogWindow.m))
        self.assertEqual(db.calls[-1], ("complete", [], []))
        self.assertEqual(db.completed_summaries, [])
        self.assertEqual(db.completed_alerts, [])

    def test_evaluate_window_aggregates_alerts_from_all_summaries(self) -> None:
        summaries = [
            make_summary(counts_by_level={"INFO": 1}),
            make_summary(counts_by_level={"INFO": 2}),
            make_summary(counts_by_level={"INFO": 3}),
        ]
        db = StubAnalysisDB(summaries)
        engine = RecordingEngine()
        service = make_service(db, engine)

        alerts = asyncio.run(service.evaluate_window(LogWindow.s))

        self.assertEqual([alert.rule_id for alert in alerts], ["rule-1", "rule-2", "rule-3"])
        self.assertEqual(len(engine.calls), 3)
        self.assertEqual(db.completed_alerts, alerts)


if __name__ == "__main__":
    unittest.main()
