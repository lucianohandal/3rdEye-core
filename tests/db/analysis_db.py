from datetime import datetime, timezone
import unittest
from uuid import UUID, uuid4
from db.AnalysisDB import AnalysisDB
from tests.db.helpers import close_pool, database_test_case, insert_organization, prepare_database
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.dto.database.AlertDTO import AlertDTO
from util.enum.LogLevel import LogLevel
from util.enum.LogWindow import LogWindow
from util.enum.Severity import Severity


def summary_dto(
    *,
    org_id: UUID,
    summary_id: UUID | None = None,
    seasonality: list[str] | None = None,
    counts_by_level: dict[str, int] | None = None,
    counts_by_source_id: dict[str, int] | None = None,
    source_id_by_log_level: dict[str, set[str]] | None = None,
) -> LogSummaryDTO:
    summary = LogSummaryDTO(
        id=summary_id or uuid4(),
        org_id=org_id,
        time_window="s",
        start_time=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        seasonality=seasonality,
    )
    summary.counts_by_level.update(counts_by_level or {})
    summary.counts_by_source_id.update(counts_by_source_id or {})
    summary.source_id_by_log_level.update(source_id_by_log_level or {})
    return summary



@database_test_case
class AnalysisDBIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.pool = await prepare_database()
        self.db = AnalysisDB()
        async with self.pool.acquire() as conn:
            self.org_id = await insert_organization(conn)

    async def asyncTearDown(self) -> None:
        await close_pool()

    async def insert_signature(
        self,
        *,
        signature_id: UUID | None = None,
        template: str = "Failed to process request",
        file: str = "api.py",
        method: str = "handle_request",
        line: int = 10,
        log_level: LogLevel = LogLevel.ERROR,
    ) -> UUID:
        signature_id = signature_id or uuid4()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO log_signatures (
                    id,
                    org_id,
                    template,
                    line,
                    file,
                    method,
                    first_appearance_timestamp,
                    first_appearance_commit,
                    log_level
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                signature_id,
                self.org_id,
                template,
                line,
                file,
                method,
                datetime(2026, 6, 10, 11, 0, tzinfo=timezone.utc),
                "seed-commit",
                log_level,
            )
        return signature_id

    async def insert_log_summary(
        self,
        *,
        summary_id: UUID | None = None,
        start_time: datetime = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        seasonality: list[str] | None = None,
        claimed: bool = False,
    ) -> UUID:
        summary_id = summary_id or uuid4()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO log_summaries (
                    id,
                    org_id,
                    time_window,
                    start_time,
                    seasonality,
                    claimed_at
                )
                VALUES ($1, $2, $3, $4, $5, CASE WHEN $6 THEN NOW() ELSE NULL END)
                """,
                summary_id,
                self.org_id,
                "s",
                start_time,
                seasonality,
                claimed,
            )
        return summary_id

    async def link_signature_to_summary(
        self,
        *,
        summary_id: UUID,
        signature_id: UUID,
        level: LogLevel,
        count: int,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO log_summary_signatures (
                    summary_id,
                    log_signature_id,
                    log_level,
                    log_count
                )
                VALUES ($1, $2, $3, $4)
                """,
                summary_id,
                signature_id,
                level,
                count,
            )

    async def test_get_log_summaries_claims_unprocessed_summaries_and_hydrates_counts(self) -> None:
        summary_id = await self.insert_log_summary(seasonality=["business_hours"])
        error_signature_id = await self.insert_signature(log_level=LogLevel.ERROR)
        info_signature_id = await self.insert_signature(
            template="Request finished",
            file="api.py",
            method="handle_request",
            line=11,
            log_level=LogLevel.INFO,
        )
        await self.link_signature_to_summary(
            summary_id=summary_id,
            signature_id=error_signature_id,
            level=LogLevel.ERROR,
            count=4,
        )
        await self.link_signature_to_summary(
            summary_id=summary_id,
            signature_id=info_signature_id,
            level=LogLevel.INFO,
            count=6,
        )

        summaries = await self.db.get_log_summaries(LogWindow.s)

        self.assertEqual(len(summaries), 1)
        summary = summaries[0]
        self.assertEqual(summary.id, summary_id)
        self.assertEqual(summary.seasonality, ["business_hours"])
        self.assertEqual(summary.counts_by_level, {"ERROR": 4, "INFO": 6})
        self.assertEqual(
            summary.counts_by_source_id,
            {str(error_signature_id): 4, str(info_signature_id): 6},
        )
        self.assertEqual(summary.source_id_by_log_level["ERROR"], {str(error_signature_id)})

        async with self.pool.acquire() as conn:
            claimed_at = await conn.fetchval(
                "SELECT claimed_at FROM log_summaries WHERE id = $1",
                summary_id,
            )
        self.assertIsNotNone(claimed_at)
        self.assertEqual(await self.db.get_log_summaries(LogWindow.s), [])

    async def test_get_baseline_reads_metric_baselines_for_exact_seasonality_bucket(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO metric_baselines (
                    org_id,
                    time_window,
                    seasonality_key,
                    metric_key,
                    sample_count,
                    mean,
                    m2
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        self.org_id,
                        "s",
                        "Christmas|business_hours",
                        "log_count[level=ERROR]",
                        4,
                        3.0,
                        16.0,
                    ),
                    (
                        self.org_id,
                        "s",
                        "Christmas|business_hours",
                        "level_distribution[key=ERROR]",
                        4,
                        0.25,
                        0.0,
                    ),
                    (
                        self.org_id,
                        "s",
                        "Christmas|business_hours",
                        "source_presence[sourceId=api]",
                        4,
                        0.5,
                        1.0,
                    ),
                ],
            )

        baseline = await self.db.get_baseline(
            LogWindow.s,
            org_id=str(self.org_id),
            seasonality=["business_hours", "Christmas"],
        )

        self.assertEqual(baseline.metric_stats["log_count[level=ERROR]"].mean, 3)
        self.assertEqual(baseline.metric_stats["log_count[level=ERROR]"].stddev, 2)
        self.assertEqual(baseline.distributions["level_distribution"]["ERROR"], 0.25)
        self.assertEqual(baseline.expected_patterns["api"].historical_occurrences, 2)

    async def test_update_baselines_upserts_running_stats_and_counts_known_absences(self) -> None:
        api_source_id = str(uuid4())
        worker_source_id = str(uuid4())
        first = summary_dto(
            org_id=self.org_id,
            seasonality=["business_hours"],
            counts_by_level={"ERROR": 4, "INFO": 6},
            counts_by_source_id={api_source_id: 4, worker_source_id: 6},
            source_id_by_log_level={"ERROR": {api_source_id}, "INFO": {worker_source_id}},
        )
        second = summary_dto(
            org_id=self.org_id,
            seasonality=["business_hours"],
            counts_by_level={"INFO": 10},
            counts_by_source_id={worker_source_id: 10},
            source_id_by_log_level={"INFO": {worker_source_id}},
        )

        await self.db.update_baselines([first, second])
        rows = await self.db.get(
            """
            SELECT metric_key, sample_count, mean, m2
            FROM metric_baselines
            WHERE org_id = $1
              AND time_window = 's'
              AND seasonality_key = 'business_hours'
            """,
            self.org_id,
        )
        by_key = {row["metric_key"]: row for row in rows}

        self.assertEqual(by_key["total_log_count"]["sample_count"], 2)
        self.assertEqual(by_key["total_log_count"]["mean"], 10)
        self.assertEqual(by_key["log_count[level=ERROR]"]["sample_count"], 2)
        self.assertEqual(by_key["log_count[level=ERROR]"]["mean"], 2)
        self.assertEqual(by_key[f"source_presence[sourceId={api_source_id}]"]["sample_count"], 2)
        self.assertEqual(by_key[f"source_presence[sourceId={api_source_id}]"]["mean"], 0.5)

    async def test_complete_analysis_inserts_alerts_updates_baselines_and_marks_processed(self) -> None:
        summary = summary_dto(
            org_id=self.org_id,
            counts_by_level={"ERROR": 3},
            counts_by_source_id={"api": 3},
            source_id_by_log_level={"ERROR": {"api"}},
        )
        await self.insert_log_summary(summary_id=summary.id, claimed=True)
        alert = AlertDTO(
            org_id=self.org_id,
            rule_id="error_logs_unusually_high",
            severity=Severity.HIGH,
            message="Error volume moved above baseline.",
            observed_value=3,
            expected_value=1,
            details={"metric_key": "log_count[level=ERROR]"},
        )

        await self.db.complete_analysis([summary], [alert])

        async with self.pool.acquire() as conn:
            alert_count = await conn.fetchval(
                "SELECT COUNT(*) FROM alerts WHERE id = $1",
                alert.id,
            )
            processed_row = await conn.fetchrow(
                """
                SELECT processed_at, claimed_at
                FROM log_summaries
                WHERE id = $1
                """,
                summary.id,
            )
            baseline_count = await conn.fetchval(
                """
                SELECT sample_count
                FROM metric_baselines
                WHERE org_id = $1
                  AND time_window = 's'
                  AND seasonality_key = 'none'
                  AND metric_key = 'log_count[level=ERROR]'
                """,
                self.org_id,
            )

        self.assertEqual(alert_count, 1)
        self.assertIsNotNone(processed_row["processed_at"])
        self.assertIsNone(processed_row["claimed_at"])
        self.assertEqual(baseline_count, 1)


if __name__ == "__main__":
    unittest.main()
