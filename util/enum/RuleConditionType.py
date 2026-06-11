from enum import Enum


class RuleConditionType(str, Enum):
    THRESHOLD = "threshold"
    ANOMALY = "anomaly"
    GROUP_ANOMALY = "group_anomaly"
    DISTRIBUTION_SHIFT = "distribution_shift"
    MISSING_EXPECTED_PATTERN = "missing_expected_pattern"
