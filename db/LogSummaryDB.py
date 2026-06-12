from datetime import datetime

from db.postgres import get_pool
from util.dto.LogSummaryDTO import LogSummaryDTO
from util.enum.LogWindow import LogWindow
from util.functions import timestamp_for_storage


class LogSummaryDB:
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id

    async def get_summary(self, window: LogWindow, end: datetime) -> LogSummaryDTO:
        window_end = timestamp_for_storage(end)
        window_start = window_end - window.duration
        pool = await get_pool()

        async with pool.acquire() as conn:
            total_logs = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM RawLogs
                WHERE org_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                """,
                self.org_id,
                window_start,
                window_end,
            )
            level_rows = await conn.fetch(
                """
                SELECT level, COUNT(*) AS count
                FROM RawLogs
                WHERE org_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                GROUP BY level
                """,
                self.org_id,
                window_start,
                window_end,
            )
            source_rows = await conn.fetch(
                """
                SELECT signature_id::text AS source_id, COUNT(*) AS count
                FROM RawLogs
                WHERE org_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                GROUP BY signature_id
                """,
                self.org_id,
                window_start,
                window_end,
            )
            source_level_rows = await conn.fetch(
                """
                SELECT DISTINCT ON (signature_id)
                    signature_id::text AS source_id,
                    level
                FROM RawLogs
                WHERE org_id = $1
                  AND timestamp >= $2
                  AND timestamp < $3
                ORDER BY signature_id, timestamp DESC
                """,
                self.org_id,
                window_start,
                window_end,
            )

        return LogSummaryDTO(
            window=window,
            start=window_start,
            end=window_end,
            total_logs=total_logs or 0,
            counts_by_level={row["level"]: row["count"] for row in level_rows},
            counts_by_source_id={row["source_id"]: row["count"] for row in source_rows},
            log_level_by_source_id={
                row["source_id"]: row["level"] for row in source_level_rows
            },
        )
