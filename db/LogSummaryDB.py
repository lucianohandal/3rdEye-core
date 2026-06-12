from datetime import datetime, timezone
from uuid import UUID

from db.PostgresDB import PostgresDB
from util.dto.LogSummaryDTO import LogSummaryDTO
from util.enum.LogLevel import LogLevel
from util.enum.LogWindow import LogWindow


class LogSummaryDB(PostgresDB):
    _SOURCE_WINDOW_BY_WINDOW = {
        LogWindow.s: LogWindow.xs,
        LogWindow.m: LogWindow.s,
        LogWindow.l: LogWindow.m,
        LogWindow.xl: LogWindow.l,
        LogWindow.xxl: LogWindow.xl,
    }

    async def generate_summary(self, window: LogWindow) -> LogSummaryDTO:
        bucket_start = self._bucket_start(window)
        source_rows = await self._fetch_source_rows(window, bucket_start)

        log_count = sum(row["log_count"] for row in source_rows)
        summary_id = await self._insert_summary(window, bucket_start, log_count)
        await self._insert_summary_signatures(summary_id, source_rows)

        counts_by_level: dict[str, int] = {}
        counts_by_source_id: dict[str, int] = {}
        log_level_by_source_id: dict[str, str] = {}

        for row in source_rows:
            level = LogLevel(row["log_level"]).name
            source_id = str(row["signature_id"])
            count = row["log_count"]

            counts_by_level[level] = counts_by_level.get(level, 0) + count
            counts_by_source_id[source_id] = counts_by_source_id.get(source_id, 0) + count
            log_level_by_source_id[source_id] = level

        return LogSummaryDTO(
            window=window,
            start_time=bucket_start,
            log_count=log_count,
            counts_by_level=counts_by_level,
            counts_by_source_id=counts_by_source_id,
            log_level_by_source_id=log_level_by_source_id,
        )

    async def _fetch_source_rows(
        self,
        window: LogWindow,
        bucket_start: datetime,
    ):

        bucket_end = bucket_start + window.value
        if window == LogWindow.xs:
            return await self.get(
                """
                SELECT r.signature_id,
                       s.log_level,
                       COUNT(*) ::int AS log_count
                FROM raw_logs r
                         JOIN log_signatures s
                              ON s.id = r.signature_id
                                  AND s.org_id = r.org_id
                WHERE r.org_id = $1
                  AND r.timestamp >= $2
                  AND r.timestamp < $3
                GROUP BY r.signature_id, s.log_level
                """,
                self.org_id,
                bucket_start,
                bucket_end,
            )
        else:
            source_window = self._SOURCE_WINDOW_BY_WINDOW[window]
            return await self.get(
                """
                SELECT lss.log_signature_id AS signature_id,
                       lss.log_level,
                       SUM(lss.log_count) ::int AS log_count
                FROM log_summaries ls
                         JOIN log_summary_signatures lss
                              ON lss.summary_id = ls.id
                WHERE ls.org_id = $1
                  AND ls.time_window = $2
                  AND ls.start_time >= $3
                  AND ls.start_time < $4
                GROUP BY lss.log_signature_id, lss.log_level
                """,
                self.org_id,
                source_window.name,
                bucket_start,
                bucket_end,
            )

    async def _insert_summary(
        self,
        window: LogWindow,
        bucket_start: datetime,
        log_count: int,
    ) -> UUID:
        pool = await PostgresDB.get_pool()

        async with pool.acquire() as conn:
            summary_id = await conn.fetchval(
                """
                INSERT INTO log_summaries (org_id, time_window, start_time, log_count)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (org_id, time_window, start_time)
                DO NOTHING
                RETURNING id
                """,
                self.org_id,
                window.name,
                bucket_start,
                log_count,
            )

            if summary_id is not None:
                return summary_id

    async def _insert_summary_signatures(self, summary_id: UUID, source_rows) -> None:
        if not source_rows:
            return

        pool = await PostgresDB.get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO log_summary_signatures (
                    summary_id,
                    log_signature_id,
                    log_level,
                    log_count
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (summary_id, log_signature_id)
                DO NOTHING
                """,
                [
                    (
                        summary_id,
                        row["signature_id"],
                        row["log_level"],
                        row["log_count"],
                    )
                    for row in source_rows
                ],
            )

    def _bucket_start(
        self,
        window: LogWindow,
    ) -> datetime:
        rounded_end = self._floor_time(datetime.now(timezone.utc), window)
        return rounded_end - window.value

    def _floor_time(self, value: datetime, window: LogWindow) -> datetime:
        value = value.astimezone(timezone.utc)
        epoch_seconds = int(value.timestamp())
        window_seconds = int(window.value.total_seconds())
        floored_seconds = epoch_seconds - (epoch_seconds % window_seconds)
        return datetime.fromtimestamp(floored_seconds, tz=timezone.utc)
