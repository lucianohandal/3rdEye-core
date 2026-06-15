from db.PostgresDB import PostgresDB
from util.dto.database.AlertDTO import AlertDTO
from util.dto.database.LogSummaryDTO import LogSummaryDTO
from util.enum.LogLevel import LogLevel
from util.enum.LogWindow import LogWindow


class AnalysisDB(PostgresDB):
    async def get_log_summaries(self, window: LogWindow) -> list[LogSummaryDTO]:
        query = """
            WITH claimed AS (
                SELECT id
                FROM log_summaries
                WHERE org_id = $1::uuid
                  AND time_window = $2
                  AND processed_at IS NULL
                  AND (
                      claimed_at IS NULL
                      OR claimed_at < NOW() - INTERVAL '15 minutes'
                  )
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
                    ls.start_time,
                    ls.log_count
            )
            SELECT
                u.id,
                u.start_time,
                u.log_count,
                lss.log_signature_id,
                lss.log_level,
                lss.log_count AS signature_log_count
            FROM updated u
            LEFT JOIN log_summary_signatures lss
              ON lss.summary_id = u.id
            ORDER BY u.start_time, u.id
        """
        rows = await self.get(query, self.org_id, window.value)

        summaries: dict[str, LogSummaryDTO] = {}

        for row in rows or []:
            summary_id = str(row["id"])
            summary = summaries.get(summary_id)
            if summary is None:
                summary = LogSummaryDTO(
                    id=row["id"],
                    window=window,
                    start_time=row["start_time"],
                    log_count=row["log_count"],
                )
                summaries[summary_id] = summary

            if row["log_signature_id"] is None:
                continue

            level = LogLevel(row["log_level"]).name
            source_id = str(row["log_signature_id"])
            count = row["signature_log_count"]

            summary.counts_by_level[level] = summary.counts_by_level.get(level, 0) + count
            summary.counts_by_source_id[source_id] = summary.counts_by_source_id.get(source_id, 0) + count
            summary.source_id_by_log_level.setdefault(level, set()).add(source_id)

        return list(summaries.values())

    async def mark_processed(self, summaries: list[LogSummaryDTO]) -> None:
        summary_ids = [summary.id for summary in summaries if summary.id is not None]
        if not summary_ids:
            return None

        await self.execute(
            """
            UPDATE log_summaries
            SET processed_at = NOW(),
                claimed_at = NULL
            WHERE org_id = $1::uuid
              AND id = ANY($2::uuid[])
            """,
            self.org_id,
            summary_ids,
        )
        return None

    async def submit_alerts(self, alerts: list[AlertDTO]) -> None:
        await self.insertmany(alerts)
        return None
