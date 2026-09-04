"""guard() has to report the call that actually ran.

A downgrade can cross vendors: the server can answer an OpenAI request with an
Anthropic model. Everything guard() then reports - the vendor the event is
priced from, the acknowledgment of what the application did - describes the
model that ran rather than the one that was asked for, and a provider call that
throws afterwards does not change what ran.

The transport is stubbed rather than the socket, so these assert on the payloads
this SDK actually puts on the wire.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from marginfuse import MarginFuse, ProviderCall, Usage
from marginfuse._client import _Response


class _Transport:
    """Answers the decision call with the verdict a test is about, accepts
    everything else, and keeps every request for the assertions."""

    def __init__(self, decision: dict[str, Any]) -> None:
        self._decision = decision
        self.posts: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, path: str, body: dict[str, Any], timeout: float) -> _Response:
        self.posts.append((path, body))
        payload = self._decision if path == "/v1/decisions" else {}
        return _Response(200, json.dumps(payload).encode("utf-8"))

    def event(self) -> dict[str, Any]:
        for path, body in self.posts:
            if path == "/v1/events":
                first: dict[str, Any] = body["events"][0]
                return first
        raise AssertionError("guard() sent no event")

    def acknowledgment(self) -> str:
        for path, body in self.posts:
            if path.endswith("/ack"):
                return str(body["acknowledgment"])
        raise AssertionError("guard() sent no acknowledgment")


def _client(
    monkeypatch: pytest.MonkeyPatch, decision: dict[str, Any]
) -> tuple[MarginFuse, _Transport]:
    mf = MarginFuse(api_key="mf_test", base_url="https://marginfuse.invalid")
    transport = _Transport(decision)
    monkeypatch.setattr(mf, "_post", transport)
    return mf, transport


def _succeeds(_decision: Any) -> ProviderCall:
    return ProviderCall(result="ok", usage=Usage(input_tokens=900, output_tokens=40))


def _throws(_decision: Any) -> ProviderCall:
    raise RuntimeError("provider exploded")


DOWNGRADE_ACROSS_VENDORS = {
    "id": "dec_7k2",
    "action": "downgrade",
    "model": "claude-haiku-4-5",
    "provider": "anthropic",
}
# The ordinary case: the server names no provider, so the decision keeps the
# caller's and nothing about the reported call moves.
ALLOW = {"id": "dec_7k3", "action": "allow"}


def test_a_cross_provider_downgrade_is_billed_to_the_vendor_that_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mf, transport = _client(monkeypatch, DOWNGRADE_ACROSS_VENDORS)

    mf.guard(_succeeds, customer_id="user_8x2m91", provider="openai", model="gpt-5")
    mf.flush()

    event = transport.event()
    assert event["provider"] == "anthropic"
    assert event["model"] == "claude-haiku-4-5"
    # What was asked for still rides along; it is the basis the saving is
    # measured against.
    assert event["requestedModel"] == "gpt-5"
    assert transport.acknowledgment() == "used_downgrade_model"


def test_anything_but_a_downgrade_still_reports_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mf, transport = _client(monkeypatch, ALLOW)

    mf.guard(_succeeds, customer_id="user_8x2m91", provider="openai", model="gpt-5")
    mf.flush()

    event = transport.event()
    assert event["provider"] == "openai"
    assert event["model"] == "gpt-5"
    assert transport.acknowledgment() == "proceeded_as_requested"


def test_a_downgrade_that_then_fails_is_still_a_downgrade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mf, transport = _client(monkeypatch, DOWNGRADE_ACROSS_VENDORS)

    with pytest.raises(RuntimeError) as raised:
        mf.guard(_throws, customer_id="user_8x2m91", provider="openai", model="gpt-5")
    # The application's own error, unchanged: guard() records the attempt and
    # then gets out of the way.
    assert str(raised.value) == "provider exploded"
    mf.flush()

    assert transport.acknowledgment() == "used_downgrade_model"
    event = transport.event()
    assert event["outcome"] == "provider_error"
    assert event["provider"] == "anthropic"
    assert event["model"] == "claude-haiku-4-5"


def test_a_failure_that_was_not_downgraded_acknowledges_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mf, transport = _client(monkeypatch, ALLOW)

    with pytest.raises(RuntimeError):
        mf.guard(_throws, customer_id="user_8x2m91", provider="openai", model="gpt-5")
    mf.flush()

    assert transport.acknowledgment() == "proceeded_as_requested"
    assert transport.event()["provider"] == "openai"
