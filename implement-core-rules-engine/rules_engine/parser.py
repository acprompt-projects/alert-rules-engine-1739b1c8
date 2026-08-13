"""Rule parser: converts rule dicts/JSON into validated Rule objects."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import re

@dataclass
class Condition:
    field: str
    operator: str  # gt, gte, lt, lte, eq, neq, regex, contains
    value: Any

@dataclass
class Aggregation:
    window_seconds: int
    fn: str  # avg, sum, min, max, count, p95
    group_by: List[str] = field(default_factory=list)

@dataclass
class Rule:
    id: str
    name: str
    conditions: List[Condition]
    aggregation: Optional[Aggregation] = None
    severity: str = "warning"
    cooldown_seconds: int = 300
    tags: Dict[str, str] = field(default_factory=dict)

VALID_OPERATORS = {"gt", "gte", "lt", "lte", "eq", "neq", "regex", "contains"}
VALID_AGG_FNS = {"avg", "sum", "min", "max", "count", "p95"}

class RuleParser:
    """Parse and validate rule definitions from dicts."""

    def parse_condition(self, raw: Dict[str, Any]) -> Condition:
        field = raw["field"]
        operator = raw["operator"]
        value = raw["value"]
        if operator not in VALID_OPERATORS:
            raise ValueError(f"Invalid operator '{operator}'; expected one of {VALID_OPERATORS}")
        if operator == "regex":
            try:
                re.compile(str(value))
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{value}': {e}")
        return Condition(field=field, operator=operator, value=value)

    def parse_aggregation(self, raw: Dict[str, Any]) -> Aggregation:
        fn = raw.get("fn", "avg")
        if fn not in VALID_AGG_FNS:
            raise ValueError(f"Invalid aggregation fn '{fn}'; expected one of {VALID_AGG_FNS}")
        return Aggregation(
            window_seconds=int(raw.get("window_seconds", 300)),
            fn=fn,
            group_by=raw.get("group_by", []),
        )

    def parse_rule(self, raw: Dict[str, Any]) -> Rule:
        rule_id = raw.get("id")
        name = raw.get("name", rule_id)
        if not rule_id:
            raise ValueError("Rule must have an 'id'")
        conditions = [self.parse_condition(c) for c in raw.get("conditions", [])]
        if not conditions:
            raise ValueError(f"Rule '{rule_id}' must have at least one condition")
        aggregation = None
        if "aggregation" in raw:
            aggregation = self.parse_aggregation(raw["aggregation"])
        return Rule(
            id=rule_id,
            name=name,
            conditions=conditions,
            aggregation=aggregation,
            severity=raw.get("severity", "warning"),
            cooldown_seconds=int(raw.get("cooldown_seconds", 300)),
            tags=raw.get("tags", {}),
        )

    def parse_rules(self, raw_list: List[Dict[str, Any]]) -> List[Rule]:
        return [self.parse_rule(r) for r in raw_list]