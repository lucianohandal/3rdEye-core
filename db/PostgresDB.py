from typing import TypeVar
from util.dto.DBModel import DBModel
import asyncpg



TDBModel = TypeVar("TDBModel", bound=DBModel)

class PostgresDB:
    DATABASE_URL = "DB_URL"
    _pool: asyncpg.Pool | None = None

    def __init__(self, org_id: str) -> None:
        self.org_id = org_id

    @staticmethod
    async def get_pool() -> asyncpg.Pool:
        pool = PostgresDB._pool

        if pool is None:
            pool = await asyncpg.create_pool(
                dsn=PostgresDB.DATABASE_URL,
                min_size=1,
                max_size=10,
            )
            PostgresDB._pool = pool

        return pool

    async def insert_many(self, table: str, entries: list[DBModel]) -> None:
        if not entries or not table:
            return

        pool = await PostgresDB.get_pool()

        async with pool.acquire() as conn:
            field_list = entries[0].field_list()
            placeholders = entries[0].placeholders()
            values = [value for entry in entries for value in entry.values()]

            await conn.executemany(
                f"""
                INSERT INTO {table} ({field_list})
                VALUES ({placeholders})
                """,
                values,
            )

    async def get(self,
                  query: str,
                  *args,
                  conn: asyncpg.Connection | None = None,
                  timeout: float | None = None,
                  record_class: type[TDBModel] | None = None,
                  ) -> list[TDBModel] | None:
        if not query:
            return None

        if record_class is not None and not issubclass(record_class, DBModel):
            raise TypeError("record_class must inherit from DBModel")

        if conn is None:
            pool = await PostgresDB.get_pool()
            async with pool.acquire() as pooled_conn:
                return await self.get(pooled_conn, query, *args, timeout=timeout, record_class=record_class)

        rows = await conn.fetch(
            query,
            *args,
            self.org_id
        )

        if record_class is None:
            return rows

        return [record_class.model_validate(dict(row)) for row in rows]