# marginfuse

[![PyPI](https://img.shields.io/pypi/v/marginfuse)](https://pypi.org/project/marginfuse/)
[![ci](https://github.com/marginfuse/marginfuse-python/actions/workflows/ci.yml/badge.svg)](https://github.com/marginfuse/marginfuse-python/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Server-side SDK for [MarginFuse](https://marginfuse.com): profitability
guardrails for AI SaaS. Connect revenue to per-request AI cost, see gross margin
per customer, and stop loss-making requests before they run.

- **Metadata only, by construction.** The event shape has no field for prompts
  or responses, so they cannot be sent. Not a policy, an absence.
- **Never breaks your app.** It does not raise into your code, and it does not
  block your request on MarginFuse being up. If MarginFuse is unreachable, your
  requests proceed unchanged.
- **Zero dependencies.** Standard library only, Python 3.9+.

> **Server side only.** This SDK carries a secret API key. Never ship it in a
> desktop app, a mobile app, or anything else a user can read.

## Install

```bash
pip install marginfuse
```

## Track an AI call

Monitoring. One call after each AI request, metadata only.

```python
import os
from marginfuse import MarginFuse, Usage

mf = MarginFuse(api_key=os.environ["MARGINFUSE_KEY"])

r = client.chat.completions.create(model="gpt-4.1", messages=messages)

mf.track(
    customer_id="cus_8x2m91",  # your Stripe customer id, or your own
    feature="ai_chat",
    provider="openai",
    model="gpt-4.1",
    usage=Usage(
        input_tokens=r.usage.prompt_tokens,
        output_tokens=r.usage.completion_tokens,
    ),
)
```

`track()` returns immediately and sends on a background thread with retries. In
a script, a Celery task or a Lambda handler, call `mf.flush()` before the
process exits, or the last events go with it.

```python
with MarginFuse(api_key=os.environ["MARGINFUSE_KEY"]) as mf:
    ...  # closing flushes
```

## Guard a call

Protection. Ask before the call runs, and act on the answer.

```python
from marginfuse import MarginFuse, ProviderCall, Usage


def run(decision):
    # decision.model is the one to call: a downgrade verdict changes it.
    r = client.chat.completions.create(model=decision.model, messages=messages)
    return ProviderCall(
        result=r,
        usage=Usage(
            input_tokens=r.usage.prompt_tokens,
            output_tokens=r.usage.completion_tokens,
        ),
    )


out = mf.guard(run, customer_id="cus_8x2m91", feature="ai_chat", provider="openai", model="gpt-4.1")

if out.kind == "completed":
    use(out.result)
elif out.kind == "topup_required":
    show_topup(out.decision.topup_context)
else:
    show_limit_reached()
```

One call does the whole loop: ask, run with the resolved model, report the real
cost, acknowledge what your application did.

### Why a callback and not a context manager

A `with` block always runs its body. Enforcement would then depend on you
remembering to check a flag, and forgetting once means a blocked request reaches
the provider anyway. With a callback that is structurally impossible: when the
verdict is `block`, your function is never called.

## Tell MarginFuse what a customer pays

Margin needs a revenue side. With Stripe connected it comes from there. Without
one, you declare your plans in MarginFuse and say which plan each customer is
on:

```python
result = mf.identify(
    customer_id="user_8x2m91",
    plan="pro",  # the key of a plan you declared in Settings
    name="Acme Studio",
    metadata={"tier": "legacy"},  # labels segment policies can match on
)

if not result.ok:
    log.warning("MarginFuse identify: %s", result.error)
```

Safe to call on every sign-in: sending the plan the customer is already on
changes nothing. Sending a different one ends the current cycle and prorates
what accrued. `period_start` backdates the cycle for a customer who has been
paying since an earlier date; `clear_plan=True` takes them off plans.

This is the one call that does not fail open. `track()` retries later and
`decide()` allows, because both have a safe default; "I could not record what
this customer pays" has none, and a wrong plan is a wrong margin. So it reports
the failure to you instead of swallowing it. It still never raises.

`track()`, `guard()` and `decide()` also accept a `plan`, so it can ride along
with usage rather than needing its own call. There it is a hint: a key that
does not resolve is ignored rather than failing your event.

## OpenRouter and other gateways

Gateways report the real cost of every call. Forward it and your figures are
exact instead of estimated.

```python
from marginfuse import from_openrouter

r = client.chat.completions.create(model="anthropic/claude-sonnet-4.5", messages=messages)

mf.track(
    customer_id="cus_8x2m91",
    feature="ai_chat",
    provider="openrouter",
    model="anthropic/claude-sonnet-4.5",
    **from_openrouter(r.usage),
)
```

Use the helper rather than mapping the fields yourself. OpenRouter's
`prompt_tokens` already includes cached reads and cache writes, which MarginFuse
prices separately, so passing it through directly charges every cached token
twice at the full input rate. The helper also formats the cost as a decimal
string, because `str(1.2e-07)` produces exponent notation and the API rejects
that.

## Configuration

```python
mf = MarginFuse(
    api_key=os.environ["MARGINFUSE_KEY"],
    base_url="https://api.marginfuse.com",  # your own deployment in dev
    timeout=1.5,  # decide() budget before failing open
    on_error=lambda err, ctx: log.warning("marginfuse %s: %s", ctx, err),
)
```

`on_error` is the only place transport failures surface. The SDK swallows them
so they cannot become your outage; without the hook they are silent.

## Async applications

This client is synchronous and does no I/O on the calling thread except during
`decide()` and `guard()`. In an async application, keep the event loop free by
running those in a worker thread:

```python
decision = await asyncio.to_thread(mf.decide, customer_id=cid, provider="openai", model="gpt-4.1")
```

`track()` and `acknowledge()` already return immediately, so they are safe to
call directly from async code.

## What it sends

Everything, and nothing else:

```
event_id  customer_id  feature  provider  model  requested_model
usage(input_tokens, output_tokens, cached_input_tokens,
      cache_creation_tokens, images, audio_seconds)
cost_usd  occurred_at  outcome  decision_id  retry_of_event_id  corrects_event_id
```

There is no field for message content anywhere in the wire types. The
[conformance suite](https://github.com/marginfuse/sdk-contract) checks this
against the bytes that actually leave the process, on every scenario.

## Conformance

This SDK is verified against
[marginfuse/sdk-contract](https://github.com/marginfuse/sdk-contract), the same
contract every MarginFuse SDK in every language is held to. It is a submodule
here, so the pinned commit records exactly which contract a release passed.

```bash
git clone --recurse-submodules https://github.com/marginfuse/marginfuse-python
cd marginfuse-python
uv sync
uv run pytest          # unit tests, plus the shared gateway vectors
uv run --directory contract/harness npm install
npm --prefix contract/harness run conformance python
```

## Links

- [MarginFuse](https://marginfuse.com), product and pricing
- [Documentation](https://marginfuse.com/docs)
- [API reference](https://api.marginfuse.com/openapi.json)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

MIT, Pemira Labs.
