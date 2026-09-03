"""The public types have to survive being introspected.

Annotations are strings under ``from __future__ import annotations``, so a
PEP 604 union imports fine on Python 3.9 and then fails the moment anything
resolves it: FastAPI, Pydantic, any dataclass serializer, typing.get_type_hints
itself. This package claims 3.9, so this pins that claim.
"""

from __future__ import annotations

import typing

import marginfuse
from marginfuse import Decision, GuardOutcome, IdentifyResult, ProviderCall, Usage


def test_public_types_resolve() -> None:
    for target in (Usage, Decision, ProviderCall, GuardOutcome, IdentifyResult):
        assert typing.get_type_hints(target)


def test_client_signatures_resolve() -> None:
    for name in ("decide", "track", "guard", "acknowledge", "identify", "flush"):
        assert typing.get_type_hints(getattr(marginfuse.MarginFuse, name)) is not None


def test_no_field_can_carry_content() -> None:
    # The privacy claim as a test rather than a promise. If a future change
    # adds somewhere for message content to live, this is what notices.
    banned = {
        "prompt",
        "prompts",
        "message",
        "messages",
        "content",
        "contents",
        "text",
        "input",
        "inputs",
        "output",
        "outputs",
        "completion",
        "completions",
        "response",
        "responses",
        "body",
        "document",
        "documents",
    }
    for target in (Usage, Decision, ProviderCall, IdentifyResult):
        for field in typing.get_type_hints(target):
            assert field.lower() not in banned, f"{target.__name__}.{field}"
