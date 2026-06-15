import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from db.UsersDB import UsersDB
from tests.db.helpers import close_pool, database_test_case, insert_organization, prepare_database
from auth.core import (
    AuthForbidden,
    JWTClaims,
    ParsedAPIKey,
    api_key_display_prefix,
    hash_api_key_secret,
    parse_api_key,
)


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

    async def test_authorize_api_key_returns_context_for_valid_secret_and_scope(self) -> None:
        db = UsersDB()
        org_id = uuid4()
        key_id = uuid4()
        secret = "test-secret"
        credential = ParsedAPIKey(key_id=key_id, secret=secret)
        db.get = AsyncMock(
            return_value=[
                {
                    "org_id": org_id,
                    "key_hash": hash_api_key_secret(secret),
                    "scopes": ["logs:write"],
                    "is_not_revoked": True,
                    "is_not_expired": True,
                    "org_is_active": True,
                }
            ]
        )
        db.execute = AsyncMock()

        context = await db.authorize_api_key(credential, required_scope="logs:write")

        self.assertIsNotNone(context)
        self.assertEqual(context.org_id, org_id)
        self.assertEqual(context.scopes, frozenset({"logs:write"}))
        self.assertEqual(context.credential_type, "api_key")
        self.assertEqual(context.credential_id, key_id)
        db.execute.assert_awaited_once()

    async def test_authorize_api_key_rejects_wrong_secret(self) -> None:
        db = UsersDB()
        credential = ParsedAPIKey(key_id=uuid4(), secret="wrong-secret")
        db.get = AsyncMock(
            return_value=[
                {
                    "org_id": uuid4(),
                    "key_hash": hash_api_key_secret("right-secret"),
                    "scopes": ["logs:write"],
                    "is_not_revoked": True,
                    "is_not_expired": True,
                    "org_is_active": True,
                }
            ]
        )
        db.execute = AsyncMock()

        self.assertIsNone(await db.authorize_api_key(credential))
        db.execute.assert_not_awaited()

    async def test_authorize_api_key_rejects_revoked_and_expired_keys(self) -> None:
        db = UsersDB()
        credential = ParsedAPIKey(key_id=uuid4(), secret="test-secret")
        db.execute = AsyncMock()

        for is_not_revoked, is_not_expired in [(False, True), (True, False)]:
            db.get = AsyncMock(
                return_value=[
                    {
                        "org_id": uuid4(),
                        "key_hash": hash_api_key_secret("test-secret"),
                        "scopes": ["logs:write"],
                        "is_not_revoked": is_not_revoked,
                        "is_not_expired": is_not_expired,
                        "org_is_active": True,
                    }
                ]
            )

            self.assertIsNone(await db.authorize_api_key(credential))

        db.execute.assert_not_awaited()

    async def test_authorize_api_key_rejects_missing_scope(self) -> None:
        db = UsersDB()
        credential = ParsedAPIKey(key_id=uuid4(), secret="test-secret")
        db.get = AsyncMock(
            return_value=[
                {
                    "org_id": uuid4(),
                    "key_hash": hash_api_key_secret("test-secret"),
                    "scopes": ["logs:read"],
                    "is_not_revoked": True,
                    "is_not_expired": True,
                    "org_is_active": True,
                }
            ]
        )
        db.execute = AsyncMock()

        with self.assertRaises(AuthForbidden):
            await db.authorize_api_key(credential, required_scope="logs:write")

        db.execute.assert_not_awaited()

    async def test_authorize_api_key_rejects_inactive_org(self) -> None:
        db = UsersDB()
        credential = ParsedAPIKey(key_id=uuid4(), secret="test-secret")
        db.get = AsyncMock(
            return_value=[
                {
                    "org_id": uuid4(),
                    "key_hash": hash_api_key_secret("test-secret"),
                    "scopes": ["logs:write"],
                    "is_not_revoked": True,
                    "is_not_expired": True,
                    "org_is_active": False,
                }
            ]
        )
        db.execute = AsyncMock()

        with self.assertRaises(AuthForbidden):
            await db.authorize_api_key(credential, required_scope="logs:write")

        db.execute.assert_not_awaited()

    async def test_authorize_jwt_claims_returns_context_for_active_user_and_org(self) -> None:
        db = UsersDB()
        user_id = uuid4()
        org_id = uuid4()
        claims = JWTClaims(
            subject=str(user_id),
            org_id=org_id,
            scopes=frozenset({"logs:read"}),
            raw_claims={},
        )
        db.get = AsyncMock(
            return_value=[
                {
                    "id": user_id,
                    "org_id": org_id,
                    "user_is_active": True,
                    "org_is_active": True,
                }
            ]
        )

        context = await db.authorize_jwt_claims(claims, required_scope="logs:read")

        self.assertIsNotNone(context)
        self.assertEqual(context.org_id, org_id)
        self.assertEqual(context.subject, str(user_id))
        self.assertEqual(context.credential_type, "jwt")

    async def test_authorize_jwt_claims_rejects_missing_scope_before_db_lookup(self) -> None:
        db = UsersDB()
        db.get = AsyncMock()
        claims = JWTClaims(
            subject=str(uuid4()),
            org_id=uuid4(),
            scopes=frozenset({"logs:write"}),
            raw_claims={},
        )

        with self.assertRaises(AuthForbidden):
            await db.authorize_jwt_claims(claims, required_scope="logs:read")

        db.get.assert_not_awaited()

    async def test_authorize_jwt_claims_rejects_disabled_user_and_inactive_org(self) -> None:
        db = UsersDB()
        user_id = uuid4()
        org_id = uuid4()
        claims = JWTClaims(
            subject=str(user_id),
            org_id=org_id,
            scopes=frozenset({"logs:read"}),
            raw_claims={},
        )

        for user_is_active, org_is_active in [(False, True), (True, False)]:
            db.get = AsyncMock(
                return_value=[
                    {
                        "id": user_id,
                        "org_id": org_id,
                        "user_is_active": user_is_active,
                        "org_is_active": org_is_active,
                    }
                ]
            )

            with self.assertRaises(AuthForbidden):
                await db.authorize_jwt_claims(claims, required_scope="logs:read")


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
        secret = "integration-secret"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    api_key,
                    org_id,
                    key_hash,
                    display_prefix,
                    expires_at
                )
                VALUES ($1, $2, $3, $4, NOW() + INTERVAL '1 day')
                """,
                api_key,
                self.org_id,
                hash_api_key_secret(secret),
                api_key_display_prefix(api_key),
            )

        self.assertEqual(await self.db.get_org_id(str(api_key)), self.org_id)

    async def test_authorize_api_key_accepts_nullable_expiry_and_updates_last_used_at(self) -> None:
        api_key = uuid4()
        secret = "integration-secret"
        credential = parse_api_key(f"3eye_live_{api_key}.{secret}")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    api_key,
                    org_id,
                    key_hash,
                    display_prefix,
                    expires_at
                )
                VALUES ($1, $2, $3, $4, NULL)
                """,
                api_key,
                self.org_id,
                hash_api_key_secret(secret),
                api_key_display_prefix(api_key),
            )

        context = await self.db.authorize_api_key(credential, required_scope="logs:write")

        self.assertIsNotNone(context)
        self.assertEqual(context.org_id, self.org_id)
        async with self.pool.acquire() as conn:
            last_used_at = await conn.fetchval(
                "SELECT last_used_at FROM api_keys WHERE api_key = $1",
                api_key,
            )
        self.assertIsNotNone(last_used_at)

    async def test_authorize_api_key_ignores_missing_expired_and_revoked_keys(self) -> None:
        expired_key = uuid4()
        revoked_key = uuid4()
        secret = "integration-secret"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    api_key,
                    org_id,
                    key_hash,
                    display_prefix,
                    expires_at
                )
                VALUES ($1, $2, $3, $4, NOW() - INTERVAL '1 second')
                """,
                expired_key,
                self.org_id,
                hash_api_key_secret(secret),
                api_key_display_prefix(expired_key),
            )
            await conn.execute(
                """
                INSERT INTO api_keys (
                    api_key,
                    org_id,
                    key_hash,
                    display_prefix,
                    revoked_at
                )
                VALUES ($1, $2, $3, $4, NOW())
                """,
                revoked_key,
                self.org_id,
                hash_api_key_secret(secret),
                api_key_display_prefix(revoked_key),
            )

        missing = parse_api_key(f"3eye_live_{uuid4()}.{secret}")
        expired = parse_api_key(f"3eye_live_{expired_key}.{secret}")
        revoked = parse_api_key(f"3eye_live_{revoked_key}.{secret}")

        self.assertIsNone(await self.db.authorize_api_key(missing))
        self.assertIsNone(await self.db.authorize_api_key(expired))
        self.assertIsNone(await self.db.authorize_api_key(revoked))

    async def test_authorize_api_key_rejects_missing_scope_and_inactive_org(self) -> None:
        missing_scope_key = uuid4()
        inactive_org_key = uuid4()
        secret = "integration-secret"
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_keys (
                    api_key,
                    org_id,
                    key_hash,
                    display_prefix,
                    scopes
                )
                VALUES ($1, $2, $3, $4, ARRAY['logs:read'])
                """,
                missing_scope_key,
                self.org_id,
                hash_api_key_secret(secret),
                api_key_display_prefix(missing_scope_key),
            )
            await conn.execute(
                """
                UPDATE organizations
                SET status = 'disabled',
                    disabled_at = NOW()
                WHERE id = $1
                """,
                self.org_id,
            )
            await conn.execute(
                """
                INSERT INTO api_keys (
                    api_key,
                    org_id,
                    key_hash,
                    display_prefix,
                    scopes
                )
                VALUES ($1, $2, $3, $4, ARRAY['logs:write'])
                """,
                inactive_org_key,
                self.org_id,
                hash_api_key_secret(secret),
                api_key_display_prefix(inactive_org_key),
            )

        with self.assertRaises(AuthForbidden):
            await self.db.authorize_api_key(
                parse_api_key(f"3eye_live_{missing_scope_key}.{secret}"),
                required_scope="logs:write",
            )

        with self.assertRaises(AuthForbidden):
            await self.db.authorize_api_key(
                parse_api_key(f"3eye_live_{inactive_org_key}.{secret}"),
                required_scope="logs:write",
            )
