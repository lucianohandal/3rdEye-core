from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any
from collections.abc import Mapping

import yaml


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "configs.yaml"
TEST_CONFIG_PATH = BASE_DIR / "configs.testing.yaml"
TEST_ENVIRONMENTS = {"test", "testing"}
MISSING = object()
ENV_OVERRIDE_NAMES = (
    "APP_TITLE",
    "APP_VERSION",
    "DB_URL",
    "DATABASE_URL",
    "DB_POOL_MIN_SIZE",
    "DATABASE_POOL_MIN_SIZE",
    "DB_POOL_MAX_SIZE",
    "DATABASE_POOL_MAX_SIZE",
    "AUTH_SECRET",
    "LOGS_READ_SCOPE",
    "LOGS_WRITE_SCOPE",
    "API_KEY_PREFIX",
    "API_KEY_HASH_ALGORITHM",
    "API_KEY_HASH_SECRET",
    "DEFAULT_API_KEY_SCOPE",
    "JWT_ALGORITHM",
    "JWT_SECRET",
    "JWT_ISSUER",
    "JWT_AUDIENCE",
    "JWT_LEEWAY_SECONDS",
)


@dataclass(frozen=True)
class AppConfig:
    title: str = "3rd Eye API"
    version: str = "0.1.0"


@dataclass(frozen=True)
class DatabaseConfig:
    url: str | None = "DB_URL"
    pool_min_size: int = 1
    pool_max_size: int = 10


@dataclass(frozen=True)
class AuthScopesConfig:
    logs_read: str = "logs:read"
    logs_write: str = "logs:write"


@dataclass(frozen=True)
class APIKeyConfig:
    prefix: str = "3eye_live_"
    hash_algorithm: str = "hmac-sha256"
    hash_secret: str | None = None
    default_scope: str = "logs:write"


@dataclass(frozen=True)
class JWTConfig:
    algorithm: str = "HS256"
    secret: str | None = None
    issuer: str = "3rd-eye"
    audience: str = "3rd-eye-api"
    leeway_seconds: int = 0


@dataclass(frozen=True)
class AuthConfig:
    local_auth_secret: str = "3rdeye-local-development-secret"
    scopes: AuthScopesConfig = field(default_factory=AuthScopesConfig)
    api_key: APIKeyConfig = field(default_factory=APIKeyConfig)
    jwt: JWTConfig = field(default_factory=JWTConfig)


@dataclass(frozen=True)
class Config:
    environment: str
    app: AppConfig = field(default_factory=AppConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)


def get_config(
    environment: str | None = None,
    config_path: str | Path | None = None,
    *,
    reload: bool = False,
) -> Config:
    if reload:
        _get_config_cached.cache_clear()

    normalized_environment = _normalize_environment(environment)
    normalized_path = _normalize_config_path(config_path)
    env_signature = _env_signature(normalized_environment)
    return _get_config_cached(normalized_environment, normalized_path, env_signature)


def load_config(
    environment: str | None = None,
    config_path: str | Path | None = None,
) -> Config:
    normalized_environment = _normalize_environment(environment)
    normalized_path = _normalize_config_path(config_path)

    if normalized_path is not None:
        config_data = _read_yaml(Path(normalized_path))
    else:
        config_data = _read_yaml(DEFAULT_CONFIG_PATH)
        if normalized_environment in TEST_ENVIRONMENTS:
            config_data = _deep_merge(config_data, _read_yaml(TEST_CONFIG_PATH))

    _apply_env_overrides(config_data, normalized_environment)
    return _build_config(config_data, normalized_environment)


@lru_cache(maxsize=8)
def _get_config_cached(
    environment: str,
    config_path: str | None,
    env_signature: tuple[tuple[str, str | None], ...],
) -> Config:
    return load_config(environment=environment, config_path=config_path)


def _normalize_environment(environment: str | None) -> str:
    value = (
        environment
        or os.environ.get("THIRDEYE_ENV")
        or os.environ.get("APP_ENV")
        or "default"
    )
    return value.strip().lower() or "default"


def _normalize_config_path(config_path: str | Path | None) -> str | None:
    value = (
        str(config_path)
        if config_path is not None
        else os.environ.get("THIRDEYE_CONFIG_PATH") or os.environ.get("CONFIG_PATH")
    )
    return str(Path(value).expanduser()) if value else None


def _env_signature(environment: str) -> tuple[tuple[str, str | None], ...]:
    env_names = list(ENV_OVERRIDE_NAMES)
    if environment in TEST_ENVIRONMENTS:
        env_names.append("TEST_DATABASE_URL")

    return tuple((name, os.environ.get(name)) for name in env_names)


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")

    return data


def _deep_merge(
    base: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> dict[str, Any]:
    merged = deepcopy(dict(base))

    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
            continue

        merged[key] = deepcopy(value)

    return merged


def _apply_env_overrides(config_data: dict[str, Any], environment: str) -> None:
    _set_from_env(config_data, ("app", "title"), "APP_TITLE")
    _set_from_env(config_data, ("app", "version"), "APP_VERSION")

    _set_from_env(config_data, ("database", "url"), "DB_URL", "DATABASE_URL")
    if environment in TEST_ENVIRONMENTS:
        _set_from_env(config_data, ("database", "url"), "TEST_DATABASE_URL")

    _set_from_env(
        config_data,
        ("database", "pool_min_size"),
        "DB_POOL_MIN_SIZE",
        "DATABASE_POOL_MIN_SIZE",
        parser=_parse_int,
    )
    _set_from_env(
        config_data,
        ("database", "pool_max_size"),
        "DB_POOL_MAX_SIZE",
        "DATABASE_POOL_MAX_SIZE",
        parser=_parse_int,
    )

    _set_from_env(config_data, ("auth", "local_auth_secret"), "AUTH_SECRET")
    _set_from_env(config_data, ("auth", "scopes", "logs_read"), "LOGS_READ_SCOPE")
    _set_from_env(config_data, ("auth", "scopes", "logs_write"), "LOGS_WRITE_SCOPE")
    _set_from_env(config_data, ("auth", "api_key", "prefix"), "API_KEY_PREFIX")
    _set_from_env(
        config_data,
        ("auth", "api_key", "hash_algorithm"),
        "API_KEY_HASH_ALGORITHM",
    )
    _set_from_env(
        config_data,
        ("auth", "api_key", "hash_secret"),
        "API_KEY_HASH_SECRET",
    )
    _set_from_env(
        config_data,
        ("auth", "api_key", "default_scope"),
        "DEFAULT_API_KEY_SCOPE",
    )
    _set_from_env(config_data, ("auth", "jwt", "algorithm"), "JWT_ALGORITHM")
    _set_from_env(config_data, ("auth", "jwt", "secret"), "JWT_SECRET")
    _set_from_env(config_data, ("auth", "jwt", "issuer"), "JWT_ISSUER")
    _set_from_env(config_data, ("auth", "jwt", "audience"), "JWT_AUDIENCE")
    _set_from_env(
        config_data,
        ("auth", "jwt", "leeway_seconds"),
        "JWT_LEEWAY_SECONDS",
        parser=_parse_int,
    )


def _set_from_env(
    config_data: dict[str, Any],
    path: tuple[str, ...],
    *env_names: str,
    parser=str,
) -> None:
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value is None or value == "":
            continue

        _set_nested(config_data, path, parser(value))
        return


def _set_nested(
    config_data: dict[str, Any],
    path: tuple[str, ...],
    value: Any,
) -> None:
    current = config_data
    for key in path[:-1]:
        next_value = current.setdefault(key, {})
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value

    current[path[-1]] = value


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Expected integer config value, got {value!r}") from exc


def _build_config(config_data: Mapping[str, Any], environment: str) -> Config:
    app_data = _mapping(config_data, "app")
    database_data = _mapping(config_data, "database")
    auth_data = _mapping(config_data, "auth")
    auth_scopes_data = _mapping(auth_data, "scopes")
    api_key_data = _mapping(auth_data, "api_key")
    jwt_data = _mapping(auth_data, "jwt")

    return Config(
        environment=environment,
        app=AppConfig(
            title=_string(app_data.get("title"), AppConfig.title),
            version=_string(app_data.get("version"), AppConfig.version),
        ),
        database=DatabaseConfig(
            url=_optional_string(database_data.get("url", MISSING), DatabaseConfig.url),
            pool_min_size=_integer(
                database_data.get("pool_min_size"),
                DatabaseConfig.pool_min_size,
            ),
            pool_max_size=_integer(
                database_data.get("pool_max_size"),
                DatabaseConfig.pool_max_size,
            ),
        ),
        auth=AuthConfig(
            local_auth_secret=_string(
                auth_data.get("local_auth_secret"),
                AuthConfig.local_auth_secret,
            ),
            scopes=AuthScopesConfig(
                logs_read=_string(
                    auth_scopes_data.get("logs_read"),
                    AuthScopesConfig.logs_read,
                ),
                logs_write=_string(
                    auth_scopes_data.get("logs_write"),
                    AuthScopesConfig.logs_write,
                ),
            ),
            api_key=APIKeyConfig(
                prefix=_string(api_key_data.get("prefix"), APIKeyConfig.prefix),
                hash_algorithm=_string(
                    api_key_data.get("hash_algorithm"),
                    APIKeyConfig.hash_algorithm,
                ),
                hash_secret=_optional_string(
                    api_key_data.get("hash_secret", MISSING),
                    APIKeyConfig.hash_secret,
                ),
                default_scope=_string(
                    api_key_data.get("default_scope"),
                    APIKeyConfig.default_scope,
                ),
            ),
            jwt=JWTConfig(
                algorithm=_string(jwt_data.get("algorithm"), JWTConfig.algorithm),
                secret=_optional_string(jwt_data.get("secret", MISSING), JWTConfig.secret),
                issuer=_string(jwt_data.get("issuer"), JWTConfig.issuer),
                audience=_string(jwt_data.get("audience"), JWTConfig.audience),
                leeway_seconds=_integer(
                    jwt_data.get("leeway_seconds"),
                    JWTConfig.leeway_seconds,
                ),
            ),
        ),
    )


def _mapping(config_data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config_data.get(key, {})
    if not isinstance(value, Mapping):
        raise ValueError(f"Config section {key!r} must be a mapping")

    return value


def _string(value: Any, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"Expected string config value, got {value!r}")
    return value


def _optional_string(value: Any, default: str | None) -> str | None:
    if value is MISSING:
        return default
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected string config value, got {value!r}")
    return value


def _integer(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected integer config value, got {value!r}")
    return value
