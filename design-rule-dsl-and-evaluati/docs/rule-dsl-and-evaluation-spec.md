# Alert Rule DSL & Evaluation Model Specification

## 1. Rule Schema

Alert rules are defined in YAML (or JSON) and consist of conditions, thresholds, time windows, and severity mappings.

### 1.1 Top-Level Structure

```yaml
id: string            # unique rule identifier
name: string          # human-readable name
description: string   # optional description
enabled: boolean      # default true
tags: [string]        # optional categorisation tags

metric:
  source: string      # "metrics-ingest" | "infra-observability" | custom
  name: string        # metric path, e.g. "cpu.utilization.percent"
  labels:             # optional label matchers (key-value filters)
    key: string

condition:
  operator: string    # gt | gte | lt | lte | eq | neq | between | outside
  threshold: number | [number, number]  # single value or [low, high] for between/outside
  time_window: string # e.g. "5m", "1h", "24h"  (aggregation window)
  aggregation: string # avg | min | max | sum | count | p50 | p95 | p99
  evaluation_mode: string  # "each" (every datapoint) | "window" (aggregate then compare)

severity:
  mapping:            # ordered list; first match wins
    - threshold: number   # compared with same operator as condition
      level: string       # critical | warning | info
  default_level: string   # fallback when no mapping matches

cooldown: string      # min time between repeated alerts, e.g. "10m"
notification:
  channels: [string]  # e.g. ["slack-ops", "pagerduty-oncall"]
  repeat_interval: string  # e.g. "1h"

metadata:
  owner: string
  runbook_url: string
```

### 1.2 Condition Operators

| Operator | Meaning                  | Threshold type |
|----------|--------------------------|----------------|
| gt       | greater than             | number         |
| gte      | greater than or equal    | number         |
| lt       | less than                | number         |
| lte      | less than or equal       | number         |
| eq       | equal to                 | number         |
| neq      | not equal to             | number         |
| between  | within [low, high]       | [number,number]|
| outside  | outside [low, high]      | [number,number]|

### 1.3 Time Window Format

Duration strings: `Ns` (seconds), `Nm` (minutes), `Nh` (hours), `Nd` (days).

### 1.4 Aggregation Functions

Applied over the time window before comparison: `avg`, `min`, `max`, `sum`, `count`, `p50`, `p95`, `p99`.

## 2. Example Rules

### 2.1 CPU Utilization — Critical/Warning Split

```yaml
id: cpu-util-alert
name: CPU Utilization Alert
enabled: true
tags: [infra, cpu]

metric:
  source: infra-observability
  name: cpu.utilization.percent
  labels:
    env: production

condition:
  operator: gt
  threshold: 80
  time_window: 5m
  aggregation: avg
  evaluation_mode: window

severity:
  mapping:
    - threshold: 95
      level: critical
    - threshold: 80
      level: warning
  default_level: info

cooldown: 10m
notification:
  channels: [slack-ops, pagerduty-oncall]
  repeat_interval: 1h

metadata:
  owner: platform-team
  runbook_url: https://runbooks/internal/cpu-high
```

### 2.2 Memory Low — Between Threshold (outside safe range)

```yaml
id: mem-pressure-alert
name: Memory Pressure
enabled: true

metric:
  source: metrics-ingest
  name: memory.available.bytes

condition:
  operator: lt
  threshold: 1073741824   # 1 GiB
  time_window: 2m
  aggregation: min
  evaluation_mode: window

severity:
  mapping:
    - threshold: 268435456   # 256 MiB
      level: critical
    - threshold: 1073741824  # 1 GiB
      level: warning
  default_level: info

cooldown: 5m
notification:
  channels: [slack-ops]
  repeat_interval: 30m
```

### 2.3 Error Rate — Between Range

```yaml
id: error-rate-alert
name: HTTP Error Rate
enabled: true

metric:
  source: metrics-ingest
  name: http.requests.rate
  labels:
    status: "5xx"

condition:
  operator: between
  threshold: [0.05, 1.0]   # alert if error rate 5%-100%
  time_window: 10m
  aggregation: avg
  evaluation_mode: window

severity:
  mapping:
    - threshold: 0.25
      level: critical
    - threshold: 0.05
      level: warning
  default_level: info

cooldown: 15m
notification:
  channels: [slack-ops, pagerduty-oncall]
  repeat_interval: 1h
```

## 3. Evaluation Engine Interface

### 3.1 Core Types (Python)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from datetime import datetime

class Operator(Enum):
    GT = "gt"; GTE = "gte"; LT = "lt"; LTE = "lte"
    EQ = "eq"; NEQ = "neq"; BETWEEN = "between"; OUTSIDE = "outside"

class Aggregation(Enum):
    AVG = "avg"; MIN = "min"; MAX = "max"; SUM = "sum"
    COUNT = "count"; P50 = "p50"; P95 = "p95"; P99 = "p99"

class SeverityLevel(Enum):
    CRITICAL = "critical"; WARNING = "warning"; INFO = "info"

class EvalMode(Enum):
    EACH = "each"; WINDOW = "window"

@dataclass
class MetricSpec:
    source: str
    name: str
    labels: dict[str, str] = field(default_factory=dict)

@dataclass
class Condition:
    operator: Operator
    threshold: float | list[float]
    time_window: str       # e.g. "5m"
    aggregation: Aggregation
    evaluation_mode: EvalMode

@dataclass
class SeverityMapping:
    threshold: float
    level: SeverityLevel

@dataclass
class Severity:
    mapping: list[SeverityMapping]
    default_level: SeverityLevel

@dataclass
class AlertRule:
    id: str
    name: str
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    metric: Optional[MetricSpec] = None
    condition: Optional[Condition] = None
    severity: Optional[Severity] = None
    cooldown: str = "5m"
    notification_channels: list[str] = field(default_factory=list)
    notification_repeat_interval: str = "1h"
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 3.2 Evaluation Engine ABC

```python
from abc import ABC, abstractmethod

@dataclass
class EvaluationInput:
    rule: AlertRule
    metric_values: list[tuple[datetime, float]]  # (timestamp, value) in window
    evaluated_at: datetime

@dataclass
class EvaluationResult:
    rule_id: str
    fired: bool
    severity: SeverityLevel
    current_value: float
    threshold: float | list[float]
    evaluated_at: datetime
    message: str = ""

class RuleEvaluator(ABC):
    @abstractmethod
    def evaluate(self, input: EvaluationInput) -> EvaluationResult: ...

    @abstractmethod
    def compare(self, value: float, operator: Operator,
                threshold: float | list[float]) -> bool: ...

    @abstractmethod
    def aggregate(self, values: list[float],
                  func: Aggregation) -> float: ...

    @abstractmethod
    def resolve_severity(self, value: float,
                         severity: Severity) -> SeverityLevel: ...
```

### 3.3 Evaluation Algorithm

```
evaluate(input):
    1. If rule.enabled is false → return fired=False
    2. Extract metric_values within rule.condition.time_window
    3. If evaluation_mode == "window":
         aggregated = aggregate(values, condition.aggregation)
         breached  = compare(aggregated, condition.operator, condition.threshold)
    4. If evaluation_mode == "each":
         breached  = any(compare(v, condition.operator, condition.threshold)
                         for v in values)
         aggregated = value that first breached (or last value)
    5. If breached:
         level = resolve_severity(aggregated, rule.severity)
         return fired=True, severity=level, current_value=aggregated
    6. Else:
         return fired=False, severity=default_level, current_value=aggregated
```

### 3.4 Severity Resolution

Walk `severity.mapping` in declaration order. First entry where `compare(value, condition.operator, entry.threshold)` is true wins. If none match, return `severity.default_level`.

## 4. Validation Rules

- `id` must be unique across all loaded rules.
- `condition.threshold` must be a `number` for scalar operators, `[number, number]` for `between`/`outside`.
- For `between`/`outside`, `threshold[0] < threshold[1]` must hold.
- `severity.mapping` entries must be ordered from highest to lowest severity (critical → warning → info).
- `time_window` must parse as a valid duration string.
- `cooldown` must be >= `time_window`.

## 5. JSON Schema (machine-validatable)

A companion `rule-schema.json` is provided alongside this spec for programmatic validation of rule YAML/JSON files.