import json
import uuid
from collections import defaultdict

from IPython.utils import signatures, io

from db.PostgresDB import PostgresDB
from util.dto.LogSignatureDTO import LogSignatureDTO
from util.dto.RawLogDTO import RawLogDTO


class RawLogDB(PostgresDB):
    async def insert_raw_logs(self, log_events: list[RawLogDTO]) -> None:
        if not log_events:
            return None

        query = """
                WITH incoming AS (
                    SELECT *
                    FROM jsonb_to_recordset($2::jsonb) AS i(
                        message text, timestamp timestamptz, stack text, service text, environment text,
                        version text, git_sha text, trace_id text, span_id text, request_id text,
                        user_id text, attributes jsonb, file text, method text, template text, line smallint
                    )
                )
                INSERT INTO raw_logs (
                    org_id, signature_id, message, timestamp, stack,
                    service, environment, version, git_sha,
                    trace_id, span_id, request_id, user_id, attributes
                )
                SELECT
                    $1::uuid, s.id, i.message, i.timestamp, i.stack,
                    i.service, i.environment, i.version, i.git_sha,
                    i.trace_id, i.span_id, i.request_id, i.user_id,
                    COALESCE(i.attributes::jsonb, '{}'::jsonb)
                FROM incoming i
                LEFT JOIN log_signatures s
                  ON s.org_id = $1::uuid
                 AND s.file IS NOT DISTINCT FROM i.file
                 AND s.method IS NOT DISTINCT FROM i.method
                 AND s.template IS NOT DISTINCT FROM i.template
                 AND s.line IS NOT DISTINCT FROM i.line;
                """


        await self.execute(
            query,
            self.org_id,
            json.dumps([log.model_dump(mode="json") for log in log_events]),
        )

        await self.sign_logs()
        return None

    async def sign_logs(self) -> None:

        query = f"""
            SELECT {RawLogDTO.field_list()}
            FROM {RawLogDTO.table_name()}
            WHERE org_id = $1::uuid
              AND signature_id IS NULL;
            """

        raw_logs: list[RawLogDTO] | None = await self.get(query, record_class=RawLogDTO)
        if not raw_logs:
            return None

        signatures: dict[tuple[str | None, str | None, str | None, str | None], LogSignatureDTO] = defaultdict(list)

        # TODO: choose closest line if needed
        for i in range(0, len(raw_logs)):
            key = (raw_logs[i].template, raw_logs[i].file, raw_logs[i].method, raw_logs[i].line)
            log_signature: LogSignatureDTO = signatures.get(key, LogSignatureDTO.from_raw_logs(raw_logs[i]))

            if raw_logs[i].timestamp < log_signature.first_appearance_timestamp:
                log_signature.first_appearance_timestamp = raw_logs[i].timestamp
                log_signature.first_appearance_commit = raw_logs[i].git_sha

            raw_logs[i].signature_id = log_signature.id

        await self.insertmany(list(signatures.values()))
        await self.updatemany(raw_logs)
        return None
