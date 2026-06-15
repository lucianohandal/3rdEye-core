from pathlib import Path
from typing import Iterable

from analysis.engine import AnalysisEngine
from util.dto.analysis.BaselineSnapshot import BaselineSnapshot
from analysis.rules import AnalysisRule, load_rules
from db.PostgresManager import get_analysis_db
from util.dto.database.AlertDTO import AlertDTO
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.enum.LogWindow import LogWindow


DEFAULT_RULES_PATH = Path(__file__).with_name("default_rules.json")


class AnalysisService:
    def __init__(
        self,
        org_id: str,
        rules: Iterable[AnalysisRule] | None = None,
    ) -> None:
        self.org_id = org_id
        rules = list(rules) if rules is not None else load_rules(DEFAULT_RULES_PATH)
        self.engine = AnalysisEngine(rules)
        self.db = get_analysis_db()

    async def evaluate_window(
        self,
        window: LogWindow,
        baseline: BaselineSnapshot | None = None,
    ) -> list[AlertDTO]:
        summaries: list[LogSummaryDTO] = await self.db.get_log_summaries(window)
        alerts: list[AlertDTO] = []

        for summary in summaries:
            summary_baseline = baseline
            if summary_baseline is None:
                summary_baseline = await self.db.get_baseline(
                    summary.time_window,
                    org_id=str(summary.org_id),
                    seasonality=summary.seasonality,
                )
            alerts.extend(self.engine.evaluate([summary], summary_baseline))

        await self.db.complete_analysis(summaries, alerts)
        return alerts
