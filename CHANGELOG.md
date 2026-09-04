# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0]

### Fixed

- A downgrade that crosses vendors is reported against the vendor that actually
  ran it. `guard()` already ran the model the server chose, but the usage event
  still named the requested provider, so the call was priced from the wrong
  catalog and the saving the downgrade exists to prove was computed against the
  wrong basis. An `allow` is unchanged, because the decision already defaults
  its provider to the requested one.
- A downgrade whose provider call then fails is acknowledged as
  `used_downgrade_model` rather than `proceeded_as_requested`. The cheaper model
  did run; what failed came after. Reporting otherwise told reconciliation the
  policy never applied, which skewed realized-savings attribution on the error
  path.

### Changed

- Pinned contract v2, whose new scenarios cover both corrections above and add
  a privacy check that hands the SDK content-bearing fields and scans the bytes
  that actually leave the process.

## [0.2.0]

### Added

- `identify()`: tell MarginFuse who a customer is and which plan they are on.

  MarginFuse can now compute margin without a revenue source connected, from
  plans you declare in Settings and a plan assigned per customer. This call is
  how your application assigns that plan itself.

  ```python
  mf.identify(customer_id="user_8x2m91", plan="pro", name="Acme Studio")
  ```

  `plan` is the key of a plan declared in MarginFuse, not a Stripe price id.
  Safe to call on every sign-in: sending the plan the customer is already on
  changes nothing. `period_start` backdates the cycle, `clear_plan` ends it.

  Unlike `track()`, this one reports failure instead of failing quietly. A
  wrong plan is a wrong margin, and there is no safe default for "I could not
  record what this customer pays". Check `result.ok`; `on_error` is called too.
  It still never raises into your code.

- `plan` on `track()`, `guard()` and `decide()`, so a plan can ride along with
  usage rather than needing its own call. There it is a hint: a key that does
  not resolve is ignored rather than failing your event, because usage must
  never be lost to a plan note.

Both are additive. Existing code keeps working unchanged.

## [0.1.0]

First release. Python 3.9+, zero dependencies, standard library only.

### Added

- `MarginFuse.track()` reports an AI call that already happened. Returns
  immediately, sends on a background thread with retries, and never raises into
  application code.
- `MarginFuse.decide()` asks whether the next call should run. Fails open to
  `allow` with `degraded=True` on any timeout or error, because MarginFuse being
  unreachable must not become your outage.
- `MarginFuse.guard()` does the whole loop: ask, run your callback with the
  resolved model, report the real cost, acknowledge what the application did.
- `MarginFuse.flush()` and context manager support, for jobs and scripts that
  would otherwise exit before their last events are sent.
- `from_openrouter()` maps an OpenRouter `usage` object, including the gateway's
  own cost, so gateway figures are exact rather than estimated.

### Notes on the design

- **`guard()` takes a callback rather than being a context manager.** A `with`
  block always runs its body, so enforcement would depend on the caller
  remembering to check a flag, and forgetting once means a blocked request
  reaches the provider anyway. With a callback that is structurally impossible.
- **The public types avoid PEP 604 unions.** `X | None` is only a string under
  `from __future__ import annotations`, so it imports on 3.9 and then fails the
  moment anything resolves it: FastAPI, Pydantic, any dataclass serializer. A
  test pins this.
- Verified against
  [marginfuse/sdk-contract](https://github.com/marginfuse/sdk-contract): 16
  behavioral scenarios and 13 gateway vectors, the same ones the Node SDK
  passes, so the two agree rather than each being separately plausible.
