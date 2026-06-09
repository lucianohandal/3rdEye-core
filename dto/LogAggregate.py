from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, NamedTuple

from dto.LogEventDTO import LogEventDTO
from dto.LogLevel import LogLevel

LogID = NamedTuple(
    "LogID",
    [
        ("template", str),
        ("count", str),
     ],

)

@dataclass(frozen=True, slots=True)
class Log:
    timestamp: datetime
    id: LogID
    level: LogLevel

@dataclass(frozen=True, slots=True)
class LogAggregate:
    time_from: datetime
    time_to: datetime
    count: int
    levels: Mapping[LogLevel, tuple[int, frozenset[LogID]]]
    templates: Mapping[LogID, tuple[int, LogLevel]]

    def __post_init__(self) -> None:
        if self.time_from > self.time_to:
            raise ValueError("time_from must be before or equal to time_to")

    @classmethod
    def from_logs(cls, logs: list[Log]) -> "LogAggregate":
        if not logs:
            raise ValueError("logs cannot be empty")

        time_from = logs[0].timestamp
        time_to = logs[0].timestamp
        levels: dict[LogLevel, tuple[int, set[LogID]]] = {}
        templates: dict[LogID, tuple[int, LogLevel]] = {}

        for log in logs:
            time_from = min(time_from, log.timestamp)
            time_to = max(time_to, log.timestamp)

            level_count, level_log_ids = levels.get(log.level, (0, set()))
            level_log_ids.add(log.id)
            levels[log.level] = (level_count + 1, level_log_ids)

            template_data = templates.get(log.id)
            if template_data is None:
                templates[log.id] = (1, log.level)
                continue

            template_count, template_level = template_data
            if template_level != log.level:
                raise ValueError(
                    f"log id {log.id!r} has multiple levels: "
                    f"{template_level!r} and {log.level!r}"
                )

            templates[log.id] = (template_count + 1, template_level)

        return cls(
            time_from=time_from,
            time_to=time_to,
            count=len(logs),
            levels=MappingProxyType(
                {
                    level: (count, frozenset(log_ids))
                    for level, (count, log_ids) in levels.items()
                }
            ),
            templates=MappingProxyType(templates),
        )

    def count_for_level(self, level: LogLevel) -> int:
        level_data = self.levels.get(level)
        if level_data is None:
            return 0
        return level_data[0]

    def ids_for_level(self, level: LogLevel) -> frozenset[LogID]:
        level_data = self.levels.get(level)
        if level_data is None:
            return frozenset()
        return level_data[1]

    def count_for_template(self, template: str) -> int:
        return sum(
            count
            for log_id, (count, _) in self.templates.items()
            if log_id.template == template
        )