"""
Stage 7.2 (Gemini) — Gemini Parser Tests

All tests are fully deterministic.
No real Gemini API calls are made.
The google-genai client is mocked at the exact call site inside gemini_parser.py.

Tests:
  1. Valid provider response → correct structured requirements
  2. Application extraction → conveyor
  3. Missing torque → remains None
  4. Missing service factor → remains None
  5. Service factor extraction → 1.5
  6. Invalid model output (negative torque) → validation failure
  7. Provider exception (Auth Error) → controlled provider-auth status
  8. Provider exception (Rate Limit) → controlled rate-limit status
  9. Timeout → controlled timeout status
 10. Missing API key → configuration error
 11. Extra/unexpected fields from provider → ignored
 12. Provider selection logic (Mock, OpenAI, Gemini)
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.ai.gemini_parser import GeminiRequirementParser, _GeminiExtractedRequirements
from app.ai.provider import get_parser
import os

# ---------------------------------------------------------------------------
# Helpers — build a mock GenerateContentResponse
# ---------------------------------------------------------------------------

def _make_response(extracted: _GeminiExtractedRequirements) -> MagicMock:
    """Return a MagicMock that mimics google.genai.types.GenerateContentResponse."""
    mock_resp = MagicMock()
    mock_resp.parsed = extracted
    return mock_resp


# ---------------------------------------------------------------------------
# TEST 1 — Valid provider returns correct structured requirements
# ---------------------------------------------------------------------------

def test_1_gemini_valid_full_requirements():
    """Gemini provider returns 1 Nm, 35 RPM, 20 V → correct structured requirements."""
    extracted = _GeminiExtractedRequirements(
        required_torque_nm=1.0,
        required_speed_rpm=35.0,
        max_voltage_v=20.0,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.return_value = _make_response(extracted)

        parser = GeminiRequirementParser(api_key="fake-key", model="gemini-3.5-flash-lite")
        result = parser.parse("I need 1 Nm at 35 RPM, maximum 20 V.")

    assert result.parser_status == "PARSED"
    assert result.requirements.required_torque_nm == 1.0
    assert result.requirements.required_speed_rpm == 35.0
    assert result.requirements.max_voltage_v == 20.0
    assert result.requirements.service_factor is None
    assert len(result.missing_fields) == 0


# ---------------------------------------------------------------------------
# TEST 2 — Application extraction
# ---------------------------------------------------------------------------

def test_2_gemini_application_extraction():
    """Natural-language application 'motor for a conveyor' → application = 'conveyor'."""
    extracted = _GeminiExtractedRequirements(
        required_torque_nm=None,
        required_speed_rpm=None,
        max_voltage_v=None,
        service_factor=None,
        application="conveyor",
        clarifications=[],
    )
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.return_value = _make_response(extracted)

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need a geared motor for a conveyor.")

    assert result.requirements.application == "conveyor"
    assert result.requirements.required_torque_nm is None
    assert "required_torque_nm" in result.missing_fields
    assert result.parser_status == "PARTIAL"


# ---------------------------------------------------------------------------
# TEST 3 — Missing torque
# ---------------------------------------------------------------------------

def test_3_gemini_missing_torque():
    """'about 30 RPM' → torque remains None, speed captured."""
    extracted = _GeminiExtractedRequirements(
        required_torque_nm=None,
        required_speed_rpm=30.0,
        max_voltage_v=None,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.return_value = _make_response(extracted)

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need approximately 30 RPM.")

    assert result.requirements.required_torque_nm is None
    assert result.requirements.required_speed_rpm == 30.0
    assert "required_torque_nm" in result.missing_fields
    assert result.parser_status == "PARTIAL"


# ---------------------------------------------------------------------------
# TEST 4 & 5 — Service factor extraction
# ---------------------------------------------------------------------------

def test_4_gemini_missing_service_factor():
    """Service factor not mentioned → remains None; no invention."""
    extracted = _GeminiExtractedRequirements(
        required_torque_nm=1.0,
        required_speed_rpm=35.0,
        max_voltage_v=None,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.return_value = _make_response(extracted)

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.requirements.service_factor is None
    assert result.parser_status == "PARTIAL" # missing max_voltage_v

def test_5_gemini_service_factor_extraction():
    """Service factor mentioned → extracted."""
    extracted = _GeminiExtractedRequirements(
        required_torque_nm=1.0,
        required_speed_rpm=35.0,
        max_voltage_v=None,
        service_factor=1.5,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.return_value = _make_response(extracted)

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need 1 Nm at 35 RPM with a service factor of 1.5.")

    assert result.requirements.service_factor == 1.5


# ---------------------------------------------------------------------------
# TEST 6 — Invalid model output (negative engineering value)
# ---------------------------------------------------------------------------

def test_6_gemini_invalid_negative_torque():
    """Negative torque from model → validation failure, no value trusted."""
    extracted = _GeminiExtractedRequirements(
        required_torque_nm=-5.0,   # physically impossible
        required_speed_rpm=35.0,
        max_voltage_v=20.0,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.return_value = _make_response(extracted)

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need -5 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_VALIDATION_FAILED"
    assert result.requirements.required_torque_nm is None
    assert len(result.clarifications) > 0


# ---------------------------------------------------------------------------
# TEST 7 & 8 — Provider exceptions (Auth & Rate Limit)
# ---------------------------------------------------------------------------

def test_7_gemini_auth_error():
    """ClientError with 401/403 status \u2192 ERROR_PROVIDER_AUTH."""
    from google.genai import errors
    
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        
        # Mock ClientError with code 401
        err = errors.ClientError(401, {"error": {"message": "Invalid API key"}})
        
        mock_client_instance.models.generate_content.side_effect = err

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_PROVIDER_AUTH"
    assert result.requirements.required_torque_nm is None

def test_8_gemini_rate_limit():
    """ClientError with 429 status \u2192 ERROR_PROVIDER_RATE_LIMIT."""
    from google.genai import errors
    
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        
        err = errors.ClientError(429, {"error": {"message": "Quota exceeded"}})
            
        mock_client_instance.models.generate_content.side_effect = err

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_PROVIDER_RATE_LIMIT"
    assert result.requirements.required_torque_nm is None


# ---------------------------------------------------------------------------
# TEST 9 — Timeout
# ---------------------------------------------------------------------------

def test_9_gemini_timeout():
    """TimeoutError \u2192 ERROR_PROVIDER_TIMEOUT."""
    with patch("app.ai.gemini_parser.genai.Client") as MockClient:
        mock_client_instance = MockClient.return_value
        mock_client_instance.models.generate_content.side_effect = TimeoutError("Timeout")

        parser = GeminiRequirementParser(api_key="fake-key")
        result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_PROVIDER_TIMEOUT"
    assert result.requirements.required_torque_nm is None


# ---------------------------------------------------------------------------
# TEST 10 — Missing API key
# ---------------------------------------------------------------------------

def test_10_gemini_missing_api_key(monkeypatch):
    """No GEMINI_API_KEY \u2192 ERROR_CONFIGURATION_MISSING, no network call."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    parser = GeminiRequirementParser(api_key=None)
    result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_CONFIGURATION_MISSING"
    assert "GEMINI_API_KEY is missing" in result.clarifications[0]
    assert result.requirements.required_torque_nm is None


# ---------------------------------------------------------------------------
# TEST 11 — Extra fields from provider
# ---------------------------------------------------------------------------

def test_11_extra_fields_are_not_trusted():
    """Extra fields are rejected by Pydantic schema validation."""
    from pydantic import ValidationError
    
    declared_fields = set(_GeminiExtractedRequirements.model_fields.keys())
    assert "best_motor_part_number" not in declared_fields

    try:
        obj = _GeminiExtractedRequirements(
            required_torque_nm=1.0,
            required_speed_rpm=35.0,
            max_voltage_v=20.0,
            service_factor=None,
            application=None,
            clarifications=[],
            best_motor_part_number="MAXON-EC-45",   # invented field
        )
        assert not hasattr(obj, "best_motor_part_number")
    except (ValidationError, TypeError):
        pass


# ---------------------------------------------------------------------------
# TEST 12 — Provider selection logic
# ---------------------------------------------------------------------------

def test_12_provider_selection(monkeypatch):
    """Test AI_PROVIDER resolution in get_parser()."""
    from app.ai.requirement_parser import MockRequirementParser
    from app.ai.openai_parser import OpenAIRequirementParser
    from app.ai.gemini_parser import GeminiRequirementParser
    
    # 1. Default (Mock)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    assert isinstance(get_parser(), MockRequirementParser)
    
    # 2. Mock explicit
    monkeypatch.setenv("AI_PROVIDER", "mock")
    assert isinstance(get_parser(), MockRequirementParser)
    
    # 3. OpenAI
    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert isinstance(get_parser(), OpenAIRequirementParser)
    
    # 4. Gemini
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert isinstance(get_parser(), GeminiRequirementParser)
    
    # 5. Unknown
    monkeypatch.setenv("AI_PROVIDER", "unknown")
    with pytest.raises(RuntimeError, match="Unknown AI_PROVIDER 'unknown'"):
        get_parser()
