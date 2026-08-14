from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import FastAPI, HTTPException, status
from fastapi.exception_handlers import http_exception_handler

from .models import (
    AlertRule, AlertRuleUpdate, ChannelType, DryRunRequest, DryRunResult, ErrorResponse, Severity,
)

app = FastAPI(title="Alert Rules Engine API", version="1.0.0")

_rules_store: Dict[str, AlertRule] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@app.get("/rules", response_model=List[AlertRule], summary="List all alert rules")
async def list_rules(enabled: bool = None, severity: Severity = None):
    rules = list(_rules_store.values())
    if enabled is not None:
        rules = [r for r in rules if r.enabled == enabled]
    if severity is not None:
        rules = [r for r in rules if r.severity == severity]
    return rules


@app.get("/rules/{rule_id}", response_model=AlertRule, summary="Get a single rule")
async def get_rule(rule_id: str):
    rule = _rules_store.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return rule


@app.post("/rules", response_model=AlertRule, status_code=status.HTTP_201_CREATED, summary="Create a rule")
async def create_rule(rule: AlertRule):
    rule.id = str(uuid.uuid4())
    rule.created_at = _now()
    rule.updated_at = rule.created_at
    _rules_store[rule.id] = rule
    return rule


@app.put("/rules/{rule_id}", response_model=AlertRule, summary="Update a rule")
async def update_rule(rule_id: str, patch: AlertRuleUpdate):
    existing = _rules_store.get(rule_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    update_data = patch.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(existing, field, value)
    try:
        existing.model_validate(existing.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Validation error: {exc}")
    existing.updated_at = _now()
    return existing


@app.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a rule")
async def delete_rule(rule_id: str):
    if rule_id not in _rules_store:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    del _rules_store[rule_id]


@app.post("/rules/dry-run", response_model=DryRunResult, summary="Dry-run evaluate a rule against sample data")
async def dry_run(req: DryRunRequest):
    triggering = [v for v in req.sample_values if req.rule.condition.evaluate(v)]
    return DryRunResult(triggered=len(triggering) > 0, triggering_values=triggering, rule=req.rule)


@app.post("/rules/{rule_id}/test", response_model=DryRunResult, summary="Test a stored rule against sample data")
async def test_rule(rule_id: str, sample_values: List[float]):
    rule = _rules_store.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    triggering = [v for v in sample_values if rule.condition.evaluate(v)]
    return DryRunResult(triggered=len(triggering) > 0, triggering_values=triggering, rule=rule)