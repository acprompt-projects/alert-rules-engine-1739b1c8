"""End-to-end integration tests for alert-rules-engine.

Covers: rule CRUD, metric ingestion → rule evaluation → alert creation,
and notification dispatch to Slack/PagerDuty webhooks.
"""

import time
import uuid

import pytest


def _make_rule(metric_name="cpu_percent", threshold=90.0, comparator="gt",
               channel="slack", severity="critical"):
    return {
        "id": str(uuid.uuid4())[:8],
        "name": f"alert-{uuid.uuid4())[:6]}",
        "metric": metric_name,
        "threshold": threshold,
        "comparator": comparator,
        "channel": channel,
        "severity": severity,
        "enabled": True,
    }


# ── API CRUD ──────────────────────────────────────────────────────────────

class TestRuleCRUD:
    def test_create_and_get_rule(self, api_client):
        rule = _make_rule()
        resp = api_client.create_rule(rule)
        assert resp.status_code == 201
        got = api_client.get_rule(rule["id"])
        assert got.status_code == 200
        assert got.json()["threshold"] == rule["threshold"]

    def test_list_rules(self, api_client):
        api_client.create_rule(_make_rule())
        resp = api_client.list_rules()
        assert resp.status_code == 200
        assert isinstance(resp.json(), list) and len(resp.json()) >= 1

    def test_update_rule(self, api_client):
        rule = _make_rule()
        api_client.create_rule(rule)
        resp = api_client.update_rule(rule["id"], {**rule, "threshold": 95.0})
        assert resp.status_code == 200
        assert api_client.get_rule(rule["id"]).json()["threshold"] == 95.0

    def test_delete_rule(self, api_client):
        rule = _make_rule()
        api_client.create_rule(rule)
        assert api_client.delete_rule(rule["id"]).status_code == 204
        assert api_client.get_rule(rule["id"]).status_code == 404


# ── Rule Evaluation & Alert Triggering ────────────────────────────────────

class TestRuleEvaluation:
    def test_metric_triggers_alert(self, api_client):
        rule = _make_rule(metric_name="mem_pct", threshold=85.0, comparator="gt")
        api_client.create_rule(rule)
        resp = api_client.ingest_metric({"name": "mem_pct", "value": 92.3,
                                         "host": "web-01"})
        assert resp.status_code == 202
        alerts = api_client.alerts().json()
        matched = [a for a in alerts if a["rule_id"] == rule["id"]]
        assert len(matched) >= 1
        assert matched[0]["severity"] == "critical"

    def test_metric_below_threshold_no_alert(self, api_client):
        rule = _make_rule(metric_name="disk_pct", threshold=90.0, comparator="gt")
        api_client.create_rule(rule)
        api_client.ingest_metric({"name": "disk_pct", "value": 45.0,
                                  "host": "web-02"})
        alerts = api_client.alerts().json()
        assert not any(a["rule_id"] == rule["id"] for a in alerts)

    def test_comparator_lt(self, api_client):
        rule = _make_rule(metric_name="free_mem", threshold=10.0, comparator="lt",
                          channel="pagerduty")
        api_client.create_rule(rule)
        api_client.ingest_metric({"name": "free_mem", "value": 3.2,
                                  "host": "db-01"})
        alerts = api_client.alerts().json()
        assert any(a["rule_id"] == rule["id"] for a in alerts)

    def test_disabled_rule_skipped(self, api_client):
        rule = _make_rule()
        rule["enabled"] = False
        api_client.create_rule(rule)
        api_client.ingest_metric({"name": rule["metric"], "value": 99.0,
                                  "host": "x"})
        alerts = api_client.alerts().json()
        assert not any(a["rule_id"] == rule["id"] for a in alerts)


# ── Notification Dispatch ─────────────────────────────────────────────────

class TestNotificationDispatch:
    def test_slack_webhook_dispatched(self, api_client, mock_webhook_server,
                                     webhook_calls):
        port = mock_webhook_server
        rule = _make_rule(channel="slack")
        rule["webhook_url"] = f"http://127.0.0.1:{port}/slack"
        api_client.create_rule(rule)
        api_client.ingest_metric({"name": rule["metric"], "value": 95.0,
                                  "host": "web-01"})
        time.sleep(0.5)  # allow async dispatch
        slack_calls = [c for c in webhook_calls if "/slack" in c["path"]]
        assert len(slack_calls) >= 1
        assert "text" in slack_calls[0]["body"] or "blocks" in slack_calls[0]["body"]

    def test_pagerduty_webhook_dispatched(self, api_client, mock_webhook_server,
                                         webhook_calls):
        port = mock_webhook_server
        rule = _make_rule(channel="pagerduty")
        rule["webhook_url"] = f"http://127.0.0.1:{port}/pagerduty"
        api_client.create_rule(rule)
        api_client.ingest_metric({"name": rule["metric"], "value": 95.0,
                                  "host": "db-01"})
        time.sleep(0.5)
        pd_calls = [c for c in webhook_calls if "/pagerduty" in c["path"]]
        assert len(pd_calls) >= 1
        assert "event_type" in pd_calls[0]["body"] or "routing_key" in pd_calls[0]["body"]