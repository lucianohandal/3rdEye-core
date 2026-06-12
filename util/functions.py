from datetime import datetime, timezone
import re

def timestamp_for_storage(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def normalize_counts(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {key: count / total for key, count in counts.items()}

def to_snake_case(name: str) -> str:

    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
