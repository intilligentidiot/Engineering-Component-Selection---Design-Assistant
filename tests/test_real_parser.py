import pytest
from unittest.mock import patch, MagicMock
import httpx
from app.ai.real_parser import RealRequirementParser

def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    parser = RealRequirementParser(api_key=None)
    result = parser.parse("I need a motor")
    assert result.parser_status == "ERROR_CONFIGURATION_MISSING"
    assert "OPENAI_API_KEY is missing" in result.clarifications[0]

@patch("httpx.Client.post")
def test_valid_parsing(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"requirements": {"required_torque_nm": 1.0, "required_speed_rpm": 35.0, "max_voltage_v": 20.0, "service_factor": null, "application": null}, "clarifications": []}'
            }
        }]
    }
    mock_post.return_value = mock_response

    parser = RealRequirementParser(api_key="fake-key")
    result = parser.parse("I need 1 Nm at 35 RPM, maximum 20 V.")
    
    assert result.parser_status == "PARSED"
    assert result.requirements.required_torque_nm == 1.0
    assert result.requirements.required_speed_rpm == 35.0
    assert result.requirements.max_voltage_v == 20.0
    assert result.requirements.service_factor is None

@patch("httpx.Client.post")
def test_application_extraction(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"requirements": {"required_torque_nm": null, "required_speed_rpm": null, "max_voltage_v": null, "service_factor": null, "application": "conveyor"}, "clarifications": []}'
            }
        }]
    }
    mock_post.return_value = mock_response

    parser = RealRequirementParser(api_key="fake-key")
    result = parser.parse("I need a motor for a conveyor.")
    
    assert result.parser_status == "PARTIAL"
    assert result.requirements.application == "conveyor"
    assert "required_torque_nm" in result.missing_fields

@patch("httpx.Client.post")
def test_missing_torque(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": '{"requirements": {"required_torque_nm": null, "required_speed_rpm": 30.0, "max_voltage_v": null, "service_factor": null, "application": null}, "clarifications": []}'
            }
        }]
    }
    mock_post.return_value = mock_response

    parser = RealRequirementParser(api_key="fake-key")
    result = parser.parse("I need about 30 RPM.")
    
    assert result.parser_status == "PARTIAL"
    assert result.requirements.required_speed_rpm == 30.0
    assert result.requirements.required_torque_nm is None

@patch("httpx.Client.post")
def test_invalid_model_output(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{
            "message": {
                "content": "This is not JSON"
            }
        }]
    }
    mock_post.return_value = mock_response

    parser = RealRequirementParser(api_key="fake-key")
    result = parser.parse("I need 1 Nm")
    
    assert result.parser_status == "ERROR_MALFORMED_RESPONSE"

@patch("httpx.Client.post")
def test_provider_timeout(mock_post):
    mock_post.side_effect = httpx.TimeoutException("Timeout")

    parser = RealRequirementParser(api_key="fake-key")
    result = parser.parse("I need 1 Nm")
    
    assert result.parser_status == "ERROR_PROVIDER_TIMEOUT"

@patch("httpx.Client.post")
def test_provider_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_post.return_value = mock_response

    parser = RealRequirementParser(api_key="fake-key")
    result = parser.parse("I need 1 Nm")
    
    assert result.parser_status == "ERROR_PROVIDER_FAILED"
    assert "HTTP 500" in result.clarifications[0]
