"""Time-window aggregation for metrics before rule evaluation."""
import math
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from .parser import Aggregation, Rule


class _Bucket:
    __slots__ = ("values", "expire_at")

    def __init__(self, expire_at: float):
        self.values: List[float] = []
        self.expire_at = expire_at


class TimeWindowAggregator:
    """Maintain sliding time windows and compute aggregations per group key."""

    def __init__(self):
        self._buckets: Dict[Tuple[str, str], _Bucket] = {}

    def _group_key(self, event: Dict[str, Any], group_by: List[str]) -> str:
        return "|".join(str(event.get(g, "")) for g in group_by)

    def _make_bucket_key(self, rule_id: str, group_key: str) -> Tuple[str, str]:
        return (rule_id, group_key)

    def ingest(self, event: Dict[str, Any], rule: Rule, now: Optional[float] = None) -> None:
        if not rule.aggregation:
            return
        now = now or time.time()
        agg = rule.aggregation
        group_key = self._group_key(event, agg.group_by)
        bk = self._make_bucket_key(rule.id, group_key)
        bucket = self._buckets.get(bk)
        if bucket is None or bucket.expire_at <= now:
            bucket = _Bucket(expire_at=now + agg.window_seconds)
            self._buckets[bk] = bucket
        metric_val = event.get("value", event.get("metric_value"))
        if metric_val is not None:
            try:
                bucket.values.append(float(metric_val))
            except (TypeError, ValueError):
                pass

    def compute(self, event: Dict[str, Any], rule: Rule, now: Optional[float] = None) -> Optional[float]:
        if not rule.aggregation:
            return None
        now = now or time.time()
        agg = rule.aggregation
        group_key = self._group_key(event, agg.group_by)
        bk = self._make_bucket_key(rule.id, group_key)
        bucket = self._buckets.get(bk)
        if bucket is None or not bucket.values:
            return None
        vals = bucket.values
        fn = agg.fn
        if fn == "avg":
            return sum(vals) / len(vals)
        if fn == "sum":
            return sum(vals)
        if fn == "min":
            return min(vals)
        if fn == "max":
            return max(vals)
        if fn == "count":
            return float(len(vals))
        if fn == "p95":
            sv = sorted(vals)
            idx = int(math.ceil(0.95 * len(sv))) - 1
            return sv[max(idx, 0)]
        return None

    def expire(self, now: Optional[float] = None) -> int:
        now = now or time.time()
        expired = [k for k, b in self._buckets.items() if b.expire_at <= now]
        for k in expired:
            del self._buckets[k]
        return len(expired)