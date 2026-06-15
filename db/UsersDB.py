from uuid import UUID

from db.PostgresDB import PostgresDB


class UsersDB(PostgresDB):
    async def get_org_id(self, api_key: str) -> UUID | None:
        rows = await self.get(
            """
            SELECT org_id
            FROM api_keys
            WHERE api_key = $1::uuid
              AND expires_at > NOW()
            LIMIT 1
            """,
            str(api_key),
        )
        if not rows:
            return None

        return rows[0]["org_id"]
