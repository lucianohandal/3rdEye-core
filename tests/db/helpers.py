import os
import unittest
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg

from db.PostgresDB import PostgresDB


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
DB_TEST_SKIP_REASON = "TEST_DATABASE_URL is not set"
SCHEMA_PATH = Path(__file__).parents[2] / "db" / "SQL" / "schema.sql"


def database_test_case(test_class):
    return unittest.skipUnless(TEST_DATABASE_URL, DB_TEST_SKIP_REASON)(test_class)


async def prepare_database() -> asyncpg.Pool:
    if TEST_DATABASE_URL is None:
        raise unittest.SkipTest(DB_TEST_SKIP_REASON)

    PostgresDB.DATABASE_URL = TEST_DATABASE_URL
    await close_pool()
    pool = await PostgresDB.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text())
        await truncate_database(conn)
    return pool


async def close_pool() -> None:
    if PostgresDB._pool is None:
        return None

    await PostgresDB._pool.close()
    PostgresDB._pool = None
    return None


async def truncate_database(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        TRUNCATE TABLE
            raw_logs,
            log_summary_signatures,
            log_summaries,
            metric_baselines,
            alerts,
            log_signatures,
            api_keys,
            users,
            organizations,
            plans,
            holidays
        RESTART IDENTITY CASCADE
        """
    )


async def insert_organization(
    conn: asyncpg.Connection,
    org_id: UUID | None = None,
) -> UUID:
    org_id = org_id or uuid4()
    await conn.execute(
        """
        INSERT INTO organizations (id, status)
        VALUES ($1, 'active')
        """,
        org_id,
    )
    return org_id
