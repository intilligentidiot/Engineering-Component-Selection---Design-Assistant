"""
Parser Provider Selection

Single authoritative place that reads AI_PROVIDER from the environment
and returns the correct RequirementParser implementation.

Routes and all other callers import only get_parser() — no parser
construction logic lives in routes.py or anywhere else.

Configuration:
    AI_PROVIDER=mock    → MockRequirementParser   (default; safe for tests)
    AI_PROVIDER=claude  → ClaudeRequirementParser (requires ANTHROPIC_API_KEY)
    AI_PROVIDER=openai  → OpenAIRequirementParser (requires OPENAI_API_KEY)
    AI_PROVIDER=gemini  → GeminiRequirementParser (requires GEMINI_API_KEY)

Unknown values raise a RuntimeError with a controlled message so FastAPI
returns a clear error rather than silently selecting the wrong provider.

Logging:
    Logs provider name at INFO level.
    Never logs API keys or sensitive values.
"""

import os
import logging
from app.ai.requirement_parser import RequirementParser

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = ("mock", "claude", "openai", "gemini")


def get_parser() -> RequirementParser:
    """
    Return the configured RequirementParser implementation.

    Reads AI_PROVIDER environment variable (case-insensitive).
    Defaults to 'mock' so pytest and development never require a real key.

    Raises RuntimeError for unknown provider values rather than silently
    falling back to an unexpected implementation.
    """
    provider = os.environ.get("AI_PROVIDER", "mock").strip().lower()

    if provider == "claude":
        from app.ai.claude_parser import ClaudeRequirementParser
        logger.info("[AI Provider] Claude")
        return ClaudeRequirementParser()

    if provider == "openai":
        from app.ai.openai_parser import OpenAIRequirementParser
        logger.info("[AI Provider] OpenAI")
        return OpenAIRequirementParser()

    if provider == "gemini":
        from app.ai.gemini_parser import GeminiRequirementParser
        logger.info("[AI Provider] Gemini")
        return GeminiRequirementParser()

    if provider == "mock":
        from app.ai.requirement_parser import MockRequirementParser
        logger.info("[AI Provider] Mock")
        return MockRequirementParser()

    # Unknown provider — controlled error, no silent fallback
    raise RuntimeError(
        f"Unknown AI_PROVIDER '{provider}'. "
        f"Supported values: {', '.join(_SUPPORTED_PROVIDERS)}"
    )
