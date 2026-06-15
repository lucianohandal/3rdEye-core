import os
import json
from collections.abc import Sequence
from typing import Any, TypeVar

import asyncpg

from util.dto.database.DBModel import DBModel


TDBModel = TypeVar("TDBModel", bound=DBModel)

class PostgresDB:
    DATABASE_URL = os.environ.get("DB_URL", "DB_URL")
    _pool: asyncpg.Pool | None = None

    @staticmethod
    async def get_pool() -> asyncpg.Pool:
        pool = PostgresDB._pool

        if pool is None:
            pool = await asyncpg.create_pool(
                dsn=PostgresDB.DATABASE_URL,
                min_size=1,
                max_size=10,
                init=_init_connection,
            )
            PostgresDB._pool = pool

        return pool

    async def insertmany(
        self,
        entries: list[DBModel],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        if not entries:
            return
        model_class = entries[0].__class__
        fields = model_class.fields()
        values = [tuple(entry.db_dump().get(field) for field in fields) for entry in entries]

        query = f"""
            INSERT INTO {model_class.table_name()} ({",".join(fields)})
            VALUES ({model_class.place_holders(include=set(fields))})
        """

        if conn is None:
            pool = await PostgresDB.get_pool()
            async with pool.acquire() as pooled_conn:
                await pooled_conn.executemany(query, values)
            return

        await conn.executemany(query, values)

    async def updatemany(self, entries: list[DBModel]) -> None:
        if not entries:
            return

        model_class = entries[0].__class__

        table = model_class.table_name()
        fields = model_class.fields()
        update_fields = model_class.update_fields()
        placeholders = {
            field: f"${i}"
            for i, field in enumerate(fields, start=1)
        }

        set_clause = ", ".join(
            f"{field} = {placeholders[field]}"
            for field in update_fields
        )
        distinct_fields = ", ".join(update_fields)
        distinct_values = ", ".join(placeholders[field] for field in update_fields)
        values = [entry.get_values() for entry in entries]

        pool = await PostgresDB.get_pool()

        async with pool.acquire() as conn:
            await conn.executemany(
                f"""
                UPDATE {table}
                SET {set_clause}
                WHERE id = {placeholders["id"]}
                  AND ({distinct_fields}) IS DISTINCT FROM ({distinct_values})
                """,
                values,
            )

    async def executemany(
        self,
        query: str,
        args: Sequence[Sequence[Any]],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        if not query or not args:
            return None

        if conn is None:
            pool = await PostgresDB.get_pool()
            async with pool.acquire() as pooled_conn:
                await pooled_conn.executemany(query, args)
            return None

        await conn.executemany(query, args)
        return None

    async def execute(
        self,
        query: str,
        *args,
        conn: asyncpg.Connection | None = None,
    ):
        if not query:
            return None

        if conn is None:
            pool = await PostgresDB.get_pool()
            async with pool.acquire() as pooled_conn:
                return await pooled_conn.execute(query, *args)

        result = await conn.execute(
            query,
            *args,
        )

        return result

    async def get(
        self,
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
                return await self.get(
                    query,
                    *args,
                    conn=pooled_conn,
                    timeout=timeout,
                    record_class=record_class,
                )

        rows = await conn.fetch(
            query,
            *args,
            timeout=timeout,
        )

        if record_class is None:
            return rows

        return [record_class.model_validate(dict(row)) for row in rows]


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
