# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
