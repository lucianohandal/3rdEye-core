import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from configs import get_config, load_config


class ConfigsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        get_config(reload=True)

    def test_default_config_loads_yaml_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config()

        self.assertEqual(config.environment, "default")
        self.assertEqual(config.app.title, "3rd Eye API")
        self.assertEqual(config.app.version, "0.1.0")
        self.assertEqual(config.database.url, "DB_URL")
        self.assertEqual(config.database.pool_min_size, 1)
        self.assertEqual(config.database.pool_max_size, 10)
        self.assertEqual(config.auth.api_key.prefix, "3eye_live_")
        self.assertEqual(config.auth.api_key.default_scope, "logs:write")
        self.assertEqual(config.auth.jwt.algorithm, "HS256")
        self.assertEqual(config.auth.jwt.issuer, "3rd-eye")
        self.assertEqual(config.auth.jwt.audience, "3rd-eye-api")

    def test_testing_config_overrides_default_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(environment="test")

        self.assertEqual(config.environment, "test")
        self.assertIsNone(config.database.url)
        self.assertEqual(config.auth.local_auth_secret, "3rdeye-test-secret")

    def test_environment_variables_override_yaml_values(self) -> None:
        env = {
            "APP_TITLE": "3rd Eye Test API",
            "TEST_DATABASE_URL": "postgresql://postgres:postgres@localhost/test",
            "AUTH_SECRET": "shared-test-secret",
            "API_KEY_HASH_SECRET": "api-key-hash-secret",
            "JWT_SECRET": "jwt-secret",
            "JWT_ISSUER": "issuer-from-env",
            "JWT_LEEWAY_SECONDS": "30",
            "DB_POOL_MAX_SIZE": "3",
        }

        with patch.dict(os.environ, env, clear=True):
            config = load_config(environment="test")

        self.assertEqual(config.app.title, "3rd Eye Test API")
        self.assertEqual(
            config.database.url,
            "postgresql://postgres:postgres@localhost/test",
        )
        self.assertEqual(config.database.pool_max_size, 3)
        self.assertEqual(config.auth.local_auth_secret, "shared-test-secret")
        self.assertEqual(config.auth.api_key.hash_secret, "api-key-hash-secret")
        self.assertEqual(config.auth.jwt.secret, "jwt-secret")
        self.assertEqual(config.auth.jwt.issuer, "issuer-from-env")
        self.assertEqual(config.auth.jwt.leeway_seconds, 30)

    def test_get_config_uses_environment_selector(self) -> None:
        with patch.dict(os.environ, {"THIRDEYE_ENV": "test"}, clear=True):
            config = get_config(reload=True)

        self.assertEqual(config.environment, "test")
        self.assertEqual(config.auth.local_auth_secret, "3rdeye-test-secret")

    def test_get_config_cache_tracks_environment_overrides(self) -> None:
        with patch.dict(os.environ, {"AUTH_SECRET": "first-secret"}, clear=True):
            first_config = get_config(reload=True)

        with patch.dict(os.environ, {"AUTH_SECRET": "second-secret"}, clear=True):
            second_config = get_config()

        self.assertEqual(first_config.auth.local_auth_secret, "first-secret")
        self.assertEqual(second_config.auth.local_auth_secret, "second-secret")

    def test_custom_config_path_must_be_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "configs.yaml"
            config_path.write_text("- not-a-mapping\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError):
                    load_config(config_path=config_path)


if __name__ == "__main__":
    unittest.main()
