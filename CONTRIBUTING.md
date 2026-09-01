# Contributing

## Getting set up

The conformance contract is a submodule, so clone with it:

```bash
git clone --recurse-submodules https://github.com/marginfuse/marginfuse-python
cd marginfuse-python
uv sync
uv run pytest
```

If you already cloned without it: `git submodule update --init --recursive`.

## Before you open a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest

npm --prefix contract/harness install
npm --prefix contract/harness run conformance python
```

CI runs all of it on Python 3.9 through 3.13.

## Three rules worth knowing before you change behavior

**This SDK never raises into application code.** It sits in the request path of
somebody else's product. A transport error goes to the `on_error` hook and the
call proceeds; it does not become an exception the caller has to catch. The one
exception is `guard()`, which propagates whatever your own callback raised,
because your error handling owns that.

**`guard()` will not become a context manager.** A `with` block always runs its
body, so enforcement would depend on the caller remembering to check a flag.
Forgetting once means a blocked request reaches the provider. The callback form
makes that impossible, and that is worth more than the nicer-looking API.

**Behavior is defined in the contract, not here.** The expectations live in
[marginfuse/sdk-contract](https://github.com/marginfuse/sdk-contract) as data,
and every MarginFuse SDK in every language reads the same files. If you are
changing what the SDK does rather than how it does it, the change starts with a
pull request there. Otherwise this SDK drifts away from the others, which is
the failure the contract exists to prevent.

## Style

Match the surrounding code. `ruff` decides formatting. Comments explain why, not
what. No em dashes.

Avoid PEP 604 unions (`X | None`) in anything public: they resolve at runtime
and this package supports Python 3.9. Use `Optional[X]`. A test enforces it.
