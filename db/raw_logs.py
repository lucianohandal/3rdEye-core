import json
from datetime import datetime, timezone
from uuid import uuid4

from dto.LogEventDTO import LogEventDTO
from db.postgres import get_pool


def _timestamp_for_storage(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def _attributes_for_storage(log: LogEventDTO) -> dict:
    attributes = dict(log.attributes)
    attributes["args"] = log.args
    attributes["template"] = log.template
    return attributes


class RawLogDB:
    async def insert_many(
        self,
        project_id: str,
        api_key_id: str,
        logs: list[LogEventDTO],
    ) -> None:
        if not logs:
            return

        values = [
            (
                str(uuid4()),
                project_id,
                api_key_id,
                _timestamp_for_storage(log.timestamp),
                log.level.value,
                log.message,
                log.service,
                log.environment,
                log.version,
                log.git_sha,
                log.trace_id,
                log.span_id,
                log.request_id,
                log.user_id,
                log.file,
                log.line,
                log.function,
                log.stack,
                json.dumps(_attributes_for_storage(log)),
            )
            for log in logs
        ]


        pool = await get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO raw_logs (
                    id,
                    project_id,
                    api_key_id,
                    timestamp,
                    level,
                    message,
                    service,
                    environment,
                    version,
                    git_sha,
                    trace_id,
                    span_id,
                    request_id,
                    user_id,
                    file,
                    line,
                    function,
                    stack,
                    attributes
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9, $10, $11, $12, $13, $14, $15, $16,
                    $17, $18, $19
                )
                """,
                values,
            )
