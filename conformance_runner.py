"""The Python conformance runner.

Reads one scenario as JSON on stdin, drives this SDK against the mock server
the driver started, and prints one JSON report on stdout. See
contract/harness/runners/README.md for the contract.

Exit non-zero only if the runner itself broke. An SDK misbehaving is a report
for the driver to judge, not a crash here.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any

from marginfuse import MarginFuse, ProviderCall, Usage

# The scenarios speak the wire's camelCase; this SDK speaks snake_case.
USAGE_KEYS = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cachedInputTokens": "cached_input_tokens",
    "cacheCreationTokens": "cache_creation_tokens",
    "images": "images",
    "audioSeconds": "audio_seconds",
}
PARAM_KEYS = {
    "customerId": "customer_id",
    "clearPlan": "clear_plan",
    "periodStart": "period_start",
    "eventId": "event_id",
    "requestedModel": "requested_model",
    "costUsd": "cost_usd",
    "decisionId": "decision_id",
    "expectedUsage": "expected_usage",
    "feature": "feature",
    "provider": "provider",
    "model": "model",
    "outcome": "outcome",
}


def usage_from(raw: Any) -> Usage:
    fields = {USAGE_KEYS[k]: v for k, v in (raw or {}).items() if k in USAGE_KEYS}
    return Usage(**fields)


def params_from(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "usage":
            out["usage"] = usage_from(value)
        elif key == "expectedUsage":
            out["expected_usage"] = usage_from(value)
        elif key in PARAM_KEYS:
            out[PARAM_KEYS[key]] = value
        else:
            out[key] = value
    return out


def main() -> None:
    scenario = json.loads(sys.stdin.read())
    provider_calls: list[dict[str, Any]] = []
    on_error_contexts: list[str] = []

    options = scenario.get("options") or {}
    kwargs: dict[str, Any] = {}
    if "timeoutMs" in options:
        kwargs["timeout"] = options["timeoutMs"] / 1000.0

    mf = MarginFuse(
        api_key=os.environ.get("MARGINFUSE_API_KEY", ""),
        base_url=os.environ.get("MARGINFUSE_BASE_URL", ""),
        on_error=lambda _err, context: on_error_contexts.append(context),
        **kwargs,
    )

    report: dict[str, Any] = {"outcome": "returned"}
    action = scenario["action"]
    params = params_from(scenario.get("params") or {})

    try:
        if action == "decide":
            decision = mf.decide(**params)
            report["result"] = {
                "id": decision.id,
                "action": decision.action,
                "model": decision.model,
                "provider": decision.provider,
                "topupContext": decision.topup_context,
                "degraded": decision.degraded,
                "degradedReason": decision.degraded_reason,
            }
        elif action == "track":
            mf.track(**params)
        elif action == "acknowledge":
            mf.acknowledge(params["decision_id"], params["acknowledgment"])
        elif action == "identify":
            # The one call that reports failure instead of failing open: a
            # wrong plan is a wrong margin, so the application must see it.
            if isinstance(params.get("period_start"), str):
                params["period_start"] = datetime.fromisoformat(
                    params["period_start"].replace("Z", "+00:00")
                )
            result = mf.identify(**params)
            report["result"] = {
                "ok": result.ok,
                "customerId": result.customer_id,
                "plan": result.plan,
                "periodStart": result.period_start,
                "periodEnd": result.period_end,
                "error": result.error,
            }
        elif action == "guard":
            spec = scenario.get("provider") or {}

            def run(decision: Any) -> ProviderCall:
                provider_calls.append({"model": decision.model, "provider": decision.provider})
                if spec.get("throws"):
                    raise RuntimeError("provider exploded")
                return ProviderCall(result="ok", usage=usage_from(spec.get("usage")))

            out = mf.guard(run, **params)
            # Only the discriminant and the decision travel; `result` is the
            # application's own value and means nothing to another language.
            report["result"] = {
                "kind": out.kind,
                "decision": {
                    "id": out.decision.id,
                    "action": out.decision.action,
                    "model": out.decision.model,
                    "provider": out.decision.provider,
                    "degraded": out.decision.degraded,
                },
            }
        else:
            raise SystemExit(f"unknown action {action}")
    except BaseException as err:
        report["outcome"] = "threw"
        report["threw"] = str(err)

    # Always flush, including after a raise: the driver asserts on what the SDK
    # sent, and guard() records the attempt before it re-raises.
    mf.flush()

    report["providerCalls"] = provider_calls
    report["onErrorContexts"] = on_error_contexts
    sys.stdout.write(json.dumps(report) + "\n")


if __name__ == "__main__":
    main()
