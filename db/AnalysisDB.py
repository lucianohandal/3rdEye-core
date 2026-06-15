import datetime

from db.PostgresDB import PostgresDB
from util.dto.database.AlertDTO import AlertDTO
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.enum.LogWindow import LogWindow


class AnalysisDB(PostgresDB):
    async def get_log_summaries(self, window: LogWindow) -> list[LogSummaryDTO]:
        query = """
            WITH claimed AS (
                SELECT id
                FROM log_summaries
                WHERE time_window = $1
                  AND processed_at IS NULL
                  AND claimed_at IS NULL
                ORDER BY start_time
                FOR UPDATE SKIP LOCKED
            ),
            updated AS (
                UPDATE log_summaries ls
                SET claimed_at = NOW()
                FROM claimed
                WHERE ls.id = claimed.id
                RETURNING
                    ls.id,
                    ls.org_id,
                    ls.time_window,
                    ls.start_time,
                    ls.seasonality
            )
            SELECT
                u.id,
                u.org_id,
                u.time_window,
                u.start_time,
                u.seasonality,
                lss.log_signature_id,
                lss.log_level,
                lss.log_count AS signature_log_count
            FROM updated u
            LEFT JOIN log_summary_signatures lss
              ON lss.summary_id = u.id
            ORDER BY u.start_time, u.id
        """
        rows = await self.get(query, window.value)

        summaries: dict[str, LogSummaryDTO] = {}

        for row in rows or []:
            if row["log_signature_id"] is None:
                continue

            summary_id = str(row["id"])
            summary = summaries.get(summary_id)

            if summary is None:
                summary = LogSummaryDTO(
                    id=row["id"],
                    org_id=row["org_id"],
                    time_window=row["time_window"],
                    start_time=row["start_time"],
                    seasonality=row["seasonality"],
                )
                summaries[summary_id] = summary

            level = row["log_level"]
            source_id = str(row["log_signature_id"])
            count = row["signature_log_count"]

            summary.counts_by_level[level] = summary.counts_by_level.get(level, 0) + count
            summary.counts_by_source_id[source_id] = summary.counts_by_source_id.get(source_id, 0) + count
            summary.source_id_by_log_level.setdefault(level, set()).add(source_id)

        return list(summaries.values())

    async def mark_processed(self, summaries: list[LogSummaryDTO]) -> None:
        summary_ids = [summary.id for summary in summaries]
        if not summary_ids:
            return None

        await self.execute(
            """
            UPDATE log_summaries
            SET processed_at = NOW(),
                claimed_at   = NULL
            WHERE id = ANY ($1::uuid[])
            """,
            summary_ids,
        )
        return None

    async def submit_alerts(self, alerts: list[AlertDTO]) -> None:
        await self.insertmany(alerts)
        return None
