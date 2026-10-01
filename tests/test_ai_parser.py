import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.routes import RecommendRequest
from pydantic import ValidationError

client = TestClient(app)

def test_1_full_specs():
    """TEST 1: 'I need 1 Nm at 35 RPM, maximum 20 V.'"""
    r = client.post("/api/parse-requirements", json={
        "text": "I need 1 Nm at 35 RPM, maximum 20 V."
    })
    assert r.status_code == 200
    data = r.json()
    reqs = data["requirements"]
    
    assert reqs["required_torque_nm"] == 1.0
    assert reqs["required_speed_rpm"] == 35.0
    assert reqs["max_voltage_v"] == 20.0
    assert data["parser_status"] == "PARSED"
    assert len(data["missing_fields"]) == 0

def test_2_speed_and_torque_variant():
    """TEST 2: 'I need 35 RPM and 1 N-m.'"""
    r = client.post("/api/parse-requirements", json={
        "text": "I need 35 RPM and 1 N-m."
    })
    assert r.status_code == 200
    data = r.json()
    reqs = data["requirements"]
    
    assert reqs["required_torque_nm"] == 1.0
    assert reqs["required_speed_rpm"] == 35.0
    assert reqs["max_voltage_v"] is None
    assert "max_voltage_v" in data["missing_fields"]
    assert data["parser_status"] == "PARTIAL"

def test_3_only_application():
    """TEST 3: 'I need a motor for a conveyor.'"""
    r = client.post("/api/parse-requirements", json={
        "text": "I need a motor for a conveyor."
    })
    assert r.status_code == 200
    data = r.json()
    reqs = data["requirements"]
    
    assert reqs["application"] == "conveyor"
    assert reqs["required_torque_nm"] is None
    assert reqs["required_speed_rpm"] is None
    assert reqs["max_voltage_v"] is None
    
    assert "required_torque_nm" in data["missing_fields"]
    assert "required_speed_rpm" in data["missing_fields"]
    assert "max_voltage_v" in data["missing_fields"]
    assert data["parser_status"] == "PARTIAL"

def test_4_only_speed():
    """TEST 4: 'I need about 30 RPM.'"""
    r = client.post("/api/parse-requirements", json={
        "text": "I need about 30 RPM."
    })
    assert r.status_code == 200
    data = r.json()
    reqs = data["requirements"]
    
    assert reqs["required_speed_rpm"] == 30.0
    assert reqs["required_torque_nm"] is None
    assert "required_torque_nm" in data["missing_fields"]
    assert data["parser_status"] == "PARTIAL"

def test_5_service_factor():
    """TEST 5: 'I need 1 Nm at 35 RPM with a service factor of 1.5.'"""
    r = client.post("/api/parse-requirements", json={
        "text": "I need 1 Nm at 35 RPM with a service factor of 1.5."
    })
    assert r.status_code == 200
    data = r.json()
    reqs = data["requirements"]
    
    assert reqs["required_torque_nm"] == 1.0
    assert reqs["required_speed_rpm"] == 35.0
    assert reqs["service_factor"] == 1.5

def test_6_unsupported_unit():
    """TEST 6: Unsupported/ambiguous unit or value -> clear clarification/error -> no guessing."""
    r = client.post("/api/parse-requirements", json={
        "text": "I need 10 lb-ft of torque."
    })
    assert r.status_code == 200
    data = r.json()
    
    assert data["parser_status"] == "NEEDS_CLARIFICATION"
    assert len(data["clarifications"]) > 0
    assert "Unsupported unit 'lb-ft'" in data["clarifications"][0]
    assert data["requirements"]["required_torque_nm"] is None

def test_7_validation_flow():
    """TEST 7: AI/parser output goes through existing validation."""
    r = client.post("/api/parse-requirements", json={
        "text": "I need 1 Nm at 35 RPM, maximum 20 V."
    })
    data = r.json()
    reqs = data["requirements"]
    
    # Try to build the RecommendRequest object which applies existing Pydantic validation
    try:
        validated_request = RecommendRequest(
            required_speed_rpm=reqs["required_speed_rpm"],
            required_torque_nm=reqs["required_torque_nm"],
            max_voltage_v=reqs["max_voltage_v"],
            # If SF is None in parser output, let RecommendRequest use its default (1.0)
            service_factor=reqs["service_factor"] if reqs["service_factor"] else 1.0,
            top_n=5
        )
    except ValidationError:
        pytest.fail("AI parsed output failed existing Pydantic validation layer!")
        
    assert validated_request.required_torque_nm == 1.0
    assert validated_request.required_speed_rpm == 35.0
    assert validated_request.max_voltage_v == 20.0
    assert validated_request.service_factor == 1.0 # default fallback
