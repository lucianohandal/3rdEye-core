from uuid import UUID
from datetime import datetime
from typing import Any

from pydantic import Field, PrivateAttr

from util.dto.database.DBModel import DBModel
from util.enum.LogWindow import LogWindow
from util.functions import normalize_counts


class LogSummaryDTO(DBModel):
    time_window: LogWindow
    start_time: datetime
    seasonality: list[str] | None = None
    processed_at: datetime | None = None

    counts_by_level: dict[str, int] = PrivateAttr(default_factory=dict)
    counts_by_source_id: dict[str, int] = PrivateAttr(default_factory=dict)
    source_id_by_log_level: dict[UUID, set[str]] = PrivateAttr(default_factory=dict)

    @property
    def log_count(self) -> int:
        return sum(self.counts_by_level.values())

    def metric_value(self, metric: str, filters: dict[str, Any] | None = None) -> float:
        filters = filters or {}
        if metric == "total_log_count":
            return float(self.log_count)

        if metric == "log_count":
            level = filters.get("level")
            source_id = filters.get("sourceId")
            if level is not None and source_id is not None:
                if self._source_matches_level(str(source_id), str(level)):
                    return float(self.counts_by_source_id.get(str(source_id), 0))
                return 0
            if source_id is not None:
                return float(self.counts_by_source_id.get(str(source_id), 0))
            if level is None:
                return float(self.log_count)
            return float(self.counts_by_level.get(str(level).upper(), 0))

        if metric == "source_presence":
            source_id = filters.get("sourceId")
            if source_id is None:
                return float(len([count for count in self.counts_by_source_id.values() if count > 0]))
            return float(self.counts_by_source_id.get(str(source_id), 0))

        raise ValueError(f"Unsupported metric: {metric}")

    def metric_series(self, metric: str, filters: dict[str, Any] | None = None) -> dict[str, float]:
        filters = filters or {}

        if metric == "source_rate":
            level = filters.get("level")
            if level is None:
                denominator = self.log_count
                source_counts = self.counts_by_source_id
            else:
                level_key = str(level).upper()
                denominator = self.counts_by_level.get(level_key, 0)
                source_counts = {
                    source_id: count
                    for source_id, count in self.counts_by_source_id.items()
                    if self._source_matches_level(source_id, level_key)
                }

            if denominator <= 0:
                return {}
            return {source_id: count / denominator for source_id, count in source_counts.items()}

        raise ValueError(f"Unsupported metric series: {metric}")

    def distribution(self, metric: str) -> dict[str, float]:
        if metric == "level_distribution":
            return normalize_counts(self.counts_by_level)
        if metric == "source_distribution":
            return normalize_counts(self.counts_by_source_id)
        raise ValueError(f"Unsupported distribution metric: {metric}")

    def _source_matches_level(self, source_id: str, level: str) -> bool:
        return source_id in self.source_id_by_log_level.get(level.upper(), set())
