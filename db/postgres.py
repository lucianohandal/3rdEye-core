# import asyncpg
#
# from app.core.config import settings


# _pool: asyncpg.Pool | None = None


# async def get_pool() -> asyncpg.Pool:
    # global _pool
    #
    # if _pool is None:
    #     _pool = await asyncpg.create_pool(
    #         dsn=settings.database_url,
    #         min_size=1,
    #         max_size=10,
    #     )
    #
    # return _pool

class PrintConnection:
    async def executemany(self, command: str, values):
        print("executemany command:")
        print(command)
        print("executemany values:")
        print(values)

    async def execute(self, command: str, *args):
        print("execute command:")
        print(command)
        print("execute args:")
        print(args)

    async def fetch(self, command: str, *args):
        print("fetch command:")
        print(command)
        print("fetch args:")
        print(args)
        return []

    async def fetchrow(self, command: str, *args):
        print("fetchrow command:")
        print(command)
        print("fetchrow args:")
        print(args)
        return None

    async def fetchval(self, command: str, *args):
        print("fetchval command:")
        print(command)
        print("fetchval args:")
        print(args)
        return None


class PrintAcquireContext:
    async def __aenter__(self) -> PrintConnection:
        return PrintConnection()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class PrintPool:
    def acquire(self) -> PrintAcquireContext:
        return PrintAcquireContext()


async def get_pool() -> PrintPool:
    return PrintPool()