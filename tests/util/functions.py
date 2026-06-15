import unittest
from datetime import datetime, timezone, timedelta

from util.functions import normalize_counts, timestamp_for_storage, to_snake_case


class UtilFunctionsTestCase(unittest.TestCase):
    def test_timestamp_for_storage_adds_utc_to_naive_datetime(self) -> None:
        timestamp = datetime(2026, 6, 10, 12, 30)

        stored = timestamp_for_storage(timestamp)

        self.assertEqual(stored, datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc))

    def test_timestamp_for_storage_preserves_aware_datetime(self) -> None:
        offset = timezone(timedelta(hours=-5))
        timestamp = datetime(2026, 6, 10, 12, 30, tzinfo=offset)

        stored = timestamp_for_storage(timestamp)

        self.assertIs(stored, timestamp)
        self.assertEqual(stored.tzinfo, offset)

    def test_normalize_counts_returns_fraction_by_key(self) -> None:
        counts = {"INFO": 8, "ERROR": 2}

        normalized = normalize_counts(counts)

        self.assertEqual(normalized, {"INFO": 0.8, "ERROR": 0.2})

    def test_normalize_counts_returns_empty_for_non_positive_totals(self) -> None:
        self.assertEqual(normalize_counts({}), {})
        self.assertEqual(normalize_counts({"INFO": 0, "ERROR": 0}), {})
        self.assertEqual(normalize_counts({"INFO": 1, "ERROR": -1}), {})

    def test_to_snake_case_converts_camel_case(self) -> None:
        self.assertEqual(to_snake_case("RawLogDTO"), "raw_log_d_t_o")
        self.assertEqual(to_snake_case("LogSignature"), "log_signature")
        self.assertEqual(to_snake_case("DBModel"), "d_b_model")

    def test_to_snake_case_preserves_existing_lowercase_words(self) -> None:
        self.assertEqual(to_snake_case("already_snake"), "already_snake")
        self.assertEqual(to_snake_case("lowercase"), "lowercase")


if __name__ == "__main__":
    unittest.main()
