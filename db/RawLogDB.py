import asyncpg

from db.PostgresDB import PostgresDB
from util.dto.LogEventDTO import LogEventDTO

from util.dto.LogSignatureDTO import LogSignatureDTO
from util.dto.RawLogDTO import RawLogDTO


class RawLogDB(PostgresDB):
    async def insert_raw_logs(self, log_events: list[LogEventDTO]) -> None:
        if not log_events:
            return []
        templates = []
        files = []
        methods = []
        logs_by_key: dict[tuple[str | None, str | None, str | None, str | None], list[LogEventDTO]] = defaultdict(list)
        for log in log_events:
            key = (log.template, log.file, log.method, log.line)
            if key not in logs_by_key:
                files.append(log.file)
                methods.append(log.method)
                templates.append(log.template)

            logs_by_key.get(key, []).append(log)

        query = """
                SELECT DISTINCT s.id, s.file, s.method, s.org_id, s.line
                FROM log_signatures s
                JOIN unnest($1::text[], $2::text[], $3::text[]) AS k(file, method, template)
                  ON s.file IS NOT DISTINCT FROM k.file
                 AND s.method IS NOT DISTINCT FROM k.method
                 AND s.template IS NOT DISTINCT FROM k.template
                WHERE s.org_id = $3;
                """
        signatures = await self.get(
            query,
            files,
            methods,
            templates,
            self.org_id,
            record_class=LogSignatureDTO,
        )

        raw_logs: list[RawLogDTO] = []
        new_signatures: list[LogSignatureDTO] = []
        for signature in signatures:
            key = (signature.template, signature.file, signature.method, signature.line)
            for log_event in logs_by_key.pop(key):
                raw_logs.append(RawLogDTO.from_log_event(log_event, signature.id))

        # TODO: choose closest line if needed
        for log_event_list in logs_by_key.values():
            log_event: LogEventDTO = min(log_event_list, key=lambda x: log_event.timestamp)
            signature = LogSignatureDTO.from_log_event(log_event)
            raw_logs.append(RawLogDTO.from_log_event(log_event, signature.id))
            new_signatures.append(signature)

        await self.insert_many(LogSignatureDTO.table_name(), new_signatures)
        await self.insert_many(RawLogDTO.table_name(), raw_logs)
        return None
