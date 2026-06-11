from collections.abc import Iterable
from math import isfinite

from analysis.models import AnalysisFinding, BaselineSnapshot
from analysis.rules import AnalysisRule, RuleCondition
from util.dto.LogSummaryDTO import LogSummaryDTO
from util.enum.RuleConditionType import RuleConditionType


class AnalysisEngine:
    def __init__(self, rules: Iterable[AnalysisRule]) -> None:
        self.rules = list(rules)

    def evaluate(
        self,
        snapshot: LogSummaryDTO,
        baseline: BaselineSnapshot | None = None,
    ) -> list[AnalysisFinding]:
        baseline = baseline or BaselineSnapshot()
        findings: list[AnalysisFinding] = []

        for rule in self.rules:
            if not rule.enabled or rule.window != snapshot.window:
                continue

            findings.extend(self._evaluate_rule(rule, snapshot, baseline))

        return findings

    def _evaluate_rule(
        self,
        rule: AnalysisRule,
        snapshot: LogSummaryDTO,
        baseline: BaselineSnapshot,
    ) -> list[AnalysisFinding]:
        condition = rule.condition

        if condition.type == RuleConditionType.THRESHOLD:
            return _as_findings(_evaluate_threshold(rule, snapshot))
        if condition.type == RuleConditionType.ANOMALY:
            return _as_findings(_evaluate_anomaly(rule, snapshot, baseline))
        if condition.type == RuleConditionType.GROUP_ANOMALY:
            return _evaluate_group_anomaly(rule, snapshot, baseline)
        if condition.type == RuleConditionType.DISTRIBUTION_SHIFT:
            return _as_findings(_evaluate_distribution_shift(rule, snapshot, baseline))
        if condition.type == RuleConditionType.MISSING_EXPECTED_PATTERN:
            return _as_findings(_evaluate_missing_expected_pattern(rule, snapshot, baseline))

        raise ValueError(f"Unsupported condition type: {condition.type}")


def _evaluate_threshold(rule: AnalysisRule, snapshot: LogSummaryDTO) -> AnalysisFinding | None:
    condition = rule.condition
    observed = snapshot.metric_value(rule.metric, rule.filter)

    if not condition.operator.compare(observed, condition.value):
        return None

    return AnalysisFinding(
        rule_id=rule.id,
        window=rule.window,
        severity=rule.severity,
        message=f"{rule.id} matched: observed {observed:g} {condition.operator.value} {condition.value:g}",
        observed_value=observed,
        expected_value=condition.value,
    )


def _evaluate_anomaly(
    rule: AnalysisRule,
    snapshot: LogSummaryDTO,
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

    z_score, is_unusual = _is_unusual_change(
        observed=observed,
        expected=expected,
        stddev=metric_baseline.stddev,
        condition=condition,
    )

    if not is_unusual or not _matches_direction(delta, condition.direction):
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


def _evaluate_group_anomaly(
    rule: AnalysisRule,
    snapshot: LogSummaryDTO,
    baseline: BaselineSnapshot,
) -> list[AnalysisFinding]:
    findings: list[AnalysisFinding] = []
    observed_series = snapshot.metric_series(rule.metric, rule.filter)
    group_filter_name = _group_filter_name(rule.metric)

    for group_key, observed in observed_series.items():
        metric_key = _metric_key(rule, {group_filter_name: group_key})
        metric_baseline = baseline.metric_stats.get(metric_key)
        if metric_baseline is None or metric_baseline.sample_count <= 0:
            continue

        expected = metric_baseline.mean
        delta = observed - expected
        z_score, is_unusual = _is_unusual_change(
            observed=observed,
            expected=expected,
            stddev=metric_baseline.stddev,
            condition=rule.condition,
        )
        if not is_unusual or not _matches_direction(delta, rule.condition.direction):
            continue

        percent_change = abs(delta) / expected if expected else float("inf")
        details = {
            "metric_key": metric_key,
            "group_key": group_key,
            group_filter_name: group_key,
            "baseline_sample_count": metric_baseline.sample_count,
            "percent_change": percent_change,
        }
        if z_score is not None and isfinite(z_score):
            details["z_score"] = z_score

        findings.append(
            AnalysisFinding(
                rule_id=rule.id,
                window=rule.window,
                severity=rule.severity,
                message=f"{rule.id} matched for {group_key}: {observed:.3f} vs expected {expected:.3f}",
                observed_value=observed,
                expected_value=expected,
                details=details,
            )
        )

    return findings


def _evaluate_distribution_shift(
    rule: AnalysisRule,
    snapshot: LogSummaryDTO,
    baseline: BaselineSnapshot,
) -> AnalysisFinding | None:
    condition = rule.condition
    observed = snapshot.distribution(rule.metric)
    expected = baseline.distributions.get(rule.metric)
    if not observed or not expected:
        return None

    distance = _total_variation_distance(observed, expected)
    threshold = condition.distance_threshold or condition.sensitivity.distribution_distance_threshold
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
    snapshot: LogSummaryDTO,
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

    observed_keys = {key for key, count in snapshot.counts_by_source_id.items() if count > 0}
    missing = sorted(expected_keys - observed_keys)
    if not missing:
        return None

    return AnalysisFinding(
        rule_id=rule.id,
        window=rule.window,
        severity=rule.severity,
        message=f"{rule.id} matched: {len(missing)} expected source(s) missing",
        observed_value=float(len(missing)),
        expected_value=0,
        details={
            "missing_source_ids": missing,
            "schedule": condition.schedule,
        },
    )


def _as_findings(finding: AnalysisFinding | None) -> list[AnalysisFinding]:
    if finding is None:
        return []
    return [finding]


def _metric_key(rule: AnalysisRule, extra_filters: dict[str, str] | None = None) -> str:
    filters = dict(rule.filter)
    if extra_filters:
        filters.update(extra_filters)

    if not filters:
        return rule.metric

    filter_parts = ",".join(f"{key}={value}" for key, value in sorted(filters.items()))
    return f"{rule.metric}[{filter_parts}]"


def _group_filter_name(metric: str) -> str:
    if metric == "source_rate":
        return "sourceId"
    return "group"


def _z_score_threshold(condition: RuleCondition) -> float:
    return condition.z_score_threshold or condition.sensitivity.z_score_threshold


def _is_unusual_change(
    observed: float,
    expected: float,
    stddev: float,
    condition: RuleCondition,
) -> tuple[float | None, bool]:
    percent_change = abs(observed - expected) / expected if expected else float("inf")
    if stddev == 0:
        return None, observed != expected and percent_change >= condition.min_percent_change

    z_score = (observed - expected) / stddev
    return (
        z_score,
        abs(z_score) >= _z_score_threshold(condition)
        and percent_change >= condition.min_percent_change,
    )


def _matches_direction(delta: float, direction: str) -> bool:
    if direction == "up":
        return delta > 0
    if direction == "down":
        return delta < 0
    return True


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
