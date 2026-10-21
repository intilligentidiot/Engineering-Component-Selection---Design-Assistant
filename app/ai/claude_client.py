"""
Claude (Anthropic) structured-output call, used when AI_PROVIDER=claude.

Same role as the Gemini and OpenAI branches: the model only reads text into a
declared Pydantic schema (or proposes a calculation plan). It never produces
result numbers — the deterministic engine does every calculation.

Configuration (read from environment — never hard-coded):
    ANTHROPIC_API_KEY  — required
    CLAUDE_MODEL       — optional, defaults to claude-opus-5-5
    CLAUDE_EFFORT      — optional: low | medium | high (default medium)

A declined request (safety classifier) is retried server-side on Anthropic's
recommended fallback model (fallbacks="default").
"""
import os
import logging
from typing import Optional, Type

from pydantic import BaseModel

from app.ai.sizing_parser import ProviderError

logger = logging.getLogger(__name__)

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:                     # optional dependency
    anthropic = None
    _ANTHROPIC_AVAILABLE = False

DEFAULT_MODEL = "claude-opus-5-5"
_EFFORTS = ("low", "medium", "high", "xhigh", "max")


def claude_structured(schema: Type[BaseModel], system: str, text: str,
                      api_key: Optional[str] = None, model: Optional[str] = None) -> BaseModel:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ERROR_CONFIGURATION_MISSING", "ANTHROPIC_API_KEY is missing — the AI reader is unavailable.")
    if not _ANTHROPIC_AVAILABLE:
        raise ProviderError("ERROR_CONFIGURATION_MISSING", "anthropic SDK is not installed. Run: pip install anthropic")

    model = model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    effort = os.environ.get("CLAUDE_EFFORT", "medium").strip().lower()
    if effort not in _EFFORTS:
        effort = "medium"
    logger.info("[AI Provider] Claude | model=%s effort=%s", model, effort)

    try:
        client = anthropic.Anthropic(api_key=key)
        resp = client.beta.messages.parse(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": text}],
            output_format=schema,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise ProviderError("ERROR_PROVIDER_AUTH", "AI provider: authentication failed. Check ANTHROPIC_API_KEY.")
    except anthropic.PermissionDeniedError:
        raise ProviderError("ERROR_PROVIDER_AUTH", "AI provider: this API key is not allowed to use the model.")
    except anthropic.RateLimitError:
        raise ProviderError("ERROR_PROVIDER_RATE_LIMIT", "AI provider: rate limit or credit limit reached. Please retry later.")
    except anthropic.APITimeoutError:
        raise ProviderError("ERROR_PROVIDER_TIMEOUT", "AI provider: request timed out.")
    except anthropic.APIConnectionError:
        raise ProviderError("ERROR_PROVIDER_FAILED", "AI provider: could not connect.")
    except anthropic.APIStatusError as e:
        logger.error("[AI Provider] Claude — API error %s", e.status_code)
        raise ProviderError("ERROR_PROVIDER_FAILED", f"AI provider error ({e.status_code}).")

    if resp.stop_reason == "refusal":
        raise ProviderError("ERROR_PROVIDER_REFUSED", "The AI declined this request. Please rephrase it or use the form.")
    if resp.stop_reason == "max_tokens":
        raise ProviderError("ERROR_MALFORMED_RESPONSE", "The AI answer was too long and was cut off. Please shorten the question.")
    parsed = resp.parsed_output
    if parsed is None:
        raise ProviderError("ERROR_MALFORMED_RESPONSE", "The AI returned an unexpected answer.")
    return parsed
