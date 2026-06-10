from collections.abc import Iterable
from math import isfinite
from operator import eq, ge, gt, le, lt, ne

from analysis.models import AggregateSnapshot, AnalysisFinding, BaselineSnapshot
from analysis.rules import AnalysisRule, RuleCondition


_OPERATORS = {
    ">": gt,
    ">=": ge,
    "<": lt,
    "<=": le,
    "==": eq,
    "!=": ne,
}

_Z_SCORE_BY_SENSITIVITY = {
    "low": 3.0,
    "medium": 2.0,
    "high": 1.5,
}

_DISTANCE_BY_SENSITIVITY = {
    "low": 0.45,
    "medium": 0.30,
    "high": 0.20,
}


class AnalysisEngine:
    def __init__(self, rules: Iterable[AnalysisRule]) -> None:
        self.rules = list(rules)

    def evaluate(
        self,
        snapshot: AggregateSnapshot,
        baseline: BaselineSnapshot | None = None,
    ) -> list[AnalysisFinding]:
        baseline = baseline or BaselineSnapshot()
        findings: list[AnalysisFinding] = []

        for rule in self.rules:
            if not rule.enabled or rule.window != snapshot.window:
                continue

            finding = self._evaluate_rule(rule, snapshot, baseline)
            if finding is not None:
                findings.append(finding)

        return findings

    def _evaluate_rule(
        self,
        rule: AnalysisRule,
        snapshot: AggregateSnapshot,
        baseline: BaselineSnapshot,
    ) -> AnalysisFinding | None:
        condition = rule.condition

        if condition.type == "threshold":
            return _evaluate_threshold(rule, snapshot)
        if condition.type == "anomaly":
            return _evaluate_anomaly(rule, snapshot, baseline)
        if condition.type == "distribution_shift":
            return _evaluate_distribution_shift(rule, snapshot, baseline)
        if condition.type == "missing_expected_pattern":
            return _evaluate_missing_expected_pattern(rule, snapshot, baseline)

        raise ValueError(f"Unsupported condition type: {condition.type}")


def _evaluate_threshold(rule: AnalysisRule, snapshot: AggregateSnapshot) -> AnalysisFinding | None:
    condition = rule.condition
    observed = snapshot.metric_value(rule.metric, rule.filter)
    operator_fn = _OPERATORS[condition.operator]

    if not operator_fn(observed, condition.value):
        return None

    return AnalysisFinding(
        rule_id=rule.id,
        window=rule.window,
        severity=rule.severity,
        message=f"{rule.id} matched: observed {observed:g} {condition.operator} {condition.value:g}",
        observed_value=observed,
        expected_value=condition.value,
    )


def _evaluate_anomaly(
    rule: AnalysisRule,
    snapshot: AggregateSnapshot,
    baseline: BaselineSnapshot,
) -> AnalysisFinding | None:
    condition = rule.condition
    metric_key = _metric_key(rule)
    metric_baseline = baseline.metric_stats.get(metric_key)
    if metric_baseline is None or metric_baseline.sample_count <= 0:
        return None

    observed = snapshot.metric_value(rule.metric, rule.filter)
    expected = metric_baseline.mean
    delta = observed - expected
    percent_change = abs(delta) / expected if expected else float("inf")

    if metric_baseline.stddev == 0:
        is_unusual = observed != expected and percent_change >= condition.min_percent_change
        z_score = None
    else:
        z_score = delta / metric_baseline.stddev
        threshold = _z_score_threshold(condition)
        is_unusual = abs(z_score) >= threshold and percent_change >= condition.min_percent_change

    if not is_unusual:
        return None

    details = {
        "metric_key": metric_key,
        "baseline_sample_count": metric_baseline.sample_count,
        "percent_change": percent_change,
    }
    if z_score is not None and isfinite(z_score):
        details["z_score"] = z_score

    return AnalysisFinding(
        rule_id=rule.id,
        window=rule.window,
        severity=rule.severity,
        message=f"{rule.id} matched: {metric_key} moved from {expected:g} to {observed:g}",
        observed_value=observed,
        expected_value=expected,
        details=details,
    )


def _evaluate_distribution_shift(
    rule: AnalysisRule,
    snapshot: AggregateSnapshot,
    baseline: BaselineSnapshot,
) -> AnalysisFinding | None:
    condition = rule.condition
    observed = snapshot.distribution(rule.metric)
    expected = baseline.distributions.get(rule.metric)
    if not observed or not expected:
        return None

    distance = _total_variation_distance(observed, expected)
    threshold = condition.distance_threshold or _DISTANCE_BY_SENSITIVITY[condition.sensitivity]
    if distance < threshold:
        return None

    return AnalysisFinding(
        rule_id=rule.id,
        window=rule.window,
        severity=rule.severity,
        message=f"{rule.id} matched: {rule.metric} shifted by {distance:.3f}",
        observed_value=distance,
        expected_value=threshold,
        details={
            "distance": distance,
            "threshold": threshold,
            "top_changes": _top_distribution_changes(observed, expected),
        },
    )


def _evaluate_missing_expected_pattern(
    rule: AnalysisRule,
    snapshot: AggregateSnapshot,
    baseline: BaselineSnapshot,
) -> AnalysisFinding | None:
    condition = rule.condition
    expected_keys = set(condition.expected_patterns) or {
        key
        for key, pattern in baseline.expected_patterns.items()
        if pattern.historical_occurrences >= condition.min_historical_occurrences
    }
    if not expected_keys:
        return None

    observed_keys = {key for key, count in snapshot.counts_by_template.items() if count > 0}
    missing = sorted(expected_keys - observed_keys)
    if not missing:
        return None

    return AnalysisFinding(
        rule_id=rule.id,
        window=rule.window,
        severity=rule.severity,
        message=f"{rule.id} matched: {len(missing)} expected pattern(s) missing",
        observed_value=float(len(missing)),
        expected_value=0,
        details={
            "missing_patterns": missing,
            "schedule": condition.schedule,
        },
    )


def _metric_key(rule: AnalysisRule) -> str:
    if not rule.filter:
        return rule.metric

    filter_parts = ",".join(f"{key}={value}" for key, value in sorted(rule.filter.items()))
    return f"{rule.metric}[{filter_parts}]"


def _z_score_threshold(condition: RuleCondition) -> float:
    return condition.z_score_threshold or _Z_SCORE_BY_SENSITIVITY[condition.sensitivity]


def _total_variation_distance(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0) - right.get(key, 0)) for key in keys)


def _top_distribution_changes(
    observed: dict[str, float],
    expected: dict[str, float],
    limit: int = 5,
) -> list[dict[str, float | str]]:
    keys = set(observed) | set(expected)
    changes = [
        {
            "key": key,
            "observed": observed.get(key, 0),
            "expected": expected.get(key, 0),
            "delta": observed.get(key, 0) - expected.get(key, 0),
        }
        for key in keys
    ]
    return sorted(changes, key=lambda item: abs(float(item["delta"])), reverse=True)[:limit]
