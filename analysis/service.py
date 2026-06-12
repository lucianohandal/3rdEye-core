from datetime import datetime
from pathlib import Path
from typing import Iterable

from analysis.engine import AnalysisEngine
from analysis.models import BaselineSnapshot
from analysis.rules import AnalysisRule, load_rules
from db.PostgresDB import PostgresDB
from db.LogSummaryDB import LogSummaryDB
from util.dto.AlertDTO import AlertDTO
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
        self.rules = list(rules) if rules is not None else load_rules(DEFAULT_RULES_PATH)
        self.summary_db = summary_db or LogSummaryDB(org_id)
        self.finding_db = finding_db or PostgresDB(org_id)

    async def evaluate_window(
        self,
        window: LogWindow,
        end: datetime | None = None,
        baseline: BaselineSnapshot | None = None,
    ) -> list[AlertDTO]:
        summary = await self.summary_db.generate_summary(window)
        return AnalysisEngine(self.rules).evaluate(summary, baseline)

    async def evaluate_and_store_window(
        self,
        window: LogWindow,
        end: datetime | None = None,
        baseline: BaselineSnapshot | None = None,
    ) -> list[AlertDTO]:
        summary = await self.summary_db.generate_summary(window)
        findings = AnalysisEngine(self.rules).evaluate(summary, baseline)
        await self.finding_db.insert_many(findings, summary.start, summary.end)
        return findings
