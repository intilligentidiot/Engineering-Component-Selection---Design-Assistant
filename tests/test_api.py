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
