from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from configs import get_config


_auth_config = get_config().auth

API_KEY_PREFIX = _auth_config.api_key.prefix
API_KEY_HASH_ALGORITHM = _auth_config.api_key.hash_algorithm
DEFAULT_API_KEY_SCOPE = _auth_config.api_key.default_scope
JWT_ALGORITHM = _auth_config.jwt.algorithm
JWT_ISSUER = _auth_config.jwt.issuer
JWT_AUDIENCE = _auth_config.jwt.audience
JWT_LEEWAY_SECONDS = _auth_config.jwt.leeway_seconds
LOCAL_AUTH_SECRET = _auth_config.local_auth_secret


class AuthError(Exception):
    status_code = 401

    def __init__(self, detail: str = "Unauthorized") -> None:
        self.detail = detail
        super().__init__(detail)


class AuthUnauthorized(AuthError):
    status_code = 401


class AuthForbidden(AuthError):
    status_code = 403


@dataclass(frozen=True)
class ParsedAPIKey:
    key_id: UUID
    secret: str


@dataclass(frozen=True)
class JWTSettings:
    secret: str
    issuer: str = JWT_ISSUER
    audience: str = JWT_AUDIENCE
    leeway_seconds: int = JWT_LEEWAY_SECONDS


@dataclass(frozen=True)
class JWTClaims:
    subject: str
    org_id: UUID
    scopes: frozenset[str]
    raw_claims: dict[str, Any]


@dataclass(frozen=True)
class AuthContext:
    org_id: UUID
    scopes: frozenset[str]
    credential_type: Literal["api_key", "jwt"]
    credential_id: UUID | None = None
    subject: str | None = None


def get_api_key_hash_secret() -> str:
    auth_config = get_config().auth
    return auth_config.api_key.hash_secret or auth_config.local_auth_secret


def get_jwt_settings() -> JWTSettings:
    auth_config = get_config().auth
    return JWTSettings(
        secret=auth_config.jwt.secret or auth_config.local_auth_secret,
        issuer=auth_config.jwt.issuer,
        audience=auth_config.jwt.audience,
        leeway_seconds=auth_config.jwt.leeway_seconds,
    )


def parse_bearer_authorization(authorization: str | None) -> str:
    if not authorization:
        raise AuthUnauthorized("Missing Authorization header")

    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthUnauthorized("Malformed Authorization header")

    return parts[1].strip()


def parse_api_key(token: str) -> ParsedAPIKey:
    if not token.startswith(API_KEY_PREFIX):
        raise AuthUnauthorized("Malformed API key")

    key_part, separator, secret = token.partition(".")
    if not separator or not secret:
        raise AuthUnauthorized("Malformed API key")

    try:
        key_id = UUID(key_part.removeprefix(API_KEY_PREFIX))
    except ValueError as exc:
        raise AuthUnauthorized("Malformed API key") from exc

    return ParsedAPIKey(key_id=key_id, secret=secret)


def api_key_display_prefix(key_id: UUID) -> str:
    return f"{API_KEY_PREFIX}{key_id}"


def hash_api_key_secret(
    secret: str,
    hash_secret: str | None = None,
) -> str:
    secret_key = hash_secret or get_api_key_hash_secret()
    digest = hmac.new(
        secret_key.encode("utf-8"),
        secret.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{API_KEY_HASH_ALGORITHM}:{digest}"


def verify_api_key_secret(secret: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False

    expected = hash_api_key_secret(secret)
    if not stored_hash.startswith(f"{API_KEY_HASH_ALGORITHM}:"):
        expected = expected.removeprefix(f"{API_KEY_HASH_ALGORITHM}:")

    return hmac.compare_digest(expected, stored_hash)


def create_app_jwt(
    claims: dict[str, Any],
    settings: JWTSettings | None = None,
) -> str:
    settings = settings or get_jwt_settings()
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    signing_input = ".".join(
        [
            _base64url_encode_json(header),
            _base64url_encode_json(claims),
        ]
    )
    signature = hmac.new(
        settings.secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def verify_app_jwt(
    token: str,
    settings: JWTSettings | None = None,
    required_scope: str | None = None,
    now: int | None = None,
) -> JWTClaims:
    settings = settings or get_jwt_settings()
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthUnauthorized("Malformed JWT")

    header = _decode_json_part(parts[0], "JWT header")
    payload = _decode_json_part(parts[1], "JWT payload")

    if header.get("alg") != JWT_ALGORITHM:
        raise AuthUnauthorized("Unsupported JWT algorithm")

    expected_signature = hmac.new(
        settings.secret.encode("utf-8"),
        f"{parts[0]}.{parts[1]}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    received_signature = _base64url_decode(parts[2], "JWT signature")
    if not hmac.compare_digest(expected_signature, received_signature):
        raise AuthUnauthorized("Invalid JWT signature")

    now = int(time.time()) if now is None else now
    _validate_registered_claims(payload, settings, now)

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthUnauthorized("JWT missing subject")

    org_id = payload.get("org_id")
    try:
        parsed_org_id = UUID(str(org_id))
    except (TypeError, ValueError) as exc:
        raise AuthUnauthorized("JWT missing organization") from exc

    scopes = _extract_scopes(payload)
    if required_scope and required_scope not in scopes:
        raise AuthForbidden("Missing required scope")

    return JWTClaims(
        subject=subject,
        org_id=parsed_org_id,
        scopes=scopes,
        raw_claims=payload,
    )


def _validate_registered_claims(
    payload: dict[str, Any],
    settings: JWTSettings,
    now: int,
) -> None:
    if payload.get("iss") != settings.issuer:
        raise AuthUnauthorized("Invalid JWT issuer")

    audience = payload.get("aud")
    if isinstance(audience, str):
        valid_audience = audience == settings.audience
    elif isinstance(audience, list):
        valid_audience = settings.audience in audience
    else:
        valid_audience = False
    if not valid_audience:
        raise AuthUnauthorized("Invalid JWT audience")

    exp = _numeric_claim(payload, "exp")
    if now >= exp + settings.leeway_seconds:
        raise AuthUnauthorized("Expired JWT")

    iat = _numeric_claim(payload, "iat")
    if iat > now + settings.leeway_seconds:
        raise AuthUnauthorized("JWT issued in the future")


def _numeric_claim(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthUnauthorized(f"JWT missing {name}")
    return int(value)


def _extract_scopes(payload: dict[str, Any]) -> frozenset[str]:
    scopes: set[str] = set()

    scope = payload.get("scope")
    if isinstance(scope, str):
        scopes.update(scope.split())

    claim_scopes = payload.get("scopes")
    if isinstance(claim_scopes, list):
        scopes.update(item for item in claim_scopes if isinstance(item, str))

    roles = payload.get("roles")
    if isinstance(roles, list):
        scopes.update(item for item in roles if isinstance(item, str))

    return frozenset(scopes)


def _decode_json_part(value: str, label: str) -> dict[str, Any]:
    try:
        decoded = _base64url_decode(value, label)
        data = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthUnauthorized(f"Malformed {label}") from exc

    if not isinstance(data, dict):
        raise AuthUnauthorized(f"Malformed {label}")
    return data


def _base64url_encode_json(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(encoded)


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(value: str, label: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise AuthUnauthorized(f"Malformed {label}") from exc
