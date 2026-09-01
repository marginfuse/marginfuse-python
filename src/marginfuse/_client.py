"""MarginFuse Python SDK.

Reliability contract: this SDK NEVER raises into application code and NEVER
blocks a request on MarginFuse availability. decide() fails open to "allow" on
any timeout or error; track() and acknowledge() retry on a background thread
and surface problems only through ``on_error``.

Zero dependencies, standard library only, so it installs into any environment
without pulling a transitive tree behind it.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ._types import (
    Acknowledgment,
    Decision,
    GuardOutcome,
    Outcome,
    ProviderCall,
    Usage,
)

__all__ = ["MarginFuse"]

DEFAULT_BASE_URL = "https://api.marginfuse.com"
DEFAULT_TIMEOUT = 1.5
TRACK_RETRIES = 3
USER_AGENT = "marginfuse-python/0.1.0"

_USAGE_WIRE = {
    "input_tokens": "inputTokens",
    "output_tokens": "outputTokens",
    "cached_input_tokens": "cachedInputTokens",
    "cache_creation_tokens": "cacheCreationTokens",
    "images": "images",
    "audio_seconds": "audioSeconds",
}


def _usage_payload(usage: Optional[Usage]) -> dict[str, Any]:
    if usage is None:
        return {}
    out: dict[str, Any] = {}
    for attr, wire in _USAGE_WIRE.items():
        value = getattr(usage, attr)
        if value is not None:
            out[wire] = value
    return out


def _drop_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if v is not None}


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def json(self) -> Any:
        return json.loads(self._body.decode("utf-8"))

    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")[:200]


class MarginFuse:
    """The client.

    Args:
        api_key: Your project API key. Required.
        base_url: Point at your own deployment in development.
        timeout: Seconds decide() waits before failing open. Default 1.5.
        on_error: Called with (error, context) for transport failures the SDK
            swallowed. Without it, they are silent by design: this SDK is in
            your request path and must not become your outage.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        on_error: Optional[Callable[[BaseException, str], None]] = None,
    ) -> None:
        if not api_key:
            raise ValueError("MarginFuse: api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._on_error = on_error
        # One worker: events for a project are cheap and ordering them costs
        # nothing, while an unbounded pool would let a slow network spawn
        # threads inside somebody else's web worker.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="marginfuse")
        self._pending: list[Future[None]] = []
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- public

    def decide(
        self,
        *,
        customer_id: str,
        provider: str,
        model: str,
        feature: Optional[str] = None,
        expected_usage: Optional[Usage] = None,
    ) -> Decision:
        """Ask whether the next call should run. Always returns.

        On any timeout or error this returns ``action="allow"`` with
        ``degraded=True``: MarginFuse being unreachable must never become your
        outage.
        """
        payload = _drop_none(
            {
                "customerId": customer_id,
                "feature": feature,
                "provider": provider,
                "model": model,
                "expectedUsage": _usage_payload(expected_usage) if expected_usage else None,
            }
        )
        try:
            res = self._post("/v1/decisions", payload, self._timeout)
            if res.status < 200 or res.status >= 300:
                self._report(RuntimeError(f"decide: HTTP {res.status}"), "decide")
                return self._fail_open(provider, model, f"server responded {res.status}")
            body = res.json()
            return Decision(
                id=body.get("id"),
                action=body.get("action", "allow"),
                model=body.get("model") or model,
                provider=body.get("provider") or provider,
                topup_context=body.get("topupContext"),
                degraded=bool(body.get("degraded", False)),
                degraded_reason=body.get("degradedReason"),
            )
        except TimeoutError as err:
            self._report(err, "decide")
            return self._fail_open(provider, model, "timeout")
        except Exception as err:
            self._report(err, "decide")
            return self._fail_open(provider, model, "unreachable")

    def track(
        self,
        *,
        customer_id: str,
        provider: str,
        model: str,
        usage: Optional[Usage] = None,
        feature: Optional[str] = None,
        requested_model: Optional[str] = None,
        cost_usd: Optional[str] = None,
        event_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        outcome: Outcome = "success",
        decision_id: Optional[str] = None,
        retry_of_event_id: Optional[str] = None,
        corrects_event_id: Optional[str] = None,
    ) -> None:
        """Report an AI call that already happened. Returns immediately.

        Sends on a background thread with retries. Call :meth:`flush` before a
        process exits, or the last events go with it.
        """
        when = occurred_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        event = _drop_none(
            {
                "eventId": event_id or f"evt_{uuid.uuid4()}",
                "customerId": customer_id,
                "feature": feature,
                "provider": provider,
                "model": model,
                "requestedModel": requested_model,
                "usage": _usage_payload(usage),
                "costUsd": cost_usd,
                "occurredAt": when.isoformat().replace("+00:00", "Z"),
                "outcome": outcome,
                "decisionId": decision_id,
                "retryOfEventId": retry_of_event_id,
                "correctsEventId": corrects_event_id,
            }
        )
        self._background(lambda: self._send_event(event))

    def track_and_wait(self, **kwargs: Any) -> None:
        """track() for jobs and scripts that must not exit early."""
        self.track(**kwargs)
        self.flush()

    def acknowledge(self, decision_id: str, acknowledgment: Acknowledgment) -> None:
        """Tell MarginFuse what your application actually did with a decision."""

        def send() -> None:
            try:
                res = self._post(
                    f"/v1/decisions/{decision_id}/ack",
                    {"acknowledgment": acknowledgment},
                    5.0,
                )
                if res.status < 200 or res.status >= 300:
                    self._report(RuntimeError(f"ack: HTTP {res.status}"), "acknowledge")
            except Exception as err:
                self._report(err, "acknowledge")

        self._background(send)

    def guard(
        self,
        run: Callable[[Decision], ProviderCall],
        *,
        customer_id: str,
        provider: str,
        model: str,
        feature: Optional[str] = None,
        expected_usage: Optional[Usage] = None,
    ) -> GuardOutcome:
        """The whole loop: ask, run, report, acknowledge.

        ``run`` receives the decision and must return a :class:`ProviderCall`.
        Use ``decision.model``: a downgrade verdict changes it.

        It takes a callback rather than being a context manager on purpose. A
        ``with`` block always executes its body, so enforcement would depend on
        the caller remembering to check a flag, and forgetting once means a
        blocked request reaches the provider anyway. Here that is structurally
        impossible: when the verdict is block, ``run`` is never called.

        Errors your callback raises propagate, because your error handling owns
        provider failures. The attempt is still recorded first.
        """
        decision = self.decide(
            customer_id=customer_id,
            provider=provider,
            model=model,
            feature=feature,
            expected_usage=expected_usage,
        )

        # Enforcement depends on the ACTION alone. A missing id costs an
        # acknowledgment; it must never turn a block into a provider call.
        if decision.action == "block":
            if decision.id:
                self.acknowledge(decision.id, "blocked_before_provider_call")
            return GuardOutcome(kind="blocked", decision=decision)
        if decision.action == "topup_required":
            if decision.id:
                self.acknowledge(decision.id, "presented_topup")
            return GuardOutcome(kind="topup_required", decision=decision)

        model_to_use = decision.model if decision.action == "downgrade" else model
        try:
            call = run(decision)
        except BaseException:
            # The provider may still have charged. Record the attempt without
            # usage; a corrected event can carry the real numbers later.
            self.track(
                customer_id=customer_id,
                feature=feature,
                provider=provider,
                model=model_to_use,
                requested_model=model,
                usage=Usage(),
                outcome="provider_error",
                decision_id=decision.id,
            )
            if decision.id:
                self.acknowledge(decision.id, "proceeded_as_requested")
            raise

        self.track(
            customer_id=customer_id,
            feature=feature,
            provider=provider,
            model=model_to_use,
            requested_model=model,
            usage=call.usage,
            cost_usd=call.cost_usd,
            outcome=call.outcome,
            decision_id=decision.id,
        )
        if decision.id:
            self.acknowledge(
                decision.id,
                "used_downgrade_model"
                if decision.action == "downgrade"
                else "proceeded_as_requested",
            )
        return GuardOutcome(kind="completed", decision=decision, result=call.result)

    def flush(self, timeout: Optional[float] = None) -> None:
        """Wait for queued events and acknowledgments. Never raises."""
        with self._lock:
            pending = list(self._pending)
        for future in pending:
            with contextlib.suppress(Exception):
                future.result(timeout=timeout)
        with self._lock:
            self._pending = [f for f in self._pending if not f.done()]

    def close(self) -> None:
        """Flush, then stop the background worker."""
        self.flush()
        self._pool.shutdown(wait=True)

    def __enter__(self) -> MarginFuse:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --------------------------------------------------------------- private

    def _fail_open(self, provider: str, model: str, reason: str) -> Decision:
        return Decision(
            action="allow",
            model=model,
            provider=provider,
            degraded=True,
            degraded_reason=reason,
        )

    def _report(self, error: BaseException, context: str) -> None:
        if self._on_error is None:
            return
        with contextlib.suppress(Exception):
            self._on_error(error, context)

    def _background(self, fn: Callable[[], None]) -> None:
        try:
            future = self._pool.submit(fn)
        except RuntimeError:
            # The pool is shut down. Losing an event is bad; raising into the
            # caller's code is worse.
            return
        with self._lock:
            self._pending = [f for f in self._pending if not f.done()]
            self._pending.append(future)

    def _send_event(self, event: dict[str, Any]) -> None:
        last: Optional[BaseException] = None
        for attempt in range(TRACK_RETRIES):
            try:
                res = self._post("/v1/events", {"events": [event]}, 5.0)
                if 200 <= res.status < 300:
                    return
                if 400 <= res.status < 500 and res.status != 429:
                    # A malformed event is malformed on every attempt.
                    self._report(RuntimeError(f"track: HTTP {res.status} {res.text()}"), "track")
                    return
                last = RuntimeError(f"track: HTTP {res.status}")
            except Exception as err:
                last = err
            time.sleep(0.25 * (2**attempt))
        if last is not None:
            self._report(last, "track")

    def _post(self, path: str, body: dict[str, Any], timeout: float) -> _Response:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
                "user-agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return _Response(response.status, response.read())
        except urllib.error.HTTPError as err:
            # A non-2xx is an answer, not a transport failure.
            return _Response(err.code, err.read())
        except TimeoutError:
            raise
        except OSError as err:
            # urllib raises socket.timeout (an OSError) on read timeouts in
            # some versions; normalise so decide() can name the reason.
            if "timed out" in str(err).lower():
                raise TimeoutError(str(err)) from err
            raise
