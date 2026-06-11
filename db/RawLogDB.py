import json
from uuid import uuid4

from util.dto.LogEventDTO import LogEventDTO
from db.LogSignatureDB import LogSignatureDB
from db.postgres import get_pool
from util.functions import timestamp_for_storage


class RawLogDB:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.log_signature_db = LogSignatureDB(project_id)

    async def insert_many(self, logs: list[LogEventDTO]) -> None:
        if not logs:
            return

        pool = await get_pool()

        async with pool.acquire() as conn:
            values = []
            for log in logs:
                values.append(
                    (
                        str(uuid4()),
                        self.project_id,
                        await self.log_signature_db.get_signature_id(log, conn),
                        timestamp_for_storage(log.timestamp),
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
                        log.method,
                        log.stack,
                        json.dumps(log.args),
                    )
                )

            await conn.executemany(
                """
                INSERT INTO RawLogs (
                    id,
                    project_id,
                    signature_id,
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
                    method,
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
