"""Rule-matching pipeline: consumes metric events, evaluates rules, emits alerts."""
import time
from typing import Any, Callable, Dict, List, Optional
from .parser import Rule, RuleParser
from .evaluator import ConditionEvaluator
from .aggregator import TimeWindowAggregator


@dataclass_equivalent
class Alert:
    __slots__ = ("rule_id", "rule_name", "severity", "event", "aggregated_value", "timestamp", "tags")

    def __init__(
        self,
        rule_id: str,
        rule_name: str,
        severity: str,
        event: Dict[str, Any],
        aggregated_value: Optional[float],
        timestamp: float,
        tags: Dict[str, str],
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.severity = severity
        self.event = event
        self.aggregated_value = aggregated_value
        self.timestamp = timestamp
        self.tags = tags

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "event": self.event,
            "aggregated_value": self.aggregated_value,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


class RulesPipeline:
    """End-to-end pipeline: parse rules → ingest → evaluate → emit alerts."""

    def __init__(
        self,
        rules_config: Optional[List[Dict[str, Any]]] = None,
        on_alert: Optional[Callable[[Alert], None]] = None,
    ):
        self._parser = RuleParser()
        self._evaluator = ConditionEvaluator()
        self._aggregator = TimeWindowAggregator()
        self._on_alert = on_alert
        self._rules: List[Rule] = []
        self._cooldowns: Dict[str, float] = {}
        if rules_config:
            self.load_rules(rules_config)

    def load_rules(self, rules_config: List[Dict[str, Any]]) -> None:
        self._rules = self._parser.parse_rules(rules_config)

    def add_rule(self, rule_config: Dict[str, Any]) -> None:
        self._rules.append(self._parser.parse_rule(rule_config))

    def process_event(self, event: Dict[str, Any], now: Optional[float] = None) -> List[Alert]:
        now = now or time.time()
        alerts: List[Alert] = []
        for rule in self._rules:
            if rule.aggregation:
                self._aggregator.ingest(event, rule, now)
                agg_val = self._aggregator.compute(event, rule, now)
                if agg_val is not None:
                    enriched = dict(event, _aggregated=agg_val)
                else:
                    enriched = event
            else:
                enriched = event
                agg_val = None
            if not self._evaluator.evaluate_rule(enriched, rule):
                continue
            last = self._cooldowns.get(rule.id, 0.0)
            if now - last < rule.cooldown_seconds:
                continue
            self._cooldowns[rule.id] = now
            alert = Alert(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                event=event,
                aggregated_value=agg_val,
                timestamp=now,
                tags=rule.tags,
            )
            alerts.append(alert)
            if self._on_alert:
                self._on_alert(alert)
        return alerts

    def expire_windows(self, now: Optional[float] = None) -> int:
        return self._aggregator.expire(now)

    @property
    def rules(self) -> List[Rule]:
        return list(self._rules)