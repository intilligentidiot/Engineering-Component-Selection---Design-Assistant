import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.seed import seed_database

# Ensure database is seeded before the test client is created
seed_database()

client = TestClient(app)

# ── Manufacturers ────────────────────────────────────────────

def test_list_manufacturers():
    r = client.get("/api/manufacturers")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 3
    names = [m["name"] for m in data]
    assert "Maxon" in names
    assert "Faulhaber" in names
    assert "Dunkermotoren" in names

# ── Motors ───────────────────────────────────────────────────

def test_list_motors():
    r = client.get("/api/motors")
    assert r.status_code == 200
    assert len(r.json()) == 20

def test_list_motors_voltage_filter():
    r = client.get("/api/motors?max_voltage_v=12")
    assert r.status_code == 200
    motors = r.json()
    assert all(m["voltage_v"] <= 12 for m in motors)

def test_get_motor_by_id():
    r = client.get("/api/motors/1")
    assert r.status_code == 200
    motor = r.json()
    assert "part_number" in motor
    assert "data_status" in motor
    assert motor["data_status"] == "ENGINEERING_VERIFIED"

def test_get_motor_not_found():
    r = client.get("/api/motors/9999")
    assert r.status_code == 404

# ── Gearboxes ────────────────────────────────────────────────

def test_list_gearboxes():
    r = client.get("/api/gearboxes")
    assert r.status_code == 200
    assert len(r.json()) == 20

def test_list_gearboxes_ratio_filter():
    r = client.get("/api/gearboxes?min_ratio=10&max_ratio=30")
    assert r.status_code == 200
    gbs = r.json()
    assert all(10 <= g["gear_ratio"] <= 30 for g in gbs)

def test_get_gearbox_by_id():
    r = client.get("/api/gearboxes/1")
    assert r.status_code == 200
    gb = r.json()
    assert "gear_ratio" in gb
    assert "data_status" in gb
    assert gb["data_status"] == "ENGINEERING_VERIFIED"
    assert gb["efficiency"] <= 1.0

def test_get_gearbox_not_found():
    r = client.get("/api/gearboxes/9999")
    assert r.status_code == 404

# ── Recommend still works ────────────────────────────────────

def test_recommend_still_works():
    r = client.post("/api/recommend", json={
        "required_speed_rpm": 50.0,
        "required_torque_nm": 1.0,
        "service_factor": 1.0,
        "max_voltage_v": 24.0,
        "top_n": 5
    })
    assert r.status_code == 200
    data = r.json()
    assert data["count"] > 0
    assert data["discovery_status"] == "NOT_REQUESTED"
    assert len(data["internet_results"]) == 0

def test_recommend_with_internet_discovery():
    r = client.post("/api/recommend", json={
        "required_speed_rpm": 100.0,
        "required_torque_nm": 2.0,
        "service_factor": 1.2,
        "max_voltage_v": 24.0,
        "top_n": 5,
        "include_internet_results": True
    })
    assert r.status_code == 200
    data = r.json()
    assert data["discovery_status"] in ["COMPLETED", "COMPLETED_FROM_CACHE", "COMPLETED_MOCK_FALLBACK", "COMPLETED_LIVE"]
    assert len(data["internet_results"]) > 0
    assert data["internet_results"][0]["source_type"] == "INTERNET"

def test_recommend_scenario_valid_local_and_mock_internet(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    # User debug scenario: 35 RPM, 1 Nm, SF 1.0, 24.0V max, Source B enabled
    # We use 24.0V so that the mock provider's 24V records (Oriental Motor, Nanotec, ElectroCraft)
    # are not entirely skipped by the voltage filter.
    r = client.post("/api/recommend", json={
        "required_speed_rpm": 35.0,
        "required_torque_nm": 1.0,
        "service_factor": 1.0,
        "max_voltage_v": 24.0,
        "top_n": 5,
        "include_internet_results": True
    })
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    # 3 total returned from internet: Oriental Motor (MEETS), Nanotec (MEETS), ElectroCraft (DATA_INCOMPLETE)
    # However, only MEETS candidates count towards internet_count now.
    assert data["internet_count"] == 2
    assert data["discovery_status"] in ["COMPLETED", "COMPLETED_FROM_CACHE", "COMPLETED_MOCK_FALLBACK", "COMPLETED_LIVE"]
    
    manufacturers = [item["manufacturer"] for item in data["internet_results"]]
    assert "Oriental Motor" in manufacturers
    assert "Nanotec" in manufacturers
    assert "ElectroCraft" in manufacturers
    
    meets_count = sum(1 for item in data["internet_results"] if item["engineering_status"] == "MEETS")
    missing_count = sum(1 for item in data["internet_results"] if item["engineering_status"] == "DATA_INCOMPLETE")
    
    assert meets_count == 2
    assert missing_count == 1

def test_recommend_scenario_source_a_zero_source_b_zero():
    # Impossible requirement: 10,000 RPM, 1,000 Nm, 20V max, Source B enabled
    r = client.post("/api/recommend", json={
        "required_speed_rpm": 10000.0,
        "required_torque_nm": 1000.0,
        "service_factor": 2.0,
        "max_voltage_v": 20.0,
        "top_n": 5,
        "include_internet_results": True
    })
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 0
    assert data["internet_count"] == 0


