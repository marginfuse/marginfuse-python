"""OpenRouter helper.

OpenRouter returns a ``usage`` object on every response, and that object
carries the provider-final ``cost``. Forwarding it is what makes an OpenRouter
integration exact rather than estimated: MarginFuse cannot know what a gateway
charged, because routing, fees and BYOK terms are not visible in a usage event.

Two details this helper exists to get right, both of which silently misstate
margin when hand-rolled:

1. ``prompt_tokens`` is the TOTAL input count. Cached reads and cache writes
   are already inside it. MarginFuse prices input, cached input and cache
   creation as three separate charges and adds them up, so passing
   ``prompt_tokens`` straight through double-counts every cached token, at the
   full uncached rate.
2. ``cost`` is a float, and ``str()`` renders small ones in exponent notation
   ("1.2e-07"), which the API rejects as a decimal string.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal
from typing import Any, Optional

from ._types import Usage

__all__ = ["from_openrouter"]

_NANO = Decimal("0.000000001")


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if not math.isfinite(value):
        return 0
    return round(value) if value > 0 else 0


def _credits_to_usd(cost: float) -> str:
    """OpenRouter credits (1 credit = 1 USD) as a decimal string the API takes.

    Fixed point to nano precision: ``str()`` emits exponent notation for the
    small costs cheap models produce, and money below a nano cannot be
    represented at all, so it rounds down rather than pretending otherwise.
    """
    quantized = Decimal(str(cost)).quantize(_NANO, rounding=ROUND_DOWN)
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def from_openrouter(usage: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Map an OpenRouter ``usage`` object to MarginFuse keyword arguments.

        r = client.chat.completions.create(model=model, messages=messages)
        mf.track(customer_id=cid, provider="openrouter", model=model,
                 **from_openrouter(r.usage))

    ``cost_usd`` is omitted when the response carried no cost, which lets the
    event fall through to MarginFuse's own pricing instead of claiming a $0
    charge.
    """
    source: Mapping[str, Any] = usage or {}
    details = source.get("prompt_tokens_details") or {}
    if not isinstance(details, Mapping):
        details = {}

    cached = _int(details.get("cached_tokens"))
    cache_writes = _int(details.get("cache_write_tokens"))
    # Cached reads and writes are already inside prompt_tokens; what is left is
    # what was billed at the full input rate. Clamped at zero so a provider
    # reporting these differently degrades to "no fresh input" rather than a
    # negative charge.
    fresh = max(0, _int(source.get("prompt_tokens")) - cached - cache_writes)
    completion = _int(source.get("completion_tokens"))

    out: dict[str, Any] = {
        "usage": Usage(
            input_tokens=fresh or None,
            output_tokens=completion or None,
            cached_input_tokens=cached or None,
            cache_creation_tokens=cache_writes or None,
        )
    }

    cost = source.get("cost")
    # bool is an int in Python, and NaN or infinity are not money.
    if (
        isinstance(cost, (int, float))
        and not isinstance(cost, bool)
        and math.isfinite(cost)
        and cost >= 0
    ):
        out["cost_usd"] = _credits_to_usd(float(cost))
    return out
