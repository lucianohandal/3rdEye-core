import json
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg

from db.postgres import get_pool
from util.dto.AnalysisFindingDTO import AnalysisFindingDTO
from util.functions import timestamp_for_storage


class AnalysisFindingDB:
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id

    async def insert_many(
        self,
        findings: list[AnalysisFindingDTO],
        window_start: datetime,
        window_end: datetime,
        conn: asyncpg.Connection | None = None,
    ) -> list[str]:
        if not findings:
            return []

        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as pooled_conn:
                return await self.insert_many(
                    findings,
                    window_start,
                    window_end,
                    pooled_conn,
                )

        now = datetime.now(timezone.utc)
        values = []
        finding_ids = []
        for finding in findings:
            finding_id = str(uuid4())
            finding_ids.append(finding_id)
            values.append(
                (
                    finding_id,
                    self.org_id,
                    finding.rule_id,
                    finding.window.value,
                    finding.severity.value,
                    finding.message,
                    finding.observed_value,
                    finding.expected_value,
                    json.dumps(finding.details),
                    timestamp_for_storage(window_start),
                    timestamp_for_storage(window_end),
                    now,
                )
            )

        await conn.executemany(
            """
            INSERT INTO Alerts (
                id,
                org_id,
                rule_id,
                window,
                severity,
                message,
                observed_value,
                expected_value,
                details,
                window_start,
                window_end,
                created_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12
            )
            """,
            values,
        )

        return finding_ids
