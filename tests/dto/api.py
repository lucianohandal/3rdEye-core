from __future__ import annotations

import json
import unittest

from util.dto.api.LogEventDTO import LogEventDTO
from util.enum.LogLevel import LogLevel

from tests.dto.database import nullable_field_names, random_model_data


class ApiDTOInitializationTestCase(unittest.TestCase):
    def test_log_event_init_with_all_values(self) -> None:
        data = random_model_data(LogEventDTO)
        dto = LogEventDTO.model_validate(data)

        for field, value in data.items():
            self.assertEqual(getattr(dto, field), value)

    def test_log_event_init_with_nullable_values(self) -> None:
        data = random_model_data(LogEventDTO, nullable=True)
        dto = LogEventDTO.model_validate(data)

        self.assertIsInstance(dto, LogEventDTO)
        for field in nullable_field_names(LogEventDTO):
            self.assertIsNone(getattr(dto, field))

    def test_log_event_json_samples_parse(self) -> None:
        samples = [
            {
                "message": "Failed to charge card for account acct_123",
                "timestamp": "2026-06-10T13:45:10Z",
                "stack": "Traceback: payment gateway timeout",
                "service": "billing-api",
                "environment": "production",
                "version": "2026.06.10",
                "git_sha": "8d1f4c9",
                "trace_id": "trace-abc",
                "span_id": "span-def",
                "request_id": "req-123",
                "user_id": "user-456",
                "attributes": {"gateway": "stripe", "retryable": True},
                "level": LogLevel.ERROR,
                "template": "Failed to charge card for account {account_id}",
                "file": "billing/payments.py",
                "line": 218,
                "method": "charge_customer",
            },
            {
                "message": "User login completed",
                "timestamp": "2026-06-10T14:00:00Z",
                "stack": None,
                "service": "identity-api",
                "environment": "staging",
                "version": "2026.06.10",
                "git_sha": "b9e42aa",
                "trace_id": "trace-login",
                "span_id": None,
                "request_id": "req-login",
                "user_id": "user-789",
                "attributes": {"region": "us-central"},
                "level": LogLevel.INFO,
                "template": "User login completed",
                "file": "auth/login.py",
                "line": 73,
                "method": "complete_login",
            },
        ]

        for sample in samples:
            with self.subTest(message=sample["message"]):
                dto = LogEventDTO.model_validate_json(json.dumps(sample))
                self.assertEqual(dto.message, sample["message"])
                self.assertEqual(dto.level, sample["level"])
                self.assertEqual(dto.signature_key(), (sample["file"], sample["template"], sample["method"], sample["line"]))

    def test_signature_key_with_all_values(self) -> None:
        dto = LogEventDTO.model_validate(random_model_data(LogEventDTO))

        self.assertEqual(
            dto.signature_key(),
            (dto.file, dto.template, dto.method, dto.line),
        )

    def test_signature_key_with_nullable_values(self) -> None:
        dto = LogEventDTO.model_validate(random_model_data(LogEventDTO, nullable=True))

        self.assertEqual(
            dto.signature_key(),
            (dto.file, dto.template, dto.method, dto.line),
        )


if __name__ == "__main__":
    unittest.main()
