from uuid import uuid4

import asyncpg

from util.dto.LogEventDTO import LogEventDTO
from db.postgres import get_pool
from util.functions import timestamp_for_storage


class LogSignatureDB:
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id

    async def get_signature_id(self, log: LogEventDTO, conn: asyncpg.Connection | None = None) -> str:
        if conn is None:
            pool = await get_pool()
            async with pool.acquire() as pooled_conn:
                return await self.get_signature_id(log, pooled_conn)

        rows = await conn.fetch(
            """
            SELECT id, line
            FROM LogSignature
            WHERE file IS NOT DISTINCT FROM $1
              AND method IS NOT DISTINCT FROM $2
              AND stack IS NOT DISTINCT FROM $3
              AND org_id IS NOT DISTINCT FROM $4
            """,
            log.file,
            log.method,
            log.stack,
            self.org_id,
        )

        if len(rows) == 1:
            return str(rows[0]["id"])

        for row in rows:
            if row["line"] == log.line:
                return str(row["id"])

        signature_id = str(uuid4())
        await conn.execute(
            """
            INSERT INTO LogSignature (
                org_id,
                id,
                template,
                line,
                file,
                stack,
                method,
                first_appearance_timestamp,
                first_appearance_commit,
                log_level
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            self.org_id,
            signature_id,
            log.template,
            log.line,
            log.file,
            log.stack,
            log.method,
            timestamp_for_storage(log.timestamp),
            log.git_sha,
            log.level.value,
        )

        return signature_id
