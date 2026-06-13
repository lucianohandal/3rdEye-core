from db.PostgresDB import PostgresDB
from util.dto.LogSummaryDTO import LogSummaryDTO
from util.enum.LogLevel import LogLevel
from util.enum.LogWindow import LogWindow


class LogSummaryDB(PostgresDB):

    async def get_log_summaries(self, window: LogWindow) -> list[LogSummaryDTO]:
        query = """
            WITH claimed AS (
                SELECT id
                FROM log_summaries
                WHERE org_id = $1
                  AND time_window = $2
                  AND processed_at IS NULL
                ORDER BY start_time
                FOR UPDATE SKIP LOCKED
            ),
            updated AS (
                UPDATE log_summaries ls
                SET processed_at = NOW()
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
        rows = await self.get(query, self.org_id, window.name)

        summaries: dict[str, LogSummaryDTO] = {}

        for row in rows:
            summary_id = str(row["id"])
            summary = summaries.get(summary_id, LogSummaryDTO(window=window,
                                                              start_time=row["start_time"],
                                                              log_count=row["log_count"],
                                                              ))

            level = LogLevel(row["log_level"])
            source_id = str(row["log_signature_id"])
            count = row["signature_log_count"]

            summary.counts_by_level[level] = summary.counts_by_level.get(level, 0) + count
            summary.counts_by_source_id[source_id] = count
            summary.counts_by_level.get(level, set()).add(source_id)

        return list(summaries.values())
