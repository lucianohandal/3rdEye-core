from datetime import datetime
from pathlib import Path
from typing import Iterable

from analysis.engine import AnalysisEngine
from analysis.models import BaselineSnapshot
from analysis.rules import AnalysisRule, load_rules
from db.PostgresDB import PostgresDB
from db.LogSummaryDB import LogSummaryDB
from util.dto.AlertDTO import AlertDTO
from util.dto.LogSummaryDTO import LogSummaryDTO
from util.enum.LogWindow import LogWindow


DEFAULT_RULES_PATH = Path(__file__).with_name("default_rules.json")


class AnalysisService:
    def __init__(
        self,
        org_id: str,
        rules: Iterable[AnalysisRule] | None = None,
        summary_db: LogSummaryDB | None = None,
        finding_db: PostgresDB | None = None,
    ) -> None:
        self.org_id = org_id
        rules = list(rules) if rules is not None else load_rules(DEFAULT_RULES_PATH)
        self.engine = AnalysisEngine(rules)
        self.summary_db = summary_db or LogSummaryDB(org_id)
        self.finding_db = finding_db or PostgresDB(org_id)

    async def evaluate_window(
        self,
        window: LogWindow,
        baseline: BaselineSnapshot | None = None,
    ) -> None:
        summaries: list[LogSummaryDTO] = await self.summary_db.get_log_summaries(window)
        alerts: list[AlertDTO] = self.engine.evaluate(summaries, baseline)
        await self.finding_db.insertmany(alerts)
