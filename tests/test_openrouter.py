"""Driven entirely by contract/conformance/gateway-vectors.json, which every
SDK in every language reads.

Assertions written here instead would be a second copy of the truth, and this
SDK would slowly stop agreeing with the others. To add a case, edit the vector
file, not this test.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from marginfuse import from_openrouter

VECTORS = json.loads(
    (Path(__file__).resolve().parents[1] / "contract/conformance/gateway-vectors.json").read_text()
)
CASES = VECTORS["adapters"]["fromOpenRouter"]["cases"]

# camelCase on the wire and in the vectors; snake_case in this SDK.
WIRE_TO_PY = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cachedInputTokens": "cached_input_tokens",
    "cacheCreationTokens": "cache_creation_tokens",
    "images": "images",
    "audioSeconds": "audio_seconds",
}


def _usage_dict(result: dict[str, Any]) -> dict[str, Any]:
    """The usage fields the adapter actually set, in wire names."""
    produced = asdict(result["usage"])
    out = {}
    for wire, attr in WIRE_TO_PY.items():
        if produced[attr] is not None:
            out[wire] = produced[attr]
    return out


def _call(case: dict[str, Any]) -> dict[str, Any]:
    return from_openrouter() if case.get("omitInput") else from_openrouter(case["input"])


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_vector(case: dict[str, Any]) -> None:
    result = _call(case)
    assert _usage_dict(result) == case["expected"]["usage"]

    expected_cost = case["expected"].get("costUsd")
    if expected_cost is None:
        # Absent must mean absent, not present-and-zero: omitting the cost lets
        # MarginFuse price the call, where "0" would claim it was free.
        assert "cost_usd" not in result
    else:
        assert result["cost_usd"] == expected_cost


def test_never_produces_a_cost_the_api_would_reject() -> None:
    # The decimal-string pattern from the API's own schema. Exponent notation
    # is the failure this guards, and it is silent everywhere else.
    decimal = re.compile(r"^\d+(\.\d+)?$")
    for case in CASES:
        cost = _call(case).get("cost_usd")
        if cost is not None:
            assert decimal.match(cost), f"{case['name']}: {cost}"


def test_every_exported_adapter_has_vectors() -> None:
    # Adapters are a category, not a one-off: Bedrock, Vertex, Azure and
    # LiteLLM will each want one, and each will have its own version of the two
    # hazards the vector file documents.
    import marginfuse

    exported = [n for n in marginfuse.__all__ if n.startswith("from_")]
    assert exported
    # The vector file keys adapters by their TypeScript name; compare without
    # case so from_openrouter and fromOpenRouter are recognised as one adapter.
    known = {k.replace("_", "").lower() for k in VECTORS["adapters"]}
    for name in exported:
        assert name.replace("_", "").lower() in known, f"{name} has no vector suite"
