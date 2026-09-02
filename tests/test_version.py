"""The reported version has to be the version that was published.

The user-agent is how a support conversation starts: someone reports odd
behaviour and the first question is which version sent the request. The Node
SDK answered that question with "0.1.0" for two releases, because the string
was written once and nothing ever compared it to the package metadata.
"""

import re
from pathlib import Path

from marginfuse import __version__
from marginfuse._client import USER_AGENT

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _declared_version() -> str:
    # Parsed by hand rather than with tomllib, which arrived in 3.11 and this
    # package supports 3.9.
    for line in PYPROJECT.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r'\s*version\s*=\s*"([^"]+)"\s*', line)
        if match:
            return match.group(1)
    raise AssertionError(f"no version found in {PYPROJECT}")


def test_version_matches_the_packaging_metadata() -> None:
    assert __version__ == _declared_version()


def test_the_user_agent_reports_that_version() -> None:
    assert "marginfuse-python/" + _declared_version() == USER_AGENT
