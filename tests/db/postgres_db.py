import re
from datetime import date
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from db.PostgresDB import PostgresDB
from tests.db.helpers import close_pool, database_test_case, insert_organization, prepare_database
from util.dto.database.AlertDTO import AlertDTO
from util.enum.Severity import Severity


class _AcquireContext:
    def __init__(self, conn) -> None:
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _Pool:
    def __init__(self, conn) -> None:
        self.conn = conn

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.conn)


class PostgresDBUpdateManyQueryTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_updatemany_uses_contiguous_placeholders_for_updated_values(self) -> None:
        conn = AsyncMock()
        alert = AlertDTO(
            org_id=uuid4(),
            rule_id="updatable_alert",
            severity=Severity.MEDIUM,
            message="Initial message",
            details={"state": "initial"},
        )

        with patch.object(PostgresDB, "get_pool", AsyncMock(return_value=_Pool(conn))):
            await PostgresDB().updatemany([alert])

        query, values = conn.executemany.await_args.args
        placeholder_numbers = sorted(
            {int(value) for value in re.findall(r"\$(\d+)", query)}
        )

        self.assertEqual(
            placeholder_numbers,
            list(range(1, max(placeholder_numbers) + 1)),
        )
        self.assertNotIn("org_id", query)
        self.assertEqual(values[0][0], alert.id)
        self.assertEqual(values[0][1], alert.rule_id)
        self.assertNotIn(alert.org_id, values[0])


@database_test_case
class PostgresDBIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.pool = await prepare_database()
        self.db = PostgresDB()
        async with self.pool.acquire() as conn:
            self.org_id = await insert_organization(conn)

    async def asyncTearDown(self) -> None:
        await close_pool()

    async def test_insertmany_and_get_record_class_round_trip_db_models(self) -> None:
        alert = AlertDTO(
            org_id=self.org_id,
            rule_id="error_logs_unusually_high",
            severity=Severity.HIGH,
            message="API error count is above baseline.",
            observed_value=42,
            expected_value=10,
            details={"metric_key": "log_count[level=ERROR]", "z_score": 3.2},
        )

        await self.db.insertmany([alert])
        rows = await self.db.get(
            "SELECT * FROM alerts WHERE id = $1",
            alert.id,
            record_class=AlertDTO,
        )

        self.assertEqual(len(rows), 1)
        stored = rows[0]
        self.assertEqual(stored.id, alert.id)
        self.assertEqual(stored.org_id, alert.org_id)
        self.assertEqual(stored.severity, Severity.HIGH)
        self.assertEqual(stored.details, alert.details)

    async def test_insertmany_uses_supplied_transaction_connection(self) -> None:
        alert = AlertDTO(
            org_id=self.org_id,
            rule_id="transactional_alert",
            severity=Severity.INFO,
            message="This alert should be rolled back.",
        )

        async with self.pool.acquire() as conn:
            transaction = conn.transaction()
            await transaction.start()
            try:
                await self.db.insertmany([alert], conn=conn)
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM alerts WHERE id = $1",
                    alert.id,
                )
                self.assertEqual(count, 1)
            finally:
                await transaction.rollback()

        rows = await self.db.get("SELECT * FROM alerts WHERE id = $1", alert.id)
        self.assertEqual(rows, [])

    async def test_execute_executemany_and_get_rows(self) -> None:
        await self.db.executemany(
            """
            INSERT INTO holidays (holiday_date, name)
            VALUES ($1, $2)
            """,
            [
                (date(2026, 1, 1), "New Year's Day"),
                (date(2026, 12, 25), "Christmas"),
            ],
        )

        await self.db.execute(
            "UPDATE holidays SET name = $1 WHERE holiday_date = $2",
            "Christmas Day",
            date(2026, 12, 25),
        )
        rows = await self.db.get(
            "SELECT holiday_date, name FROM holidays ORDER BY holiday_date"
        )

        self.assertEqual([row["name"] for row in rows], ["New Year's Day", "Christmas Day"])

    async def test_updatemany_updates_changed_fields(self) -> None:
        alert = AlertDTO(
            org_id=self.org_id,
            rule_id="updatable_alert",
            severity=Severity.MEDIUM,
            message="Initial message",
            details={"state": "initial"},
        )
        await self.db.insertmany([alert])

        alert.message = "Updated message"
        alert.severity = Severity.CRITICAL
        alert.details = {"state": "updated"}

        await self.db.updatemany([alert])
        rows = await self.db.get(
            "SELECT message, severity, details FROM alerts WHERE id = $1",
            alert.id,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message"], "Updated message")
        self.assertEqual(rows[0]["severity"], Severity.CRITICAL)
        self.assertEqual(rows[0]["details"], {"state": "updated"})

    async def test_empty_inputs_are_noops(self) -> None:
        self.assertIsNone(await self.db.insertmany([]))
        self.assertIsNone(await self.db.updatemany([]))
        self.assertIsNone(await self.db.executemany("SELECT 1", []))
        self.assertIsNone(await self.db.execute(""))
        self.assertIsNone(await self.db.get(""))

    async def test_get_rejects_non_db_model_record_class(self) -> None:
        with self.assertRaises(TypeError):
            await self.db.get("SELECT $1::uuid AS id", uuid4(), record_class=dict)


if __name__ == "__main__":
    unittest.main()
