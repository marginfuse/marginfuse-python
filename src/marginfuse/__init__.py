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
    Outcome,
    ProviderCall,
    Usage,
)

__all__ = [
    "Acknowledgment",
    "Decision",
    "DecisionAction",
    "GuardOutcome",
    "MarginFuse",
    "Outcome",
    "ProviderCall",
    "Usage",
    "from_openrouter",
]

__version__ = "0.1.0"
