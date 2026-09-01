"""The exported contract version has to be the one this build was actually
verified against, or it is a claim rather than a fact."""

from __future__ import annotations

import json
from pathlib import Path

from marginfuse import CONTRACT_VERSION


def test_matches_the_pinned_contract() -> None:
    pinned = json.loads(
        (
            Path(__file__).resolve().parents[1] / "contract/conformance/behavior-scenarios.json"
        ).read_text()
    )
    assert pinned["version"] == CONTRACT_VERSION
