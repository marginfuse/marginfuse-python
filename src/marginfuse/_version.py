"""The package version, in one place.

It is a literal rather than a lookup through ``importlib.metadata`` so that it
still answers correctly when the package is run from a source tree rather than
an installed distribution. A literal drifts unless something checks it, so
``tests/test_version.py`` asserts it equals the version in ``pyproject.toml``.

The Node SDK shipped two releases sending ``marginfuse-node/0.1.0`` because it
had the same literal and nothing compared it to anything.
"""

__version__ = "0.2.0"
