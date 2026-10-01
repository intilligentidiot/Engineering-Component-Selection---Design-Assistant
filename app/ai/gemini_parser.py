"""
Stage 7.2 (Gemini) — Gemini Requirement Parser

Implements the RequirementParser interface using Google's official
google-genai Python SDK (google-genai >= 2.0).

Uses structured JSON output constrained by a Pydantic response_schema
so Gemini is forced to return exactly the declared fields — never
free-form text, never invented engineering values.

The AI is ONLY responsible for extracting natural-language requirements
into structured fields.  All engineering calculations remain in the
deterministic engine and are never touched by this parser.

Configuration (read from environment — never hard-coded):
    GEMINI_API_KEY   — required
    GEMINI_MODEL     — optional, defaults to gemini-2.0-flash-lite
"""

import os
import logging
from typing import Optional

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from app.ai.requirement_parser import RequirementParser, ParseResult, ParsedRequirements

# ---------------------------------------------------------------------------
# Top-level import so unittest.mock.patch("app.ai.gemini_parser.genai") works.
# google-genai is an optional dependency — ImportError handled at call time.
# ---------------------------------------------------------------------------
try:
    import google.genai as genai
    from google.genai import types as genai_types
    from google.genai import errors as genai_errors
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strict structured output schema (what Gemini must produce)
# ---------------------------------------------------------------------------

class _GeminiExtractedRequirements(BaseModel):
    """
    Pydantic model used as response_schema for Gemini structured output.
    Gemini is constrained to emit exactly these fields.
    Any field not mentioned by the user must be null — never invented.
    """
    required_torque_nm: Optional[float] = Field(
        None,
        description=(
            "Output torque required by the user, in Newton-metres (Nm). "
            "Accept Nm, N-m, N·m. Return null if not stated or if unit is "
            "unsupported (e.g. lb-in, oz-in)."
        )
    )
    required_speed_rpm: Optional[float] = Field(
        None,
        description=(
            "Output shaft speed required by the user, in RPM. "
            "Accept rpm, rev/min, r/min. Return null if not stated."
        )
    )
    max_voltage_v: Optional[float] = Field(
        None,
        description=(
            "Maximum supply voltage constraint stated by the user, in Volts. "
            "This is the user's constraint ('maximum 20 V'), NOT a product rating. "
            "Accept V, volt, volts. Return null if not stated."
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
            "Short description of the application (e.g. 'conveyor', 'robot arm'). "
            "Return null if not mentioned."
        )
    )
    clarifications: list[str] = Field(
        default_factory=list,
        description=(
            "List any ambiguous or unsupported units found. "
            "Leave empty if no clarification is needed."
        )
    )


# ---------------------------------------------------------------------------
# System instruction
# ---------------------------------------------------------------------------

_SYSTEM_INSTRUCTION = (
    "You are a requirement extraction component for an engineering application. "
    "Extract only engineering requirements explicitly stated or clearly expressed "
    "by the user. "
    "Return the required structured fields. "
    "Do not calculate engineering quantities. "
    "Do not select motors or gearboxes. "
    "Do not determine whether any product meets the requirement. "
    "Do not invent missing values. "
    "If a value is absent or ambiguous, return null and record a clarification."
)


# ---------------------------------------------------------------------------
# Gemini provider implementation
# ---------------------------------------------------------------------------

class GeminiRequirementParser(RequirementParser):
    """
    Real Gemini-backed requirement parser.

    Uses the official google-genai Python SDK with structured JSON output
    (response_schema=_GeminiExtractedRequirements) so the model is
    constrained to the declared Pydantic schema.

    Configuration (read from environment — never hard-coded):
        GEMINI_API_KEY   — required
        GEMINI_MODEL     — optional, defaults to gemini-2.5-flash
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    # ------------------------------------------------------------------
    def parse(self, text: str) -> ParseResult:

        # ── 1. Configuration guard ──────────────────────────────────────
        if not self._api_key:
            logger.warning("[AI Provider] Gemini — GEMINI_API_KEY not configured.")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["GEMINI_API_KEY is missing. AI parsing is unavailable."],
                parser_status="ERROR_CONFIGURATION_MISSING",
            )

        # ── 2. SDK availability guard ───────────────────────────────────
        if not _GENAI_AVAILABLE:
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["google-genai SDK is not installed. Run: pip install google-genai"],
                parser_status="ERROR_CONFIGURATION_MISSING",
            )

        logger.info("[AI Provider] Gemini | model=%s", self._model)

        # ── 3. Call Gemini with structured JSON output ──────────────────
        try:
            client = genai.Client(api_key=self._api_key)

            response = client.models.generate_content(
                model=self._model,
                contents=text,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=_GeminiExtractedRequirements,
                    temperature=0.0,
                ),
            )

            # The SDK returns a structured object when response_schema is a
            # Pydantic model — accessed via response.parsed.
            # Fall back to JSON text parsing if .parsed is unavailable.
            if hasattr(response, "parsed") and response.parsed is not None:
                extracted: _GeminiExtractedRequirements = response.parsed
            else:
                import json as _json
                raw_text = response.text or ""
                raw_dict = _json.loads(raw_text)
                extracted = _GeminiExtractedRequirements(**raw_dict)

        # ── Provider / network errors ───────────────────────────────────
        except genai_errors.ClientError as exc:
            status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            # 401 / 403 → auth; 429 → rate limit; others → provider failed
            if status_code in (401, 403):
                logger.error("[AI Provider] Gemini — authentication failed: %s", exc)
                return ParseResult(
                    requirements=ParsedRequirements(),
                    missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                    clarifications=["AI Provider: Authentication failed. Check GEMINI_API_KEY."],
                    parser_status="ERROR_PROVIDER_AUTH",
                )
            if status_code == 429:
                logger.error("[AI Provider] Gemini — quota/rate-limit exceeded.")
                return ParseResult(
                    requirements=ParsedRequirements(),
                    missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                    clarifications=["AI Provider: Rate limit / quota exceeded. Please retry later."],
                    parser_status="ERROR_PROVIDER_RATE_LIMIT",
                )
            logger.error("[AI Provider] Gemini — client error: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"AI Provider Error: {type(exc).__name__}"],
                parser_status="ERROR_PROVIDER_FAILED",
            )

        except genai_errors.ServerError as exc:
            logger.error("[AI Provider] Gemini — server error: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"AI Provider Error: {type(exc).__name__}"],
                parser_status="ERROR_PROVIDER_FAILED",
            )

        except genai_errors.APIError as exc:
            logger.error("[AI Provider] Gemini — API error: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"AI Provider Error: {type(exc).__name__}"],
                parser_status="ERROR_PROVIDER_FAILED",
            )

        except TimeoutError as exc:
            logger.error("[AI Provider] Gemini — timeout.")
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider: Request timed out."],
                parser_status="ERROR_PROVIDER_TIMEOUT",
            )

        except (ValueError, KeyError, TypeError, __import__("json").JSONDecodeError) as exc:
            logger.error("[AI Provider] Gemini — malformed/invalid response: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=["AI Provider returned a malformed or unexpected response."],
                parser_status="ERROR_MALFORMED_RESPONSE",
            )

        except Exception as exc:
            logger.error("[AI Provider] Gemini — unexpected error: %s", exc)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=[f"Unexpected AI provider error: {type(exc).__name__}"],
                parser_status="ERROR_UNEXPECTED",
            )

        # ── 4. Validate extracted values ────────────────────────────────
        # Any invalid engineering value (negative, zero, wrong type) is rejected.
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

        torque  = _check_positive(extracted.required_torque_nm, "required_torque_nm")
        speed   = _check_positive(extracted.required_speed_rpm, "required_speed_rpm")
        voltage = _check_positive(extracted.max_voltage_v,      "max_voltage_v")
        sf      = _check_positive(extracted.service_factor,     "service_factor")

        if validation_errors:
            logger.warning("[AI Provider] Gemini — validation errors: %s", validation_errors)
            return ParseResult(
                requirements=ParsedRequirements(),
                missing_fields=["required_torque_nm", "required_speed_rpm", "max_voltage_v"],
                clarifications=validation_errors,
                parser_status="ERROR_VALIDATION_FAILED",
            )

        # ── 5. Build application-level result ───────────────────────────
        try:
            reqs = ParsedRequirements(
                required_torque_nm=torque,
                required_speed_rpm=speed,
                max_voltage_v=voltage,
                service_factor=sf,
                application=(extracted.application or None),
            )
        except PydanticValidationError as exc:
            logger.error("[AI Provider] Gemini — Pydantic schema rejection: %s", exc)
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
