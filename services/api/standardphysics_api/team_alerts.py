"""A message to the team, sent where deploy/digitalocean/monitor.sh sends its alerts.

SP_ALERT_WEBHOOK takes the same two kinds of address monitor.sh does: an ntfy topic gets the message as plain text
with a Title header, so the ntfy app shows it as a push, and anything else gets a JSON POST of {"text": ...}, which
a Slack incoming webhook accepts. Keep the two in step.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from .settings import Settings

log = logging.getLogger(__name__)

ALERT_TIMEOUT_SECONDS = 10.0


def _sends_to_ntfy(settings: Settings, webhook: str) -> bool:
    if settings.team_alert_format:
        return settings.team_alert_format == "ntfy"
    return webhook.startswith("https://ntfy.sh/")


def _request(settings: Settings, webhook: str, title: str, message: str) -> urllib.request.Request:
    if _sends_to_ntfy(settings, webhook):
        return urllib.request.Request(webhook, data=message.encode(), method="POST", headers={"Title": title})
    body = json.dumps({"text": f"{title}\n{message}"}).encode()
    return urllib.request.Request(webhook, data=body, method="POST", headers={"Content-Type": "application/json"})


def send_team_alert(settings: Settings, title: str, message: str) -> None:
    """Tell the team, or do nothing when no webhook is set. It never raises: what it reports has already happened,
    so an alert that can't be delivered is logged and dropped."""
    webhook = settings.team_alert_webhook
    if not webhook:
        return
    try:
        with urllib.request.urlopen(_request(settings, webhook, title, message), timeout=ALERT_TIMEOUT_SECONDS):
            pass
    except (OSError, ValueError) as error:
        log.warning("the team alert %r was not delivered: %s", title, error)
