from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, status

from auth.core import (
    AuthContext,
    AuthError,
    AuthUnauthorized,
    DEFAULT_API_KEY_SCOPE,
    parse_api_key,
    parse_bearer_authorization,
    verify_app_jwt,
)
from db.PostgresManager import get_users_db


WWW_AUTHENTICATE_BEARER = {"WWW-Authenticate": "Bearer"}


async def require_logs_write_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthContext:
    try:
        token = parse_bearer_authorization(authorization)
        api_key = parse_api_key(token)
        context = await get_users_db().authorize_api_key(
            api_key,
            required_scope=DEFAULT_API_KEY_SCOPE,
        )
    except AuthError as exc:
        raise _http_auth_error(exc) from exc

    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers=WWW_AUTHENTICATE_BEARER,
        )

    return context


async def require_jwt_scope(
    required_scope: str,
    authorization: str | None,
) -> AuthContext:
    try:
        token = parse_bearer_authorization(authorization)
        claims = verify_app_jwt(token, required_scope=required_scope)
        context = await get_users_db().authorize_jwt_claims(
            claims,
            required_scope=required_scope,
        )
    except AuthError as exc:
        raise _http_auth_error(exc) from exc

    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT",
            headers=WWW_AUTHENTICATE_BEARER,
        )

    return context


def require_jwt_scope_dependency(required_scope: str):
    async def dependency(
        authorization: Annotated[str | None, Header()] = None,
    ) -> AuthContext:
        return await require_jwt_scope(required_scope, authorization)

    return dependency


def _http_auth_error(exc: AuthError) -> HTTPException:
    headers = WWW_AUTHENTICATE_BEARER if isinstance(exc, AuthUnauthorized) else None
    return HTTPException(
        status_code=exc.status_code,
        detail=exc.detail,
        headers=headers,
    )

