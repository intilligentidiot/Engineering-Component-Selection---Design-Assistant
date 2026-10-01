"""
Stage 7.2 — OpenAI Parser Tests

All tests are fully deterministic.
No real OpenAI API calls are made.
The openai client is mocked at the exact call site inside openai_parser.py.

Tests:
  1. Valid provider response → correct structured requirements
  2. Application extraction → conveyor
  3. Missing torque → remains None
  4. Missing service factor → remains None
  5. Invalid model output (negative torque) → validation failure
  6. Provider exception (API error) → controlled error status
  7. Timeout → controlled timeout status
  8. Missing API key → configuration error
  9. MockRequirementParser still works (regression)
 10. /api/parse-requirements endpoint compatibility (via TestClient)
 11. AI values cannot bypass Pydantic/application validation
 12. Extra/unexpected fields from provider are ignored
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.ai.openai_parser import OpenAIRequirementParser, _AIExtractedRequirements
from app.ai.requirement_parser import MockRequirementParser
from app.api.routes import RecommendRequest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers — build a mock ParsedResponse whose .output_parsed is our schema
# ---------------------------------------------------------------------------

def _make_response(extracted: _AIExtractedRequirements) -> MagicMock:
    """Return a MagicMock that mimics openai.ParsedResponse[_AIExtractedRequirements]."""
    mock_resp = MagicMock()
    mock_resp.output_parsed = extracted
    return mock_resp


# ---------------------------------------------------------------------------
# TEST 1 — Valid provider returns correct structured requirements
# ---------------------------------------------------------------------------

def test_1_openai_valid_full_requirements():
    """OpenAI provider returns 1 Nm, 35 RPM, 20 V → correct structured requirements."""
    extracted = _AIExtractedRequirements(
        required_torque_nm=1.0,
        required_speed_rpm=35.0,
        max_voltage_v=20.0,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch(
        "app.ai.openai_parser.OpenAI"
    ) as MockClient:
        MockClient.return_value.responses.parse.return_value = _make_response(extracted)

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
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

def test_2_openai_application_extraction():
    """Natural-language application 'motor for a conveyor' → application = 'conveyor'."""
    extracted = _AIExtractedRequirements(
        required_torque_nm=None,
        required_speed_rpm=None,
        max_voltage_v=None,
        service_factor=None,
        application="conveyor",
        clarifications=[],
    )
    with patch("app.ai.openai_parser.OpenAI") as MockClient:
        MockClient.return_value.responses.parse.return_value = _make_response(extracted)

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
        result = parser.parse("I need a motor for a conveyor.")

    assert result.requirements.application == "conveyor"
    assert result.requirements.required_torque_nm is None
    assert "required_torque_nm" in result.missing_fields
    assert result.parser_status == "PARTIAL"


# ---------------------------------------------------------------------------
# TEST 3 — Missing torque
# ---------------------------------------------------------------------------

def test_3_openai_missing_torque():
    """'about 30 RPM' → torque remains None, speed captured."""
    extracted = _AIExtractedRequirements(
        required_torque_nm=None,
        required_speed_rpm=30.0,
        max_voltage_v=None,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.openai_parser.OpenAI") as MockClient:
        MockClient.return_value.responses.parse.return_value = _make_response(extracted)

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
        result = parser.parse("I need about 30 RPM.")

    assert result.requirements.required_torque_nm is None
    assert result.requirements.required_speed_rpm == 30.0
    assert "required_torque_nm" in result.missing_fields
    assert result.parser_status == "PARTIAL"


# ---------------------------------------------------------------------------
# TEST 4 — Missing service factor remains None
# ---------------------------------------------------------------------------

def test_4_openai_missing_service_factor():
    """Service factor not mentioned → remains None; no invention."""
    extracted = _AIExtractedRequirements(
        required_torque_nm=1.0,
        required_speed_rpm=35.0,
        max_voltage_v=20.0,
        service_factor=None,     # not stated
        application=None,
        clarifications=[],
    )
    with patch("app.ai.openai_parser.OpenAI") as MockClient:
        MockClient.return_value.responses.parse.return_value = _make_response(extracted)

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
        result = parser.parse("I need 1 Nm at 35 RPM, maximum 20 V.")

    assert result.requirements.service_factor is None
    assert result.parser_status == "PARSED"


# ---------------------------------------------------------------------------
# TEST 5 — Invalid model output (negative engineering value)
# ---------------------------------------------------------------------------

def test_5_openai_invalid_negative_torque():
    """Negative torque from model → validation failure, no value trusted."""
    extracted = _AIExtractedRequirements(
        required_torque_nm=-5.0,   # physically impossible
        required_speed_rpm=35.0,
        max_voltage_v=20.0,
        service_factor=None,
        application=None,
        clarifications=[],
    )
    with patch("app.ai.openai_parser.OpenAI") as MockClient:
        MockClient.return_value.responses.parse.return_value = _make_response(extracted)

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
        result = parser.parse("I need -5 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_VALIDATION_FAILED"
    assert result.requirements.required_torque_nm is None
    assert len(result.clarifications) > 0


# ---------------------------------------------------------------------------
# TEST 6 — Provider exception / API status error → controlled error
# ---------------------------------------------------------------------------

def test_6_openai_provider_api_error():
    """APIStatusError (e.g. HTTP 500) → ERROR_PROVIDER_FAILED, FastAPI does not crash."""
    from openai import APIStatusError
    import httpx

    mock_request  = httpx.Request("POST", "https://api.openai.com/v1/responses")
    mock_response_obj = MagicMock()
    mock_response_obj.status_code = 500
    mock_response_obj.headers = {}

    api_error = APIStatusError(
        message="Internal Server Error",
        response=mock_response_obj,
        body={"error": {"message": "Internal Server Error"}},
    )

    with patch("app.ai.openai_parser.OpenAI") as MockClient:
        MockClient.return_value.responses.parse.side_effect = api_error

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
        result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_PROVIDER_FAILED"
    assert "HTTP 500" in result.clarifications[0]
    assert result.requirements.required_torque_nm is None


# ---------------------------------------------------------------------------
# TEST 7 — Timeout → controlled timeout status
# ---------------------------------------------------------------------------

def test_7_openai_timeout():
    """APITimeoutError → ERROR_PROVIDER_TIMEOUT, no crash."""
    from openai import APITimeoutError

    with patch("app.ai.openai_parser.OpenAI") as MockClient:
        MockClient.return_value.responses.parse.side_effect = APITimeoutError(
            request=MagicMock()
        )

        parser = OpenAIRequirementParser(api_key="fake-key", model="gpt-4o-mini")
        result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_PROVIDER_TIMEOUT"
    assert result.requirements.required_torque_nm is None


# ---------------------------------------------------------------------------
# TEST 8 — Missing API key → configuration error
# ---------------------------------------------------------------------------

def test_8_openai_missing_api_key(monkeypatch):
    """No OPENAI_API_KEY → ERROR_CONFIGURATION_MISSING, no network call."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    parser = OpenAIRequirementParser(api_key=None)
    result = parser.parse("I need 1 Nm at 35 RPM.")

    assert result.parser_status == "ERROR_CONFIGURATION_MISSING"
    assert "OPENAI_API_KEY is missing" in result.clarifications[0]
    assert result.requirements.required_torque_nm is None


# ---------------------------------------------------------------------------
# TEST 9 — MockRequirementParser still works (regression)
# ---------------------------------------------------------------------------

def test_9_mock_parser_still_works():
    """Stage 7.1 MockRequirementParser continues to work correctly."""
    parser = MockRequirementParser()
    result = parser.parse("I need 1 Nm at 35 RPM, maximum 20 V.")

    assert result.parser_status == "PARSED"
    assert result.requirements.required_torque_nm == 1.0
    assert result.requirements.required_speed_rpm == 35.0
    assert result.requirements.max_voltage_v == 20.0


# ---------------------------------------------------------------------------
# TEST 10 — /api/parse-requirements endpoint backward compatibility
# ---------------------------------------------------------------------------

def test_10_api_endpoint_compatibility(monkeypatch):
    """
    /api/parse-requirements returns HTTP 200 with the correct schema when
    AI_PROVIDER=mock.  No real provider is called.
    """
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Import after monkeypatch so the provider module re-reads the env
    from app.main import app
    client = TestClient(app)

    r = client.post("/api/parse-requirements", json={"text": "I need 1 Nm at 35 RPM, maximum 20 V."})
    assert r.status_code == 200

    data = r.json()
    assert data["parser_status"] == "PARSED"
    assert data["requirements"]["required_torque_nm"] == 1.0
    assert data["requirements"]["required_speed_rpm"] == 35.0
    assert data["requirements"]["max_voltage_v"] == 20.0
    assert "missing_fields" in data
    assert "clarifications" in data


# ---------------------------------------------------------------------------
# TEST 11 — AI values cannot bypass Pydantic/application validation
# ---------------------------------------------------------------------------

def test_11_ai_values_pass_through_pydantic_validation():
    """
    Values from the AI parser must pass RecommendRequest Pydantic validation
    before reaching the engineering engine.
    Negative or zero values must be rejected by RecommendRequest.
    """
    # A valid AI-parsed result should pass RecommendRequest validation
    valid_request = RecommendRequest(
        required_speed_rpm=35.0,
        required_torque_nm=1.0,
        max_voltage_v=20.0,
        service_factor=1.0,
        top_n=5,
    )
    assert valid_request.required_torque_nm == 1.0

    # Zero or negative values must be rejected
    with pytest.raises(ValidationError):
        RecommendRequest(
            required_speed_rpm=-1.0,     # invalid
            required_torque_nm=1.0,
            max_voltage_v=20.0,
            service_factor=1.0,
            top_n=5,
        )

    with pytest.raises(ValidationError):
        RecommendRequest(
            required_speed_rpm=35.0,
            required_torque_nm=0.0,      # invalid (gt=0)
            max_voltage_v=20.0,
            service_factor=1.0,
            top_n=5,
        )


# ---------------------------------------------------------------------------
# TEST 12 — Extra fields from provider do not become trusted engineering data
# ---------------------------------------------------------------------------

def test_12_extra_fields_are_not_trusted():
    """
    The _AIExtractedRequirements schema is closed (Pydantic model).
    Any unexpected fields the model may return are stripped automatically
    and never reach the engineering engine.
    """
    # Construct with known fields — the schema enforces no extras
    extracted = _AIExtractedRequirements(
        required_torque_nm=1.0,
        required_speed_rpm=35.0,
        max_voltage_v=20.0,
        service_factor=None,
        application=None,
        clarifications=[],
    )

    # The schema object must not have any attribute beyond the declared fields
    declared_fields = set(_AIExtractedRequirements.model_fields.keys())
    extra_field_name = "best_motor_part_number"   # something the LLM might invent
    assert extra_field_name not in declared_fields

    # Attempting to build the schema with an extra field should be rejected
    # (Pydantic v2 with model_config forbid or simply ignores extras by default)
    try:
        obj = _AIExtractedRequirements(
            required_torque_nm=1.0,
            required_speed_rpm=35.0,
            max_voltage_v=20.0,
            service_factor=None,
            application=None,
            clarifications=[],
            best_motor_part_number="MAXON-EC-45",   # invented field
        )
        # If Pydantic silently ignored the extra field, confirm it is not accessible
        assert not hasattr(obj, "best_motor_part_number")
    except (ValidationError, TypeError):
        # If Pydantic raises on extras, that is also acceptable
        pass
