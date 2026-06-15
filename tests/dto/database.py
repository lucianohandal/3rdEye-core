from __future__ import annotations

import json
import random
import unittest
from datetime import datetime, timezone
from enum import Enum
from types import UnionType
from typing import Any, get_args, get_origin
from uuid import UUID, uuid4

from pydantic import BaseModel

from util.dto.api.LogEventDTO import LogEventDTO
from util.dto.database.AlertDTO import AlertDTO
from util.dto.database.DBModel import DBModel
from util.dto.database.LogSignatureDTO import LogSignatureDTO
from util.dto.database.RawLogDTO import RawLogDTO
from util.enum.LogLevel import LogLevel
from util.enum.Severity import Severity


RANDOM = random.Random(20260615)


def random_model_data(model_class: type[BaseModel], nullable: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, field in model_class.model_fields.items():
        if nullable and _is_nullable(field.annotation):
            data[name] = None
            continue
        data[name] = random_value(field.annotation, name)
    return data


def random_dto_instance(model_class: type[BaseModel], nullable: bool = False) -> BaseModel:
    return model_class.model_validate(random_model_data(model_class, nullable=nullable))


def nullable_field_names(model_class: type[BaseModel]) -> set[str]:
    return {
        name
        for name, field in model_class.model_fields.items()
        if _is_nullable(field.annotation)
    }


def assert_db_model_contract(
    test_case: unittest.TestCase,
    model_class: type[DBModel],
    instance: DBModel,
    expected_table_name: str,
) -> None:
    fields = list(model_class.model_fields)
    included = set(fields[:2])
    excluded = {fields[-1]}

    test_case.assertEqual(instance.db_dump(), instance.model_dump(mode="python"))
    test_case.assertEqual(instance.get_values(), tuple(instance.db_dump().values()))

    test_case.assertEqual(model_class.fields(), fields)
    test_case.assertEqual(
        model_class.fields(include=included),
        [field for field in fields if field in included],
    )
    test_case.assertEqual(
        model_class.fields(exclude=excluded),
        [field for field in fields if field not in excluded],
    )

    test_case.assertEqual(model_class.field_list(), ",".join(fields))
    test_case.assertEqual(
        model_class.field_list(include=included),
        ",".join(field for field in fields if field in included),
    )
    test_case.assertEqual(
        model_class.set_clause(include=included),
        ", ".join(
            f"{field} = ${index}"
            for index, field in enumerate([field for field in fields if field in included], start=1)
        ),
    )
    test_case.assertEqual(
        model_class.place_holders(include=included),
        ",".join(f"${index}" for index in range(1, len(included) + 1)),
    )
    test_case.assertEqual(model_class.table_name(), expected_table_name)
    test_case.assertEqual(model_class.update_fields(), [field for field in fields if field not in {"id", "org_id"}])


def _is_nullable(annotation: Any) -> bool:
    return type(None) in get_args(annotation)


def _without_none(annotation: Any) -> Any:
    return next(arg for arg in get_args(annotation) if arg is not type(None))


def random_value(annotation: Any, name: str = "value") -> Any:
    if _is_nullable(annotation):
        return random_value(_without_none(annotation), name)

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in (list,):
        return [random_value(args[0], name)]
    if origin is dict:
        value_type = args[1] if len(args) > 1 else Any
        return {f"{name}_key": random_value(value_type, name)}
    if origin in (UnionType,):
        return random_value(args[0], name)

    if annotation is Any:
        return {"sample": f"{name}-{RANDOM.randint(100, 999)}"}
    if annotation is UUID:
        return uuid4()
    if annotation is datetime:
        return datetime(2026, 6, RANDOM.randint(1, 28), 12, 30, tzinfo=timezone.utc)
    if annotation is str:
        return f"{name}-{RANDOM.randint(100, 999)}"
    if annotation is int:
        return RANDOM.randint(1, 100)
    if annotation is float:
        return round(RANDOM.uniform(1, 100), 2)
    if annotation is bool:
        return True
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return list(annotation)[0]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return random_dto_instance(annotation)

    return f"{name}-{RANDOM.randint(100, 999)}"


class DatabaseDTOInitializationTestCase(unittest.TestCase):
    def test_db_model_base_init_with_all_values(self) -> None:
        data = random_model_data(DBModel)
        dto = DBModel.model_validate(data)

        self.assertEqual(dto.id, data["id"])
        self.assertEqual(dto.org_id, data["org_id"])

    def test_db_model_base_init_with_nullable_values(self) -> None:
        data = random_model_data(DBModel, nullable=True)
        dto = DBModel.model_validate(data)

        self.assertEqual(dto.id, data["id"])
        self.assertEqual(dto.org_id, data["org_id"])

    def test_database_dtos_init_with_all_values(self) -> None:
        for model_class in [AlertDTO, LogSignatureDTO, RawLogDTO]:
            with self.subTest(model_class=model_class.__name__):
                data = random_model_data(model_class)
                dto = model_class.model_validate(data)

                for field, value in data.items():
                    self.assertEqual(getattr(dto, field), value)

    def test_database_dtos_init_with_nullable_values(self) -> None:
        for model_class in [AlertDTO, LogSignatureDTO, RawLogDTO]:
            with self.subTest(model_class=model_class.__name__):
                data = random_model_data(model_class, nullable=True)
                dto = model_class.model_validate(data)

                self.assertIsInstance(dto, model_class)
                for field in nullable_field_names(model_class):
                    self.assertIsNone(getattr(dto, field))

    def test_db_model_json_samples_parse(self) -> None:
        samples = [
            {"id": str(uuid4()), "org_id": str(uuid4())},
            {"id": str(uuid4()), "org_id": str(uuid4())},
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                dto = DBModel.model_validate_json(json.dumps(sample))
                self.assertEqual(str(dto.id), sample["id"])
                self.assertEqual(str(dto.org_id), sample["org_id"])

    def test_alert_json_samples_parse(self) -> None:
        samples = [
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "rule_id": "error_logs_unusually_high",
                "severity": Severity.HIGH,
                "message": "API error count is above the expected baseline.",
                "observed_value": 242.0,
                "expected_value": 81.0,
                "details": {"metric_key": "log_count[level=ERROR]", "z_score": 3.1},
                "created_at": "2026-06-10T12:30:00Z",
                "closed_at": None,
            },
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "rule_id": "missing_expected_logs",
                "severity": Severity.CRITICAL,
                "message": "Billing job completion log did not arrive.",
                "observed_value": 1.0,
                "expected_value": 0.0,
                "details": {"missing_source_ids": ["billing-job-finished"]},
                "created_at": "2026-06-11T03:00:00Z",
                "closed_at": "2026-06-11T03:15:00Z",
            },
        ]

        for sample in samples:
            with self.subTest(rule_id=sample["rule_id"]):
                dto = AlertDTO.model_validate_json(json.dumps(sample))
                self.assertEqual(dto.rule_id, sample["rule_id"])
                self.assertEqual(dto.severity, sample["severity"])
                self.assertEqual(dto.details, sample["details"])

    def test_log_signature_json_samples_parse(self) -> None:
        samples = [
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "template": "Failed to charge card for account {account_id}",
                "line": 218,
                "file": "billing/payments.py",
                "method": "charge_customer",
                "first_appearance_timestamp": "2026-06-10T13:45:00Z",
                "first_appearance_commit": "8d1f4c9",
                "log_level": LogLevel.ERROR,
            },
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "template": "Worker heartbeat received",
                "line": 44,
                "file": "workers/heartbeat.py",
                "method": "receive_heartbeat",
                "first_appearance_timestamp": "2026-06-10T00:00:00Z",
                "first_appearance_commit": None,
                "log_level": LogLevel.INFO,
            },
        ]

        for sample in samples:
            with self.subTest(template=sample["template"]):
                dto = LogSignatureDTO.model_validate_json(json.dumps(sample))
                self.assertEqual(dto.template, sample["template"])
                self.assertEqual(dto.log_level, sample["log_level"])

    def test_raw_log_json_samples_parse(self) -> None:
        samples = [
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "message": "Payment failed for account acct_123",
                "timestamp": "2026-06-10T13:45:10Z",
                "stack": "Traceback: payment gateway timeout",
                "signature_id": str(uuid4()),
                "service": "billing-api",
                "environment": "production",
                "version": "2026.06.10",
                "git_sha": "8d1f4c9",
                "trace_id": "trace-abc",
                "span_id": "span-def",
                "request_id": "req-123",
                "user_id": "user-456",
                "attributes": {"gateway": "stripe", "retryable": True},
            },
            {
                "id": str(uuid4()),
                "org_id": str(uuid4()),
                "message": "Worker heartbeat received",
                "timestamp": "2026-06-10T00:00:00Z",
                "stack": None,
                "signature_id": None,
                "service": None,
                "environment": None,
                "version": None,
                "git_sha": None,
                "trace_id": None,
                "span_id": None,
                "request_id": None,
                "user_id": None,
                "attributes": {},
            },
        ]

        for sample in samples:
            with self.subTest(message=sample["message"]):
                dto = RawLogDTO.model_validate_json(json.dumps(sample))
                self.assertEqual(dto.message, sample["message"])
                self.assertEqual(dto.attributes, sample["attributes"])


class DatabaseDBModelContractTestCase(unittest.TestCase):
    def test_database_dtos_follow_db_model_contract(self) -> None:
        cases = [
            (AlertDTO, "alerts"),
            (LogSignatureDTO, "log_signatures"),
            (RawLogDTO, "raw_logs"),
        ]

        for model_class, table_name in cases:
            with self.subTest(model_class=model_class.__name__):
                assert_db_model_contract(
                    self,
                    model_class,
                    random_dto_instance(model_class),
                    table_name,
                )


class DatabaseDTOFactoryMethodTestCase(unittest.TestCase):
    def test_log_signature_from_log_event(self) -> None:
        org_id = uuid4()
        event = random_dto_instance(LogEventDTO)

        signature = LogSignatureDTO.from_log_event(event, org_id)

        self.assertEqual(signature.org_id, org_id)
        self.assertEqual(signature.template, event.template)
        self.assertEqual(signature.line, event.line)
        self.assertEqual(signature.file, event.file)
        self.assertEqual(signature.method, event.method)
        self.assertEqual(signature.first_appearance_timestamp, event.timestamp)
        self.assertEqual(signature.first_appearance_commit, event.git_sha)
        self.assertEqual(signature.log_level, event.level)

    def test_raw_log_from_log_event(self) -> None:
        org_id = uuid4()
        signature_id = uuid4()
        event = random_dto_instance(LogEventDTO)

        raw_log = RawLogDTO.from_log_event(event, org_id, signature_id)

        self.assertEqual(raw_log.org_id, org_id)
        self.assertEqual(raw_log.signature_id, signature_id)
        self.assertEqual(raw_log.message, event.message)
        self.assertEqual(raw_log.timestamp, event.timestamp)
        self.assertEqual(raw_log.stack, event.stack)
        self.assertEqual(raw_log.service, event.service)
        self.assertEqual(raw_log.environment, event.environment)
        self.assertEqual(raw_log.version, event.version)
        self.assertEqual(raw_log.git_sha, event.git_sha)
        self.assertEqual(raw_log.trace_id, event.trace_id)
        self.assertEqual(raw_log.span_id, event.span_id)
        self.assertEqual(raw_log.request_id, event.request_id)
        self.assertEqual(raw_log.user_id, event.user_id)
        self.assertEqual(raw_log.attributes, event.attributes)


if __name__ == "__main__":
    unittest.main()
