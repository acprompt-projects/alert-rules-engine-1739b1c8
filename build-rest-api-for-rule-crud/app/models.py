from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class Operator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ChannelType(str, Enum):
    SLACK = "slack"
    PAGERDUTY = "pagerduty"


class ChannelConfig(BaseModel):
    type: ChannelType
    endpoint: str = Field(..., min_length=1, description="Webhook URL or routing key")

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("endpoint must be a valid HTTP(S) URL")
        return v


class Condition(BaseModel):
    operator: Operator
    threshold: float

    def evaluate(self, value: float) -> bool:
        ops = {
            Operator.GT: lambda v, t: v > t,
            Operator.GTE: lambda v, t: v >= t,
            Operator.LT: lambda v, t: v < t,
            Operator.LTE: lambda v, t: v <= t,
            Operator.EQ: lambda v, t: v == t,
            Operator.NEQ: lambda v, t: v != t,
        }
        return ops[self.operator](value, self.threshold)


class AlertRule(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=255)
    metric: str = Field(..., min_length=1, description="Metric path e.g. cpu.utilization")
    condition: Condition
    window_seconds: int = Field(60, gt=0, le=86400)
    severity: Severity = Severity.WARNING
    channels: List[ChannelConfig] = Field(default_factory=list, min_length=1)
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) < 2 or any(not p for p in parts):
            raise ValueError("metric must be dot-separated with ≥2 segments (e.g. cpu.utilization)")
        return v

    @model_validator(mode="after")
    def validate_schema(self) -> "AlertRule":
        if self.severity == Severity.CRITICAL and not any(
            c.type == ChannelType.PAGERDUTY for c in self.channels
        ):
            raise ValueError("critical rules must include a pagerduty channel")
        return self


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    metric: Optional[str] = None
    condition: Optional[Condition] = None
    window_seconds: Optional[int] = Field(None, gt=0, le=86400)
    severity: Optional[Severity] = None
    channels: Optional[List[ChannelConfig]] = None
    enabled: Optional[bool] = None


class DryRunRequest(BaseModel):
    rule: AlertRule
    sample_values: List[float] = Field(..., min_length=1, description="Metric values to test")


class DryRunResult(BaseModel):
    triggered: bool
    triggering_values: List[float]
    rule: AlertRule


class ErrorResponse(BaseModel):
    detail: str