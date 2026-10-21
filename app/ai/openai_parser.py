"""
Stage 7.2 — OpenAI Requirement Parser

Implements the RequirementParser interface using the official OpenAI Python SDK.
Uses structured output (Pydantic schema) via the Responses API so the model
is forced to return exactly the fields we declare — no free-form text, no JSON
parsing of arbitrary strings.

The AI is ONLY responsible for extracting natural-language requirements into
structured fields.  All engineering calculations remain in the deterministic
engine and are never touched by the AI layer.
"""

import os
import logging
from typing import Optional

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.ai.requirement_parser import RequirementParser, ParseResult, ParsedRequirements

# Top-level import so unittest.mock.patch("app.ai.openai_parser.OpenAI") works.
# openai is an optional dependency — ImportError is caught at call time.
try:
    from openai import (
        OpenAI,
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        RateLimitError,
        APIStatusError,
    )
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strict structured output schema (what the LLM must produce)
# ---------------------------------------------------------------------------

class _AIExtractedRequirements(BaseModel):
    """
    Pydantic model used as the structured-output schema passed to the OpenAI
    Responses API.  The model is forced to emit exactly these fields; any field
    not mentioned by the user must be null — never invented.
    """
    required_torque_nm: Optional[float] = Field(
        None,
        description=(
            "Output torque required by the user, in Newton-metres (Nm). "
            "Convert from N-m or N·m.  Return null if not stated or if the "
            "unit is unsupported (e.g. lb-in, oz-in)."
        )
    )
    required_speed_rpm: Optional[float] = Field(
        None,
        description=(
            "Output shaft speed required by the user, in RPM. "
            "Accept rpm, rev/min, r/min.  Return null if not stated."
        )
    )
    max_voltage_v: Optional[float] = Field(
        None,
        description=(
            "Maximum supply voltage constraint stated by the user, in Volts. "
            "This is the user's constraint ('maximum 20 V'), NOT a product "
            "rating.  Accept V, volt, volts.  Return null if not stated."
        )
    )
    service_factor: Optional[float] = Field(
        None,
        description=(
            "Service factor as a dimensionless multiplier (e.g. 1.5). "
            "Return null if not mentioned."
        )
    )
    application: Optional[str] = Field(
        None,
        description=(
            "Short description of the application (e.g. 'conveyor', "
            "'robot arm').  Return null if not mentioned."
        )
    )
    clarifications: list[str] = Field(
        default_factory=list,
        description=(
            "List any ambiguous or unsupported units found "
            "(e.g. 'lb-in detected — please provide torque in Nm'). "
            "Leave empty if no clarification is needed."
        )
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an engineering requirements extraction assistant. "
    "Your only job is to read the user's text and extract the engineering "
    "requirements they explicitly stated into the provided JSON schema. "
    "If a value is absent or ambiguous, return null — never invent or "
    "estimate a value. "
    "Do not perform any calculations. "
    "Do not recommend any product. "
    "Do not decide whether a product meets the requirements."
)


# ---------------------------------------------------------------------------
# OpenAI provider implementation
# ---------------------------------------------------------------------------

class OpenAIRequirementParser(RequirementParser):
    """
    Real OpenAI-backed requirement parser.

    Uses the official openai Python SDK with structured output (parse()) so the
    model is constrained to the _AIExtractedRequirements Pydantic schema.

    Configuration (read from environment — never hard-coded):
        OPENAI_API_KEY  — required
        OPENAI_MODEL    — optional, defaults to gpt-4o-mini
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    # ------------------------------------------------------------------
    def parse(self, text: str) -> ParseResult:
        # ── 1. Configuration guard ──────────────────────────────────────
        if not self._api_key:
            logger.warning("[AI Provider] OpenAI — OPENAI_API_KEY not configured.")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["OPENAI_API_KEY is missing. AI parsing is unavailable."],
                parser_status="ERROR_CONFIGURATION_MISSING",
            )

        if not self._model:
            logger.warning("[AI Provider] OpenAI — OPENAI_MODEL not configured.")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["OPENAI_MODEL is missing. AI parsing is unavailable."],
                parser_status="ERROR_CONFIGURATION_MISSING",
            )

        logger.info("[AI Provider] OpenAI | model=%s", self._model)

        # ── 2. SDK availability guard ───────────────────────────────────
        if not _OPENAI_AVAILABLE:
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["openai SDK is not installed. Run: pip install openai"],
                parser_status="ERROR_CONFIGURATION_MISSING",
            )

        # ── 3. Call OpenAI Responses API with structured output ─────────
        try:
            client = OpenAI(api_key=self._api_key)

            response = client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": text},
                ],
                text_format=_AIExtractedRequirements,
            )

            extracted: _AIExtractedRequirements = response.output_parsed

        # ── Provider / network errors ───────────────────────────────────
        except AuthenticationError:
            logger.error("[AI Provider] OpenAI — authentication failed (invalid API key).")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider: Authentication failed. Check OPENAI_API_KEY."],
                parser_status="ERROR_PROVIDER_AUTH",
            )

        except RateLimitError:
            logger.error("[AI Provider] OpenAI — rate limit exceeded.")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider: Rate limit exceeded. Please retry later."],
                parser_status="ERROR_PROVIDER_RATE_LIMIT",
            )

        except APITimeoutError:
            logger.error("[AI Provider] OpenAI — request timed out.")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider: Request timed out."],
                parser_status="ERROR_PROVIDER_TIMEOUT",
            )

        except APIConnectionError as exc:
            logger.error("[AI Provider] OpenAI — connection error: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"AI Provider: Connection error — {type(exc).__name__}"],
                parser_status="ERROR_PROVIDER_FAILED",
            )

        except APIStatusError as exc:
            logger.error("[AI Provider] OpenAI — HTTP %s", exc.status_code)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"AI Provider Error: HTTP {exc.status_code}"],
                parser_status="ERROR_PROVIDER_FAILED",
            )

        except Exception as exc:
            logger.error("[AI Provider] OpenAI — unexpected error: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"Unexpected AI provider error: {type(exc).__name__}"],
                parser_status="ERROR_UNEXPECTED",
            )

        return build_parse_result(extracted, "OpenAI")


def build_parse_result(extracted: "_AIExtractedRequirements", provider: str) -> ParseResult:
    """Validate extracted values and build the ParseResult (shared by the OpenAI and Claude parsers)."""
    # ── 3. Validate extracted values ────────────────────────────────
    # Any invalid engineering value (negative, wrong type) is rejected.
    validation_errors: list[str] = []

    def _check_positive(val: Optional[float], name: str) -> Optional[float]:
        if val is None:
            return None
        if not isinstance(val, (int, float)):
            validation_errors.append(f"{name} has invalid type: {type(val).__name__}")
            return None
        if val <= 0:
            validation_errors.append(f"{name} must be positive; got {val}")
            return None
        return float(val)

    torque  = _check_positive(extracted.required_torque_nm,  "required_torque_nm")
    speed   = _check_positive(extracted.required_speed_rpm,  "required_speed_rpm")
    voltage = _check_positive(extracted.max_voltage_v,       "max_voltage_v")
    sf      = _check_positive(extracted.service_factor,      "service_factor")

    # Extra fields the model should not have invented are silently ignored
    # because _AIExtractedRequirements has a closed schema.

    if validation_errors:
        logger.warning("[AI Provider] %s — validation errors: %s", provider, validation_errors)
        return ParseResult(
            requirements=ParsedRequirements(),
            missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
            clarifications=validation_errors,
            parser_status="ERROR_VALIDATION_FAILED",
        )

    # ── 4. Build application-level result ───────────────────────────
    try:
        reqs = ParsedRequirements(
            required_torque_nm=torque,
            required_speed_rpm=speed,
            max_voltage_v=voltage,
            service_factor=sf,
            application=(extracted.application or None),
        )
    except PydanticValidationError as exc:
        logger.error("[AI Provider] %s — Pydantic schema rejection: %s", provider, exc)
        return ParseResult(
            requirements=ParsedRequirements(),
            missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
            clarifications=["AI output failed application schema validation."],
            parser_status="ERROR_VALIDATION_FAILED",
        )

    clarifications: list[str] = list(extracted.clarifications or [])

    missing: list[str] = []
    if reqs.required_torque_nm is None:
        missing.append("required_torque_nm")
    if reqs.required_speed_rpm is None:
        missing.append("required_speed_rpm")
    if reqs.max_voltage_v is None:
        missing.append("max_voltage_v")

    if clarifications:
        status = "NEEDS_CLARIFICATION"
    elif missing:
        status = "PARTIAL"
        clarifications.append(
            "Please provide the missing engineering specifications to get a recommendation."
        )
    else:
        status = "PARSED"

    return ParseResult(
        requirements=reqs,
        missing_fields=missing,
        clarifications=clarifications,
        parser_status=status,
    )
