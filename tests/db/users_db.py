import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from db.UsersDB import UsersDB
from tests.db.helpers import close_pool, database_test_case, insert_organization, prepare_database


class UsersDBApiKeyLookupTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_get_org_id_returns_first_matching_org_id(self) -> None:
        db = UsersDB()
        org_id = uuid4()
        api_key = str(uuid4())
        db.get = AsyncMock(return_value=[{"org_id": org_id}])

        self.assertEqual(await db.get_org_id(api_key), org_id)
        db.get.assert_awaited_once()

    async def test_get_org_id_returns_none_for_missing_key(self) -> None:
        db = UsersDB()
        db.get = AsyncMock(return_value=[])

        self.assertIsNone(await db.get_org_id(str(uuid4())))


@database_test_case
class UsersDBIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.pool = await prepare_database()
        self.db = UsersDB()
        async with self.pool.acquire() as conn:
            self.org_id = await insert_organization(conn)

    async def asyncTearDown(self) -> None:
        await close_pool()

    async def test_get_org_id_reads_unexpired_api_key_org_id(self) -> None:
        api_key = uuid4()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (api_key, org_id, expires_at)
                VALUES ($1, $2, NOW() + INTERVAL '1 day')
                """,
                api_key,
                self.org_id,
            )

        self.assertEqual(await self.db.get_org_id(str(api_key)), self.org_id)

    async def test_get_org_id_ignores_missing_and_expired_api_keys(self) -> None:
        expired_key = uuid4()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (api_key, org_id, expires_at)
                VALUES ($1, $2, NOW() - INTERVAL '1 second')
                """,
                expired_key,
                self.org_id,
            )

        self.assertIsNone(await self.db.get_org_id(str(uuid4())))
        self.assertIsNone(await self.db.get_org_id(str(expired_key)))
