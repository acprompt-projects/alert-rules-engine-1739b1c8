import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

DEFAULT_RETRY = 3
DEFAULT_BACKOFF = 1.0


def _http_post(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float = 10.0) -> int:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def _post_with_retry(url: str, payload: Dict[str, Any], headers: Dict[str, str],
                     retries: int = DEFAULT_RETRY, backoff: float = DEFAULT_BACKOFF) -> bool:
    for attempt in range(retries):
        try:
            status = _http_post(url, payload, headers)
            if 200 <= status < 300:
                return True
            logger.warning("POST %s returned %d (attempt %d)", url, status, attempt + 1)
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("POST %s failed: %s (attempt %d)", url, exc, attempt + 1)
        if attempt < retries - 1:
            time.sleep(backoff * (2 ** attempt))
    return False


class WebhookChannel:
    name = "webhook"

    def __init__(self, url: str, retries: int = DEFAULT_RETRY, backoff: float = DEFAULT_BACKOFF,
                 rate_limiter: Optional[RateLimiter] = None, headers: Optional[Dict[str, str]] = None):
        self.url = url
        self.retries = retries
        self.backoff = backoff
        self.rate_limiter = rate_limiter or RateLimiter()
        self.headers = headers or {}

    def send(self, alert: Dict[str, Any]) -> bool:
        if not self.rate_limiter.allow():
            logger.warning("Rate limited for webhook %s", self.url)
            return False
        return _post_with_retry(self.url, alert, self.headers, self.retries, self.backoff)


class SlackChannel:
    name = "slack"

    def __init__(self, webhook_url: str, retries: int = DEFAULT_RETRY, backoff: float = DEFAULT_BACKOFF,
                 rate_limiter: Optional[RateLimiter] = None):
        self.webhook_url = webhook_url
        self.retries = retries
        self.backoff = backoff
        self.rate_limiter = rate_limiter or RateLimiter(max_tokens=5, refill_period=60.0)

    def send(self, alert: Dict[str, Any]) -> bool:
        if not self.rate_limiter.allow():
            logger.warning("Rate limited for Slack %s", self.webhook_url)
            return False
        severity = alert.get("severity", "warning").upper()
        payload = {
            "text": f":rotating_light: *[{severity}] {alert.get('rule_name','unknown')}* — {alert.get('message','')}",
            "attachments": [{"fields": [{"title": k, "value": str(v), "short": True} for k, v in alert.items() if k not in ("rule_name", "message")]}],
        }
        return _post_with_retry(self.webhook_url, payload, {}, self.retries, self.backoff)


class PagerDutyChannel:
    name = "pagerduty"

    def __init__(self, routing_key: str, retries: int = DEFAULT_RETRY, backoff: float = DEFAULT_BACKOFF,
                 rate_limiter: Optional[RateLimiter] = None):
        self.routing_key = routing_key
        self.retries = retries
        self.backoff = backoff
        self.rate_limiter = rate_limiter or RateLimiter(max_tokens=10, refill_period=60.0)
        self._url = "https://events.pagerduty.com/v2/enqueue"

    def send(self, alert: Dict[str, Any]) -> bool:
        if not self.rate_limiter.allow():
            logger.warning("Rate limited for PagerDuty routing_key %s", self.routing_key[:8])
            return False
        severity_map = {"critical": "critical", "warning": "warning", "info": "info"}
        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": f"{alert.get('rule_name','unknown')}: {alert.get('message','')}",
                "severity": severity_map.get(alert.get("severity", "warning"), "warning"),
                "source": alert.get("source", "alert-rules-engine"),
                "component": alert.get("component", ""),
                "custom_details": {k: v for k, v in alert.items() if k not in ("rule_name", "message", "severity", "source", "component")},
            },
        }
        return _post_with_retry(self._url, payload, {}, self.retries, self.backoff)