"""MarginFuse: profitability guardrails for AI SaaS.

    from marginfuse import MarginFuse, Usage

    mf = MarginFuse(api_key=os.environ["MARGINFUSE_KEY"])
    mf.track(
        customer_id="cus_8x2m91",
        feature="ai_chat",
        provider="openai",
        model="gpt-4.1",
        usage=Usage(input_tokens=1204, output_tokens=388),
    )

Server side only: this SDK carries a secret API key.
"""

from ._client import MarginFuse
from ._openrouter import from_openrouter
from ._types import (
    Acknowledgment,
    Decision,
    DecisionAction,
    GuardOutcome,
    IdentifyResult,
    Outcome,
    ProviderCall,
    Usage,
)
from ._version import __version__ as __version__

__all__ = [
    "CONTRACT_VERSION",
    "Acknowledgment",
    "Decision",
    "DecisionAction",
    "GuardOutcome",
    "IdentifyResult",
    "MarginFuse",
    "Outcome",
    "ProviderCall",
    "Usage",
    "from_openrouter",
]


#: The version of the shared SDK contract this build was verified against.
#:
#: Package versions differ per language, because each tracks its own breaking
#: changes: a rename in Python must not tell Node users something broke. What
#: makes the SDKs interchangeable is this, not the package version. Two SDKs
#: reporting the same contract version have passed the same scenarios and the
#: same vectors.
#:
#: See github.com/marginfuse/sdk-contract.
CONTRACT_VERSION = 1
