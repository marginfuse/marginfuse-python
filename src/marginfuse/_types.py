"""Wire types for the MarginFuse SDK.

Deliberately: there is NO field for prompt text, responses, or documents. The
SDK cannot leak what it has nowhere to carry.

Names are snake_case here and camelCase on the wire. The mapping lives in
_client.py so nothing else has to think about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Outcome = Literal["success", "provider_error", "app_cancelled", "timeout"]

DecisionAction = Literal["allow", "downgrade", "topup_required", "block"]

Acknowledgment = Literal[
    "proceeded_as_requested",
    "used_downgrade_model",
    "presented_topup",
    "blocked_before_provider_call",
    "failed_to_apply",
]


@dataclass(frozen=True)
class Usage:
    """What a provider call consumed. Every field is optional: report what you
    have, and MarginFuse prices what it can rather than assuming a zero."""

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    cache_creation_tokens: Optional[int] = None
    images: Optional[int] = None
    audio_seconds: Optional[float] = None


@dataclass(frozen=True)
class Decision:
    """A verdict. Enforce on ``action`` alone.

    ``degraded`` is True when MarginFuse could not reach a verdict and the
    request was allowed through unprotected. ``id`` is absent in that case,
    which is why enforcement must never depend on it.
    """

    action: DecisionAction
    model: str
    provider: str
    degraded: bool = False
    id: Optional[str] = None
    topup_context: Optional[str] = None
    degraded_reason: Optional[str] = None


@dataclass(frozen=True)
class GuardOutcome:
    """What guard() did.

    ``kind`` is "completed", "blocked" or "topup_required". ``result`` is your
    own callback's return value and is only present when completed.
    """

    kind: Literal["completed", "blocked", "topup_required"]
    decision: Decision
    result: object = None


@dataclass(frozen=True)
class ProviderCall:
    """What your callback did, handed back to guard() so it can be reported.

    ``cost_usd`` is a decimal string, not a float: money that round-trips
    through a float stops being the number the provider charged.
    """

    usage: Usage
    result: object = None
    cost_usd: Optional[str] = None
    outcome: Outcome = "success"
