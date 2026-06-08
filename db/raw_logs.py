import json
from datetime import datetime, timezone
from uuid import uuid4

from dto.LogEventDTO import LogEventDTO
from db.postgres import get_pool


class RawLogDB:
    async def insert_many(
        self,
        project_id: str,
        api_key_id: str,
        logs: list[LogEventDTO],
    ) -> None:
        if not logs:
            return

        now = datetime.now(timezone.utc)

        values = [
            (
                str(uuid4()),
                project_id,
                api_key_id,
                now,
                log.level.value,
                log.message,
                log.service,
                log.environment,
                log.version,
                log.git_sha,
                json.dumps(log.attributes),
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
                    attributes
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    $9, $10, $11
                )
                """,
                values,
            )