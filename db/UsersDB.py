from uuid import UUID

from db.PostgresDB import PostgresDB
from auth.core import (
    AuthContext,
    AuthForbidden,
    DEFAULT_API_KEY_SCOPE,
    JWTClaims,
    ParsedAPIKey,
    verify_api_key_secret,
)


class UsersDB(PostgresDB):
    async def get_org_id(self, api_key: str) -> UUID | None:
        rows = await self.get(
            """
            SELECT api_keys.org_id
            FROM api_keys
            JOIN organizations
              ON organizations.id = api_keys.org_id
            WHERE api_keys.api_key = $1::uuid
              AND api_keys.revoked_at IS NULL
              AND (api_keys.expires_at IS NULL OR api_keys.expires_at > NOW())
              AND organizations.status = 'active'
              AND organizations.disabled_at IS NULL
            LIMIT 1
            """,
            str(api_key),
        )
        if not rows:
            return None

        return rows[0]["org_id"]

    async def authorize_api_key(
        self,
        credential: ParsedAPIKey,
        required_scope: str = DEFAULT_API_KEY_SCOPE,
    ) -> AuthContext | None:
        rows = await self.get(
            """
            SELECT
                api_keys.org_id,
                api_keys.key_hash,
                api_keys.scopes,
                api_keys.revoked_at IS NULL AS is_not_revoked,
                (api_keys.expires_at IS NULL OR api_keys.expires_at > NOW()) AS is_not_expired,
                (
                    organizations.status = 'active'
                    AND organizations.disabled_at IS NULL
                ) AS org_is_active
            FROM api_keys
            JOIN organizations
              ON organizations.id = api_keys.org_id
            WHERE api_keys.api_key = $1::uuid
            LIMIT 1
            """,
            credential.key_id,
        )
        if not rows:
            return None

        row = rows[0]
        if not row["is_not_revoked"] or not row["is_not_expired"]:
            return None

        if not verify_api_key_secret(credential.secret, row["key_hash"]):
            return None

        scopes = frozenset(row["scopes"] or [])
        if required_scope not in scopes:
            raise AuthForbidden("Missing required scope")

        if not row["org_is_active"]:
            raise AuthForbidden("Organization is not active")

        await self.execute(
            """
            UPDATE api_keys
            SET last_used_at = NOW()
            WHERE api_key = $1::uuid
            """,
            credential.key_id,
        )

        return AuthContext(
            org_id=row["org_id"],
            scopes=scopes,
            credential_type="api_key",
            credential_id=credential.key_id,
        )

    async def authorize_jwt_claims(
        self,
        claims: JWTClaims,
        required_scope: str | None = None,
    ) -> AuthContext | None:
        if required_scope and required_scope not in claims.scopes:
            raise AuthForbidden("Missing required scope")

        try:
            user_id = UUID(claims.subject)
        except ValueError:
            return None

        rows = await self.get(
            """
            SELECT
                users.id,
                users.org_id,
                users.disabled_at IS NULL AS user_is_active,
                (
                    organizations.status = 'active'
                    AND organizations.disabled_at IS NULL
                ) AS org_is_active
            FROM users
            JOIN organizations
              ON organizations.id = users.org_id
            WHERE users.id = $1::uuid
              AND users.org_id = $2::uuid
            LIMIT 1
            """,
            user_id,
            claims.org_id,
        )
        if not rows:
            return None

        row = rows[0]
        if not row["user_is_active"]:
            raise AuthForbidden("User is disabled")

        if not row["org_is_active"]:
            raise AuthForbidden("Organization is not active")

        return AuthContext(
            org_id=row["org_id"],
            scopes=claims.scopes,
            credential_type="jwt",
            subject=claims.subject,
        )
