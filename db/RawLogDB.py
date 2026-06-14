from uuid import UUID

from db.PostgresDB import PostgresDB
from util.dto.LogSignatureDTO import LogSignatureDTO
from util.dto.RawLogDTO import RawLogDTO


class RawLogDB(PostgresDB):
    async def insert_raw_logs(self, raw_logs: list[RawLogDTO]) -> None:
        if not raw_logs:
            return None

        signatures = await self.get_log_signatures(raw_logs)
        new_signatures = {}
        # TODO: choose closest line if needed
        for i in range(0, len(raw_logs)):
            key = raw_logs[i].signature_key()
            if key in signatures:
                raw_logs[i].signature_id = signatures[key]
                continue

            new_signatures[key] = new_signatures.get(key, LogSignatureDTO.from_raw_logs(raw_logs[i]))

            if raw_logs[i].timestamp < new_signatures[key].first_appearance_timestamp:
                new_signatures[key].first_appearance_timestamp = raw_logs[i].timestamp
                new_signatures[key].first_appearance_commit = raw_logs[i].git_sha

            raw_logs[i].signature_id = new_signatures[key].id

        await self.insertmany(list(new_signatures.values()))
        await self.updatemany(raw_logs)
        return None

    async def get_log_signatures(self, raw_logs: list[RawLogDTO]) -> dict[tuple[str, str, str, int], UUID]:
        files = list({raw_log.file for raw_log in raw_logs})
        templates = list({raw_log.template for raw_log in raw_logs})

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
