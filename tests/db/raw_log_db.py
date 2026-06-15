from datetime import datetime, timezone
import unittest
from uuid import UUID

from db.RawLogDB import RawLogDB
from tests.db.helpers import close_pool, database_test_case, insert_organization, prepare_database
from util.dto.api.LogEventDTO import LogEventDTO
from util.enum.LogLevel import LogLevel


def log_event(
    *,
    message: str = "User user-123 logged in",
    timestamp: datetime = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
    git_sha: str = "abc1234",
    template: str = "User {user_id} logged in",
    file: str = "auth.py",
    line: int = 42,
    method: str = "login",
    level: LogLevel = LogLevel.INFO,
    attributes: dict | None = None,
) -> LogEventDTO:
    return LogEventDTO(
        message=message,
        timestamp=timestamp,
        service="auth",
        environment="production",
        version="2026.06.10",
        git_sha=git_sha,
        trace_id="trace-123",
        span_id="span-123",
        request_id="request-123",
        user_id="user-123",
        attributes=attributes or {"tenant": "acme"},
        level=level,
        template=template,
        file=file,
        line=line,
        method=method,
    )


@database_test_case
class RawLogDBIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.pool = await prepare_database()
        async with self.pool.acquire() as conn:
            self.org_id = await insert_organization(conn)
        self.db = RawLogDB(self.org_id)

    async def asyncTearDown(self) -> None:
        await close_pool()

    async def signature_rows(self) -> list:
        return await self.db.get(
            """
            SELECT *
            FROM log_signatures
            WHERE org_id = $1
            ORDER BY first_appearance_timestamp
            """,
            self.org_id,
        )

    async def raw_log_rows(self) -> list:
        return await self.db.get(
            """
            SELECT *
            FROM raw_logs
            WHERE org_id = $1
            ORDER BY timestamp
            """,
            self.org_id,
        )

    async def test_insert_raw_logs_creates_one_signature_for_repeated_signature_key(self) -> None:
        later = log_event(
            timestamp=datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc),
            git_sha="later-commit",
            attributes={"attempt": 2},
        )
        earlier = log_event(
            timestamp=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
            git_sha="earlier-commit",
            attributes={"attempt": 1},
        )

        await self.db.insert_raw_logs([later, earlier])

        signatures = await self.signature_rows()
        raw_logs = await self.raw_log_rows()

        self.assertEqual(len(signatures), 1)
        self.assertEqual(signatures[0]["template"], "User {user_id} logged in")
        self.assertEqual(signatures[0]["first_appearance_commit"], "earlier-commit")
        self.assertEqual(signatures[0]["log_level"], LogLevel.INFO)
        self.assertEqual(len(raw_logs), 2)
        self.assertEqual({row["signature_id"] for row in raw_logs}, {signatures[0]["id"]})
        self.assertEqual(raw_logs[0]["attributes"], {"attempt": 1})
        self.assertEqual(raw_logs[1]["attributes"], {"attempt": 2})

    async def test_insert_raw_logs_reuses_existing_signatures(self) -> None:
        first = log_event(message="User user-123 logged in")
        second = log_event(
            message="User user-456 logged in",
            timestamp=datetime(2026, 6, 10, 12, 10, tzinfo=timezone.utc),
            git_sha="second-commit",
        )

        await self.db.insert_raw_logs([first])
        original_signature_id = (await self.signature_rows())[0]["id"]

        await self.db.insert_raw_logs([second])
        signatures = await self.signature_rows()
        raw_logs = await self.raw_log_rows()

        self.assertEqual(len(signatures), 1)
        self.assertEqual(signatures[0]["id"], original_signature_id)
        self.assertEqual(len(raw_logs), 2)
        self.assertEqual({row["signature_id"] for row in raw_logs}, {original_signature_id})

    async def test_get_log_signatures_returns_mapping_by_signature_key(self) -> None:
        event = log_event()

        await self.db.insert_raw_logs([event])
        signatures = await self.db.get_log_signatures([event])

        self.assertEqual(set(signatures), {event.signature_key()})
        self.assertIsInstance(signatures[event.signature_key()], UUID)

    async def test_insert_raw_logs_empty_payload_is_noop(self) -> None:
        await self.db.insert_raw_logs([])

        self.assertEqual(await self.signature_rows(), [])
        self.assertEqual(await self.raw_log_rows(), [])


if __name__ == "__main__":
    unittest.main()
