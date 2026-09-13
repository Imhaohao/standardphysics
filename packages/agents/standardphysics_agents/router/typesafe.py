"""TypeSafe picks the next action, and its answer drives real control flow.

The request carries the schema generated from `Decision` and a summary of the
findings. The response is handed straight to `parse_decision`, so nothing the
service returns reaches a branch without being validated first, including a
transport failure: that comes back as `Rejected` rather than as an exception,
because a service being down must not be able to authorize anything either.

`base_url` and `path` are settable because the event's quickstart is the source
of truth for them, and a person collects that in the first hour along with the
key. Point them at the quickstart's endpoint and nothing else changes.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from standardphysics_contracts import Decision, Finding

from ..tracing import traced
from .decision import Rejected, action_schema, parse_decision
from .state import RouterState

API_KEY_ENV = "TYPESAFE_API_KEY"
BASE_URL_ENV = "TYPESAFE_BASE_URL"
MODEL_ENV = "TYPESAFE_MODEL"

DEFAULT_PATH = "/v1/structured"
DEFAULT_TIMEOUT_SECONDS = 20.0

PROVIDER = "typesafe"

INSTRUCTION = (
    "You are choosing the next step for an accessibility review of a small shop. "
    "Pick exactly one action. FIX moves furniture and may only target problems "
    "where furniture_can_fix is true. RESCAN_AREA asks for a short follow-up "
    "scan and may only target findings where wants_another_look is true. "
    "ASK_OWNER needs one specific question. ESCALATE queues a problem for a "
    "professional. DONE ends the review. Name every finding you act on."
)

RESPONSE_PATHS = (
    ("data",),
    ("output",),
    ("result",),
    ("choices", 0, "message", "content"),
)
"""Where a structured answer tends to sit in a response envelope.

Checked in order, and the whole body is used when none of them match, so a
service that returns the object at the top level works without configuration.
"""


class Transport(Protocol):
    def post(self, url: str, body: bytes, headers: dict[str, str]) -> bytes: ...


class UrllibTransport:
    """The standard library, so no lane inherits an HTTP dependency."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout = timeout

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> bytes:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()


def extract_payload(body: Any) -> Any:
    """Reach past a response envelope to the structured object inside it."""
    if isinstance(body, (str, bytes)):
        body = _load(body)
    if not isinstance(body, dict):
        return body
    for path in RESPONSE_PATHS:
        found = _walk(body, path)
        if found is not None:
            return found
    return body


def _load(raw: str | bytes) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw


def _walk(body: Any, path: tuple) -> Any:
    current = body
    for step in path:
        if isinstance(step, int) and isinstance(current, list) and len(current) > step:
            current = current[step]
        elif isinstance(current, dict) and step in current:
            current = current[step]
        else:
            return None
    return current


class TypeSafeRouter:
    provider = PROVIDER

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        path: str = DEFAULT_PATH,
        model: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get(API_KEY_ENV)
        self.base_url = (base_url or os.environ.get(BASE_URL_ENV) or "").rstrip("/")
        self.path = path
        self.model = model or os.environ.get(MODEL_ENV)
        self.transport = transport or UrllibTransport()

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def request_body(self, state: RouterState) -> dict:
        body = {
            "instruction": INSTRUCTION,
            "schema": action_schema(),
            "input": state.summary(),
        }
        if self.model:
            body["model"] = self.model
        return body

    @traced("router.typesafe")
    def decide(self, state: RouterState) -> Decision | Rejected:
        if not self.configured:
            return Rejected("typesafe_not_configured")
        raw = self._call(self.request_body(state))
        if isinstance(raw, Rejected):
            return raw
        decision = parse_decision(extract_payload(raw), state.findings, PROVIDER)
        if isinstance(decision, Rejected):
            return decision
        return _authorize(decision, state)

    def _call(self, body: dict) -> bytes | Rejected:
        try:
            return self.transport.post(
                f"{self.base_url}{self.path}",
                json.dumps(body).encode("utf-8"),
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
            return Rejected("transport_error")


def _authorize(decision: Decision, state: RouterState) -> Decision | Rejected:
    """The schema is not enough: the action still has to name something it may act on."""
    targets = set(decision.target_finding_ids)
    if decision.action == "FIX":
        return _authorize_fix(decision, state, targets)
    if decision.action == "RESCAN_AREA" and not targets <= set(state.rescan_finding_ids):
        return Rejected("rescan_targets_measured_finding")
    if decision.action == "ESCALATE" and not targets <= {f.id for f in state.problems}:
        return Rejected("escalate_targets_nonproblem")
    return decision


def _authorize_fix(
    decision: Decision, state: RouterState, targets: set
) -> Decision | Rejected:
    if not state.fix_budget_left:
        return Rejected("fix_budget_exhausted")
    if not targets <= set(state.fixable_finding_ids):
        return Rejected("fix_targets_unfixable_finding")
    return decision
