import json
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from main import app


HTTP_EXAMPLES = Path(__file__).with_name("logs.http")


class StubRawLogsDB:
    def __init__(self) -> None:
        self.inserted_batches = []

    async def insert_raw_logs(self, log_events):
        self.inserted_batches.append(log_events)


class FailingRawLogsDB:
    async def insert_raw_logs(self, log_events):
        raise RuntimeError("database unavailable")


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
        examples = parse_http_examples(HTTP_EXAMPLES)

        self.assertEqual(len(examples), 2)

        with patch("api.v1.logs.get_rawlogs_db", return_value=db):
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
        self.assertEqual(len(db.inserted_batches), 1)
        self.assertEqual(len(db.inserted_batches[0]), 1)
        self.assertEqual(db.inserted_batches[0][0].message, "User user-local-001 logged in")

    def test_ingest_logs_uses_raw_logs_db_for_non_empty_payloads(self) -> None:
        db = StubRawLogsDB()
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]

        with patch("api.v1.logs.get_rawlogs_db", return_value=db) as get_db:
            response = self.client.post("/v1/logs", json=payload)

        self.assertEqual(response.status_code, 202)
        get_db.assert_called_once_with("project_context.org_id")
        self.assertEqual(len(db.inserted_batches), 1)
        self.assertEqual(db.inserted_batches[0][0].signature_key(), ("auth.py", "User {user_id} logged in", "login", 42))

    def test_ingest_logs_skips_db_for_empty_payloads(self) -> None:
        with patch("api.v1.logs.get_rawlogs_db") as get_db:
            response = self.client.post("/v1/logs", json=[])

        self.assertEqual(response.status_code, 204)
        get_db.assert_not_called()

    def test_ingest_logs_surfaces_db_failures(self) -> None:
        payload = parse_http_examples(HTTP_EXAMPLES)[0]["json"]

        with patch("api.v1.logs.get_rawlogs_db", return_value=FailingRawLogsDB()):
            with self.assertRaises(RuntimeError):
                self.client.post("/v1/logs", json=payload)

    def test_ingest_logs_rejects_invalid_payloads_before_db_access(self) -> None:
        invalid_payload = [
            {
                "message": "Missing signature data",
                "timestamp": "2026-06-08T19:07:36.123456+00:00",
            }
        ]

        with patch("api.v1.logs.get_rawlogs_db") as get_db:
            response = self.client.post("/v1/logs", json=invalid_payload)

        self.assertEqual(response.status_code, 422)
        get_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
