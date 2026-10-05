"""Best-effort Slack alerts via an incoming webhook. Failures never affect the request."""

import logging

import httpx

log = logging.getLogger(__name__)


def notify(settings, text):
    url = settings.slack_webhook_url.get_secret_value()
    if not url:
        return
    try:
        httpx.post(url, json={"text": text[:3000]}, timeout=5).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Slack notification failed: %s", type(exc).__name__)
