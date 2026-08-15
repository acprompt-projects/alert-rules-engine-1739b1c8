import logging
from typing import Any, Dict, List, Optional
from .channels import WebhookChannel, SlackChannel, PagerDutyChannel
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_CHANNEL_MAP = {
    "webhook": WebhookChannel,
    "slack": SlackChannel,
    "pagerduty": PagerDutyChannel,
}


class NotificationDispatcher:
    """Routes alerts to the channels configured on each rule."""

    def __init__(self):
        self._channels: Dict[str, Any] = {}

    def register(self, name: str, channel: Any) -> None:
        self._channels[name] = channel
        logger.info("Registered notification channel '%s' (%s)", name, channel.name)

    def register_from_config(self, channel_configs: List[Dict[str, Any]]) -> None:
        for cfg in channel_configs:
            ctype = cfg.get("type")
            cls = _CHANNEL_MAP.get(ctype)
            if cls is None:
                logger.error("Unknown channel type '%s'; skipping", ctype)
                continue
            cname = cfg["name"]
            rl_cfg = cfg.get("rate_limiter", {})
            rl = RateLimiter(**rl_cfg) if rl_cfg else None
            kwargs = {k: v for k, v in cfg.items() if k not in ("type", "name", "rate_limiter")}
            if rl is not None:
                kwargs["rate_limiter"] = rl
            self.register(cname, cls(**kwargs))

    def dispatch(self, alert: Dict[str, Any], rule: Dict[str, Any]) -> Dict[str, bool]:
        channel_names = rule.get("channels", [])
        results: Dict[str, bool] = {}
        for cname in channel_names:
            ch = self._channels.get(cname)
            if ch is None:
                logger.error("Channel '%s' not registered; skipping alert for rule '%s'",
                             cname, rule.get("name", "?"))
                results[cname] = False
                continue
            try:
                ok = ch.send(alert)
            except Exception as exc:
                logger.exception("Channel '%s' raised sending alert: %s", cname, exc)
                ok = False
            results[cname] = ok
            if ok:
                logger.info("Alert dispatched to '%s' for rule '%s'", cname, rule.get("name", "?"))
            else:
                logger.warning("Alert dispatch FAILED on '%s' for rule '%s'", cname, rule.get("name", "?"))
        return results