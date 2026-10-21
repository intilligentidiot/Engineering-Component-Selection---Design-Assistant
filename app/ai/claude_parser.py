"""
Claude Requirement Parser (Advanced tab: torque / speed / voltage reader).

Same schema, prompt and validation as the OpenAI parser; only the provider
call differs (app/ai/claude_client.py). The AI only extracts stated values.
"""
import os
import logging
from typing import Optional

from app.ai.requirement_parser import RequirementParser, ParseResult, ParsedRequirements
from app.ai.openai_parser import _AIExtractedRequirements, _SYSTEM_PROMPT, build_parse_result
from app.ai.claude_client import claude_structured, DEFAULT_MODEL
from app.ai.sizing_parser import ProviderError

logger = logging.getLogger(__name__)

_ALL_MISSING = ["required_torque_nm", "required_speed_rpm", "max_voltage_v"]


class ClaudeRequirementParser(RequirementParser):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._model = model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)

    def parse(self, text: str) -> ParseResult:
        try:
            extracted = claude_structured(_AIExtractedRequirements, _SYSTEM_PROMPT, text,
                                          api_key=self._api_key, model=self._model)
        except ProviderError as e:
            return ParseResult(requirements=ParsedRequirements(), missing_fields=list(_ALL_MISSING),
                               clarifications=[e.message], parser_status=e.status)
        except Exception as exc:
            logger.error("[AI Provider] Claude — unexpected error: %s", exc)
            return ParseResult(requirements=ParsedRequirements(), missing_fields=list(_ALL_MISSING),
                               clarifications=[f"Unexpected AI provider error: {type(exc).__name__}"],
                               parser_status="ERROR_UNEXPECTED")
        return build_parse_result(extracted, "Claude")
