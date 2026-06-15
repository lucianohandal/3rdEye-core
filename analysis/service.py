from pathlib import Path
from typing import Iterable

from analysis.engine import AnalysisEngine
from analysis.models import BaselineSnapshot
from analysis.rules import AnalysisRule, load_rules
from db.PostgresManager import get_analysis_db
from util.dto.database.AlertDTO import AlertDTO
from util.dto.database.LogSummaryDTO import LogSummaryDTO
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
        alerts: list[AlertDTO] = self.engine.evaluate(summaries, baseline)
        await self.db.insertmany(alerts)
        await self.db.mark_processed(summaries)
        return alerts
