from math import sqrt
from typing import Any

import asyncpg

from db.PostgresDB import PostgresDB
from util.dto.analysis.BaselineSnapshot import BaselineSnapshot
from util.dto.analysis.ExpectedPattern import ExpectedPattern
from util.dto.database.AlertDTO import AlertDTO
from util.dto.analysis.LogSummaryDTO import LogSummaryDTO
from util.dto.analysis.MetricBaseline import MetricBaseline
from util.enum.LogLevel import LogLevel
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

        return _summaries_from_rows(rows or [])

    async def get_baseline(
        self,
        window: LogWindow,
        org_id: str | None = None,
        seasonality: list[str] | None = None,
    ) -> BaselineSnapshot:
        if org_id is None:
            return BaselineSnapshot()

        query = """
            SELECT
                metric_key,
                sample_count,
                mean,
                m2
            FROM metric_baselines
            WHERE org_id = $1::uuid
              AND time_window = $2
              AND seasonality_key = $3
            ORDER BY metric_key
        """
        rows = await self.get(
            query,
            org_id,
            _window_value(window),
            _seasonality_key(seasonality),
        )
        return _baseline_from_rows(rows or [])

    async def update_baselines(
        self,
        summaries: list[LogSummaryDTO],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        if not summaries:
            return None

        if conn is None:
            pool = await PostgresDB.get_pool()
            async with pool.acquire() as pooled_conn:
                async with pooled_conn.transaction():
                    await self.update_baselines(summaries, conn=pooled_conn)
            return None

        known_keys_by_bucket: dict[tuple[str, str, str], set[str]] = {}
        upsert_args: list[tuple[Any, str, str, str, float]] = []

        for summary in summaries:
            org_id = str(summary.org_id)
            window = _window_value(summary.time_window)
            seasonality_key = _seasonality_key(summary.seasonality)
            bucket = (org_id, window, seasonality_key)

            if bucket not in known_keys_by_bucket:
                known_keys_by_bucket[bucket] = await self._get_metric_keys(
                    org_id,
                    window,
                    seasonality_key,
                    conn=conn,
                )

            known_keys = known_keys_by_bucket[bucket]
            observed = _metric_values_for_summary(summary)
            sample_keys = known_keys | set(observed)

            upsert_args.extend(
                (
                    summary.org_id,
                    window,
                    seasonality_key,
                    metric_key,
                    observed.get(metric_key, 0.0),
                )
                for metric_key in sorted(sample_keys)
            )
            known_keys.update(sample_keys)

        if not upsert_args:
            return None

        await self.executemany(
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
            VALUES ($1, $2, $3, $4, 1, $5, 0)
            ON CONFLICT (org_id, time_window, seasonality_key, metric_key)
            DO UPDATE
            SET sample_count = metric_baselines.sample_count + 1,
                mean = metric_baselines.mean + (
                    (EXCLUDED.mean - metric_baselines.mean)
                    / (metric_baselines.sample_count + 1)
                ),
                m2 = metric_baselines.m2 + (
                    (EXCLUDED.mean - metric_baselines.mean)
                    * (
                        EXCLUDED.mean - (
                            metric_baselines.mean + (
                                (EXCLUDED.mean - metric_baselines.mean)
                                / (metric_baselines.sample_count + 1)
                            )
                        )
                    )
                ),
                updated_at = NOW()
            """,
            upsert_args,
            conn=conn,
        )
        return None

    async def complete_analysis(
        self,
        summaries: list[LogSummaryDTO],
        alerts: list[AlertDTO],
    ) -> None:
        if not summaries and not alerts:
            return None

        pool = await PostgresDB.get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self.insertmany(alerts, conn=conn)
                await self.update_baselines(summaries, conn=conn)
                await self.mark_processed(summaries, conn=conn)
        return None

    async def mark_processed(
        self,
        summaries: list[LogSummaryDTO],
        conn: asyncpg.Connection | None = None,
    ) -> None:
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
            conn=conn,
        )
        return None

    async def submit_alerts(self, alerts: list[AlertDTO]) -> None:
        await self.insertmany(alerts)
        return None

    async def _get_metric_keys(
        self,
        org_id: str,
        window: str,
        seasonality_key: str,
        conn: asyncpg.Connection,
    ) -> set[str]:
        rows = await self.get(
            """
            SELECT metric_key
            FROM metric_baselines
            WHERE org_id = $1::uuid
              AND time_window = $2
              AND seasonality_key = $3
            """,
            org_id,
            window,
            seasonality_key,
            conn=conn,
        )
        return {row["metric_key"] for row in rows or []}


def _summaries_from_rows(rows: list[Any]) -> list[LogSummaryDTO]:
    summaries: dict[str, LogSummaryDTO] = {}

    for row in rows:
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

        if row["log_signature_id"] is None:
            continue

        level = _log_level_key(row["log_level"])
        source_id = str(row["log_signature_id"])
        count = row["signature_log_count"]

        summary.counts_by_level[level] = summary.counts_by_level.get(level, 0) + count
        summary.counts_by_source_id[source_id] = summary.counts_by_source_id.get(source_id, 0) + count
        summary.source_id_by_log_level.setdefault(level, set()).add(source_id)

    return list(summaries.values())


def _baseline_from_rows(rows: list[Any]) -> BaselineSnapshot:
    baseline = BaselineSnapshot()

    for row in rows:
        metric_key = row["metric_key"]
        sample_count = row["sample_count"]
        if sample_count <= 0:
            continue

        mean = float(row["mean"])
        stddev = sqrt(float(row["m2"]) / sample_count)

        distribution_key = _metric_filter_value(metric_key, "level_distribution", "key")
        if distribution_key is not None:
            baseline.distributions.setdefault("level_distribution", {})[distribution_key] = mean
            continue

        distribution_key = _metric_filter_value(metric_key, "source_distribution", "sourceId")
        if distribution_key is not None:
            baseline.distributions.setdefault("source_distribution", {})[distribution_key] = mean
            continue

        source_id = _metric_filter_value(metric_key, "source_presence", "sourceId")
        if source_id is not None:
            baseline.expected_patterns[source_id] = ExpectedPattern(
                key=source_id,
                historical_occurrences=round(mean * sample_count),
            )
            continue

        baseline.metric_stats[metric_key] = MetricBaseline(
            mean=mean,
            stddev=stddev,
            sample_count=sample_count,
        )

    return baseline


def _metric_values_for_summary(summary: LogSummaryDTO) -> dict[str, float]:
    values: dict[str, float] = {
        "log_count": float(summary.log_count),
        "total_log_count": float(summary.log_count),
    }

    for level, count in summary.counts_by_level.items():
        values[f"log_count[level={level}]"] = float(count)

    for source_id, count in summary.counts_by_source_id.items():
        values[f"log_count[sourceId={source_id}]"] = float(count)
        if count > 0:
            values[f"source_presence[sourceId={source_id}]"] = 1.0

    for level, source_ids in summary.source_id_by_log_level.items():
        denominator = summary.counts_by_level.get(level, 0)
        if denominator <= 0:
            continue
        for source_id in source_ids:
            count = summary.counts_by_source_id.get(source_id, 0)
            values[f"source_rate[level={level},sourceId={source_id}]"] = count / denominator

    for key, value in summary.distribution("level_distribution").items():
        values[f"level_distribution[key={key}]"] = value

    for source_id, value in summary.distribution("source_distribution").items():
        values[f"source_distribution[sourceId={source_id}]"] = value

    return values


def _seasonality_key(seasonality: list[str] | None) -> str:
    if not seasonality:
        return "none"
    return "|".join(sorted(seasonality))


def _metric_filter_value(metric_key: str, metric: str, filter_name: str) -> str | None:
    prefix = f"{metric}[{filter_name}="
    if metric_key.startswith(prefix) and metric_key.endswith("]"):
        return metric_key[len(prefix):-1]
    return None


def _welford_next(
    sample_count: int,
    mean: float,
    m2: float,
    value: float,
) -> tuple[int, float, float]:
    next_count = sample_count + 1
    delta = value - mean
    next_mean = mean + (delta / next_count)
    next_m2 = m2 + (delta * (value - next_mean))
    return next_count, next_mean, next_m2


def _window_value(window: LogWindow | str) -> str:
    if isinstance(window, LogWindow):
        return window.value
    return str(window)


def _log_level_key(value: Any) -> str:
    if isinstance(value, str):
        return value.upper()
    return LogLevel(value).name
