import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from main import app
from auth.core import AuthContext, AuthForbidden, create_app_jwt


HTTP_EXAMPLES = Path(__file__).with_name("logs.http")
TEST_API_KEY_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_API_KEY_SECRET = "test-secret"
TEST_AUTHORIZATION = f"Bearer 3eye_live_{TEST_API_KEY_ID}.{TEST_API_KEY_SECRET}"


class StubRawLogsDB:
    def __init__(self) -> None:
        self.inserted_batches = []

    async def insert_raw_logs(self, log_events):
        self.inserted_batches.append(log_events)


class FailingRawLogsDB:
    async def insert_raw_logs(self, log_events):
        raise RuntimeError("database unavailable")


class StubUsersDB:
    def __init__(
        self,
        org_id=None,
        forbidden_detail: str | None = None,
    ) -> None:
        self.org_id = org_id
        self.forbidden_detail = forbidden_detail
        self.api_keys = []
        self.jwt_claims = []
        self.required_scopes = []

    async def authorize_api_key(self, api_key, required_scope):
        self.api_keys.append(api_key)
        self.required_scopes.append(required_scope)

        if self.forbidden_detail:
            raise AuthForbidden(self.forbidden_detail)

        if self.org_id is None:
            return None

        return AuthContext(
            org_id=self.org_id,
            scopes=frozenset({required_scope}),
            credential_type="api_key",
            credential_id=api_key.key_id,
        )

    async def authorize_jwt_claims(self, claims, required_scope):
        self.jwt_claims.append(claims)
        self.required_scopes.append(required_scope)

        if self.forbidden_detail:
            raise AuthForbidden(self.forbidden_detail)

        if self.org_id is None:
            return None

        return AuthContext(
            org_id=claims.org_id,
            scopes=claims.scopes,
            credential_type="jwt",
            subject=claims.subject,
        )


def parse_http_examples(path: Path) -> list[dict[str, Any]]:
    requests = []
    for block in path.read_text().split("###"):
        lines = [line.rstrip() for line in block.splitlines()]
        request_index = next(
            (
                index
                for index, line in enumerate(lines)
                if line.startswith(("GET ", "POST ", "PUT ", "PATCH ", "DELETE "))
            ),
            None,
        )
        if request_index is None:
            continue

        method, url = lines[request_index].split(maxsplit=1)
        headers: dict[str, str] = {}
        body_lines: list[str] = []
        in_body = False

        for line in lines[request_index + 1:]:
            if line.startswith(">"):
                break
            if not in_body and not line:
                in_body = True
                continue
            if not in_body:
                name, value = line.split(":", maxsplit=1)
                headers[name] = value.strip()
                continue
            body_lines.append(line)

        body_text = "\n".join(body_lines).strip()
        requests.append(
            {
                "method": method,
                "url": urlparse(url).path,
                "headers": headers,
                "json": json.loads(body_text) if body_text else None,
            }
        )

    return requests


class LogsApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_logs_http_examples_run_against_api(self) -> None:
        db = StubRawLogsDB()
        users_db = StubUsersDB(org_id="project_context.org_id")
        examples = parse_http_examples(HTTP_EXAMPLES)

        self.assertEqual(len(examples), 2)

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db", return_value=db),
        ):
            accepted = self.client.request(**examples[0])
            empty = self.client.request(**examples[1])

        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(
            accepted.json(),
            {
                "message": "Successfully processed 1 items",
                "processed_count": 1,
            },
        )
        self.assertEqual(empty.status_code, 204)
        self.assertEqual(len(users_db.api_keys), 2)
        self.assertEqual(len(db.inserted_batches), 1)
        self.assertEqual(len(db.inserted_batches[0]), 1)
        self.assertEqual(db.inserted_batches[0][0].message, "User user-local-001 logged in")

    def test_ingest_logs_uses_raw_logs_db_for_non_empty_payloads(self) -> None:
        db = StubRawLogsDB()
        org_id = uuid4()
        users_db = StubUsersDB(org_id=org_id)
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db) as get_users_db,
            patch("api.v1.logs.get_rawlogs_db", return_value=db) as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=payload,
            )

        self.assertEqual(response.status_code, 202)
        get_users_db.assert_called_once_with()
        self.assertEqual(users_db.api_keys[0].key_id, TEST_API_KEY_ID)
        self.assertEqual(users_db.api_keys[0].secret, TEST_API_KEY_SECRET)
        self.assertEqual(users_db.required_scopes, ["logs:write"])
        get_db.assert_called_once_with(org_id)
        self.assertEqual(len(db.inserted_batches), 1)
        self.assertEqual(db.inserted_batches[0][0].signature_key(), ("auth.py", "User {user_id} logged in", "login", 42))

    def test_ingest_logs_authenticates_but_skips_raw_db_for_empty_payloads(self) -> None:
        users_db = StubUsersDB(org_id=uuid4())

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db) as get_users_db,
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=[],
            )

        self.assertEqual(response.status_code, 204)
        get_users_db.assert_called_once_with()
        self.assertEqual(len(users_db.api_keys), 1)
        get_db.assert_not_called()

    def test_ingest_logs_rejects_missing_authorization_before_raw_log_db_access(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]

        with (
            patch("auth.dependencies.get_users_db") as get_users_db,
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post("/v1/logs", json=payload)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Missing Authorization header"})
        get_users_db.assert_not_called()
        get_db.assert_not_called()

    def test_ingest_logs_rejects_malformed_api_key_before_raw_log_db_access(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]

        with (
            patch("auth.dependencies.get_users_db") as get_users_db,
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": "Bearer not-a-3rdeye-key"},
                json=payload,
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Malformed API key"})
        get_users_db.assert_not_called()
        get_db.assert_not_called()

    def test_ingest_logs_rejects_unknown_api_key_before_raw_log_db_access(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]
        users_db = StubUsersDB(org_id=None)

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=payload,
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid API key"})
        self.assertEqual(users_db.api_keys[0].key_id, TEST_API_KEY_ID)
        get_db.assert_not_called()

    def test_ingest_logs_rejects_expired_or_revoked_api_key_before_raw_log_db_access(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]
        users_db = StubUsersDB(org_id=None)

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=payload,
            )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid API key"})
        get_db.assert_not_called()

    def test_ingest_logs_rejects_missing_scope_before_raw_log_db_access(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]
        users_db = StubUsersDB(org_id=uuid4(), forbidden_detail="Missing required scope")

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=payload,
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Missing required scope"})
        get_db.assert_not_called()

    def test_ingest_logs_rejects_inactive_org_before_raw_log_db_access(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]
        users_db = StubUsersDB(org_id=uuid4(), forbidden_detail="Organization is not active")

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=payload,
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Organization is not active"})
        get_db.assert_not_called()

    def test_ingest_logs_surfaces_db_failures(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]
        users_db = StubUsersDB(org_id="project_context.org_id")

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db", return_value=FailingRawLogsDB()),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    "/v1/logs",
                    headers={"Authorization": TEST_AUTHORIZATION},
                    json=payload,
                )

    def test_ingest_logs_rejects_invalid_payloads_before_db_access(self) -> None:
        users_db = StubUsersDB(org_id=uuid4())
        invalid_payload = [
            {
                "message": "Missing signature data",
                "timestamp": "2026-06-08T19:07:36.123456+00:00",
            }
        ]

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db),
            patch("api.v1.logs.get_rawlogs_db") as get_db,
        ):
            response = self.client.post(
                "/v1/logs",
                headers={"Authorization": TEST_AUTHORIZATION},
                json=invalid_payload,
            )

        self.assertEqual(response.status_code, 422)
        get_db.assert_not_called()

    def test_search_logs_uses_jwt_auth_and_returns_org_id(self) -> None:
        org_id = uuid4()
        user_id = uuid4()
        users_db = StubUsersDB(org_id=org_id)
        jwt = create_app_jwt(
            {
                "sub": str(user_id),
                "org_id": str(org_id),
                "scopes": ["logs:read"],
                "iss": "3rd-eye",
                "aud": "3rd-eye-api",
                "iat": 1_700_000_000,
                "exp": 4_100_000_000,
            }
        )

        with (
            patch("auth.dependencies.get_users_db", return_value=users_db) as get_users_db,
            patch("builtins.print") as print_org_id,
        ):
            response = self.client.get(
                "/v1/search",
                headers={"Authorization": f"Bearer {jwt}"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"org_id": str(org_id)})
        get_users_db.assert_called_once_with()
        self.assertEqual(users_db.jwt_claims[0].org_id, org_id)
        self.assertEqual(users_db.required_scopes, ["logs:read"])
        print_org_id.assert_called_once_with(org_id)


if __name__ == "__main__":
    unittest.main()
