"""Condition evaluator: comparisons, regex, threshold checks."""
import math
import re
from typing import Any, Dict, List, Optional
from .parser import Condition, Rule


class ConditionEvaluator:
    """Evaluate a single condition or all conditions of a rule against a metric event."""

    def __init__(self, field_accessor: Optional[callable] = None):
        self._accessor = field_accessor or self._default_accessor

    @staticmethod
    def _default_accessor(event: Dict[str, Any], field: str) -> Any:
        parts = field.split(".")
        obj = event
        for p in parts:
            if isinstance(obj, dict):
                obj = obj.get(p)
            else:
                return None
        return obj

    def _compare(self, actual: Any, operator: str, expected: Any) -> bool:
        if actual is None:
            return False
        ops = {
            "gt": lambda a, e: a > e,
            "gte": lambda a, e: a >= e,
            "lt": lambda a, e: a < e,
            "lte": lambda a, e: a <= e,
            "eq": lambda a, e: a == e,
            "neq": lambda a, e: a != e,
        }
        if operator in ops:
            try:
                return ops[operator](float(actual), float(expected))
            except (TypeError, ValueError):
                return ops[operator](actual, expected)
        if operator == "regex":
            return bool(re.search(str(expected), str(actual)))
        if operator == "contains":
            return str(expected) in str(actual)
        raise ValueError(f"Unsupported operator: {operator}")

    def evaluate_condition(self, event: Dict[str, Any], condition: Condition) -> bool:
        actual = self._accessor(event, condition.field)
        return self._compare(actual, condition.operator, condition.value)

    def evaluate_rule(self, event: Dict[str, Any], rule: Rule) -> bool:
        return all(self.evaluate_condition(event, c) for c in rule.conditions)

    def evaluate_rules(self, event: Dict[str, Any], rules: List[Rule]) -> List[Rule]:
        return [r for r in rules if self.evaluate_rule(event, r)]