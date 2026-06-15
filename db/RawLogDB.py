from uuid import UUID

from db.PostgresDB import PostgresDB
from util.dto.api.LogEventDTO import LogEventDTO
from util.dto.database.LogSignatureDTO import LogSignatureDTO
from util.dto.database.RawLogDTO import RawLogDTO


class RawLogDB(PostgresDB):
    def __init__(self, org_id: UUID) -> None:
        self.org_id = org_id

    async def insert_raw_logs(self, log_events: list[LogEventDTO]) -> None:
        if not log_events:
            return None

        signatures = await self.get_log_signatures(log_events)
        raw_logs = []
        new_signatures = {}
        # TODO: choose closest line if needed
        for log_event in log_events:
            key = log_event.signature_key()
            if key in signatures:
                raw_logs.append(RawLogDTO.from_log_event(log_event, self.org_id, signatures[key]))
                continue

            new_signatures[key] = new_signatures.get(key, LogSignatureDTO.from_log_event(log_event, self.org_id))

            if log_event.timestamp < new_signatures[key].first_appearance_timestamp:
                new_signatures[key].first_appearance_timestamp = log_event.timestamp
                new_signatures[key].first_appearance_commit = log_event.git_sha

            raw_logs.append(RawLogDTO.from_log_event(log_event, self.org_id, new_signatures[key].id))

        await self.insertmany(list(new_signatures.values()))
        await self.updatemany(raw_logs)
        return None

    async def get_log_signatures(self, log_events: list[LogEventDTO]) -> dict[tuple[str, str, str, int], UUID]:
        files = list({log_event.file for log_event in log_events})
        templates = list({log_event.template for log_event in log_events})

        query = f"""
            SELECT id, template, line, file, method
            FROM log_signatures
            WHERE org_id = $1::uuid
              AND template = ANY($2::text[])
              AND file = ANY($3::text[]);
        """

        rows = await self.get(query, self.org_id, templates, files)

        return {
            (row["template"], row["line"], row["file"], row["method"]): row["id"]
            for row in rows or []
        }
