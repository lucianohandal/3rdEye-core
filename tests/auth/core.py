import unittest
from uuid import uuid4

from auth.core import (
    AuthForbidden,
    AuthUnauthorized,
    JWTSettings,
    create_app_jwt,
    hash_api_key_secret,
    parse_api_key,
    parse_bearer_authorization,
    verify_api_key_secret,
    verify_app_jwt,
)


class APIKeyAuthTestCase(unittest.TestCase):
    def test_parse_bearer_authorization_extracts_token(self) -> None:
        self.assertEqual(
            parse_bearer_authorization("Bearer token-value"),
            "token-value",
        )

    def test_parse_bearer_authorization_rejects_missing_or_malformed_headers(self) -> None:
        for value in [None, "", "Basic token-value", "Bearer"]:
            with self.assertRaises(AuthUnauthorized):
                parse_bearer_authorization(value)

    def test_parse_api_key_reads_key_id_and_secret(self) -> None:
        key_id = uuid4()
        api_key = parse_api_key(f"3eye_live_{key_id}.secret-value")

        self.assertEqual(api_key.key_id, key_id)
        self.assertEqual(api_key.secret, "secret-value")

    def test_api_key_hash_verification_uses_hmac_digest(self) -> None:
        stored_hash = hash_api_key_secret("secret-value")

        self.assertTrue(verify_api_key_secret("secret-value", stored_hash))
        self.assertFalse(verify_api_key_secret("wrong-secret", stored_hash))


class JWTAuthTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = JWTSettings(
            secret="jwt-test-secret",
            issuer="3rd-eye",
            audience="3rd-eye-api",
        )
        self.now = 1_800_000_000
        self.user_id = uuid4()
        self.org_id = uuid4()

    def claims(self, **overrides):
        claims = {
            "sub": str(self.user_id),
            "org_id": str(self.org_id),
            "scopes": ["logs:read"],
            "iss": self.settings.issuer,
            "aud": self.settings.audience,
            "iat": self.now,
            "exp": self.now + 60,
        }
        claims.update(overrides)
        return claims

    def test_verify_app_jwt_accepts_valid_hs256_token(self) -> None:
        token = create_app_jwt(self.claims(), settings=self.settings)

        claims = verify_app_jwt(
            token,
            settings=self.settings,
            required_scope="logs:read",
            now=self.now,
        )

        self.assertEqual(claims.subject, str(self.user_id))
        self.assertEqual(claims.org_id, self.org_id)
        self.assertEqual(claims.scopes, frozenset({"logs:read"}))

    def test_verify_app_jwt_rejects_expired_token(self) -> None:
        token = create_app_jwt(
            self.claims(exp=self.now - 1),
            settings=self.settings,
        )

        with self.assertRaises(AuthUnauthorized):
            verify_app_jwt(token, settings=self.settings, now=self.now)

    def test_verify_app_jwt_rejects_bad_issuer_or_audience(self) -> None:
        for claim_name, value in [("iss", "other-issuer"), ("aud", "other-audience")]:
            token = create_app_jwt(
                self.claims(**{claim_name: value}),
                settings=self.settings,
            )

            with self.assertRaises(AuthUnauthorized):
                verify_app_jwt(token, settings=self.settings, now=self.now)

    def test_verify_app_jwt_rejects_missing_scope(self) -> None:
        token = create_app_jwt(
            self.claims(scopes=["logs:write"]),
            settings=self.settings,
        )

        with self.assertRaises(AuthForbidden):
            verify_app_jwt(
                token,
                settings=self.settings,
                required_scope="logs:read",
                now=self.now,
            )

    def test_verify_app_jwt_rejects_tampered_signature(self) -> None:
        token = create_app_jwt(self.claims(), settings=self.settings)
        header, payload, signature = token.split(".")
        replacement = "A" if signature[0] != "A" else "B"
        tampered = f"{header}.{payload}.{replacement}{signature[1:]}"

        with self.assertRaises(AuthUnauthorized):
            verify_app_jwt(tampered, settings=self.settings, now=self.now)


if __name__ == "__main__":
    unittest.main()

