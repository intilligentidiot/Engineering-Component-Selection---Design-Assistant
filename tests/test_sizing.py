"""
Stage 8 — application-based sizing tests.

Every application model has one hand-checked worked example
(docs/STAGE_8_APPLICATION_SIZING_SPEC.md §7). Expected values were calculated
independently from the equations in the spec.
"""
import math
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.engine.sizing import size_application, SizingRequest
from app.engine.sizing.defaults import service_factor_for
from app.engine.fit import compute_fit
from app.engine.recommend import get_recommendations
from app.database.database import Base
from app.database.models import Manufacturer, Motor, Gearbox
from app.main import app

G = 9.80665


def size(**kw):
    return size_application(SizingRequest(**kw))


CONVEYOR = dict(
    application="conveyor",
    material={"name": "Polyurethane", "density_kg_m3": 1200,
              "hardness_scale": "Shore A", "hardness_value": 90},
    part={"shape": "block", "length_mm": 200, "width_mm": 100, "height_mm": 50, "quantity": 20},
    params={"incline_deg": 10, "friction_coefficient": 0.30, "speed_m_s": 0.5,
            "accel_time_s": 0.5, "drive_diameter_mm": 100, "belt_mass_kg": 6},
    duty={"load_class": "moderate", "hours_per_day": 8},
)


# ── Worked examples ──────────────────────────────────────────

def test_conveyor_worked_example_matches_spec():
    r = size(**CONVEYOR)
    assert r.status == "SIZED"
    req = r.requirement
    assert req.required_speed_rpm == pytest.approx(95.493, abs=1e-3)
    assert req.required_torque_nm == pytest.approx(6.9003, abs=1e-4)
    assert req.peak_torque_nm == pytest.approx(8.4003, abs=1e-4)
    assert req.service_factor == 1.25
    assert req.design_torque_nm == pytest.approx(8.6254, abs=1e-4)
    assert req.design_peak_torque_nm == pytest.approx(10.5004, abs=1e-4)
    steps = {s.key: s.result for s in r.steps}
    assert steps["part_mass"] == pytest.approx(1.2)
    assert steps["moving_mass"] == pytest.approx(30.0)
    assert steps["f_gravity"] == pytest.approx(51.087, abs=1e-3)
    assert steps["f_friction"] == pytest.approx(86.919, abs=1e-3)


def test_hoist_worked_example():
    r = size(application="hoist", part={"shape": "mass", "mass_kg": 100},
             params={"speed_m_s": 0.2, "accel_time_s": 1, "drum_diameter_mm": 200},
             duty={"load_class": "moderate", "hours_per_day": 4})
    req = r.requirement
    assert req.required_torque_nm == pytest.approx(100 * G * 0.1)              # 98.07
    assert req.peak_torque_nm == pytest.approx((100 * G + 100 * 0.2) * 0.1)    # 100.07
    assert req.required_speed_rpm == pytest.approx(60 * 0.2 / (math.pi * 0.2))
    assert any("brake" in w for w in r.warnings)


def test_hoist_reeving_and_counterweight():
    r = size(application="hoist", part={"shape": "mass", "mass_kg": 100},
             params={"speed_m_s": 0.2, "accel_time_s": 1, "drum_diameter_mm": 200,
                     "rope_falls": 2, "rope_efficiency": 0.9, "counterweight_kg": 40},
             duty={"load_class": "uniform", "hours_per_day": 8})
    req = r.requirement
    assert req.required_torque_nm == pytest.approx(60 * G / (2 * 0.9) * 0.1)
    assert req.peak_torque_nm == pytest.approx((60 * G + 140 * 0.2) / (2 * 0.9) * 0.1)
    assert req.required_speed_rpm == pytest.approx(60 * 0.4 / (math.pi * 0.2))


def test_rotary_index_worked_example_with_rms():
    r = size(application="rotary_table",
             material={"density_kg_m3": 7850},
             part={"shape": "cylinder", "diameter_mm": 50, "length_mm": 50, "quantity": 8},
             params={"load_arrangement": "parts_at_radius", "load_radius_mm": 300,
                     "table_inertia_kg_m2": 2, "motion_mode": "index",
                     "index_angle_deg": 45, "index_time_s": 1},
             duty={"load_class": "moderate", "hours_per_day": 16, "dwell_time_s": 2})
    m = 8 * 7850 * math.pi * 0.05**2 * 0.05 / 4
    J = m * 0.3**2 + 2
    T_pk = J * 4 * math.radians(45) / 1**2
    req = r.requirement
    assert req.peak_torque_nm == pytest.approx(T_pk)
    assert req.required_torque_nm == pytest.approx(math.sqrt(T_pk**2 * 1 / 3))
    assert req.required_speed_rpm == pytest.approx(15.0)
    assert req.service_factor == 1.5


def test_screw_axis_vertical_with_cycle():
    r = size(application="screw_axis", part={"shape": "mass", "mass_kg": 50},
             params={"axis_angle_deg": 90, "guide_friction": 0.01, "speed_m_s": 0.1,
                     "accel_time_s": 0.2, "screw_lead_mm": 10, "screw_efficiency": 0.9},
             duty={"load_class": "uniform", "hours_per_day": 8, "run_time_s": 2, "dwell_time_s": 3})
    k = 0.01 / (2 * math.pi * 0.9)
    T_run = 50 * G * k
    T_pk = (50 * G + 50 * 0.5) * k
    T_rms = math.sqrt((2 * T_pk**2 * 0.2 + T_run**2 * 2 + T_run**2 * 3) / 5.4)
    req = r.requirement
    assert req.peak_torque_nm == pytest.approx(T_pk)
    assert req.required_torque_nm == pytest.approx(T_rms)
    assert req.required_speed_rpm == pytest.approx(600.0)


def test_screw_efficiency_is_never_assumed():
    r = size(application="screw_axis", part={"shape": "mass", "mass_kg": 50},
             params={"axis_angle_deg": 0, "guide_friction": 0.01, "speed_m_s": 0.1,
                     "accel_time_s": 0.2, "screw_lead_mm": 10},
             duty={"load_class": "uniform", "hours_per_day": 8})
    assert r.status == "REQUIREMENTS_INCOMPLETE"
    assert [m.field for m in r.missing_inputs] == ["params.screw_efficiency"]


def test_rack_pinion_axis():
    r = size(application="rack_pinion_axis", part={"shape": "mass", "mass_kg": 20},
             params={"axis_angle_deg": 0, "guide_friction": 0.05, "speed_m_s": 1,
                     "accel_time_s": 0.5, "pinion_diameter_mm": 60},
             duty={"load_class": "heavy", "hours_per_day": 12})
    req = r.requirement
    assert req.required_torque_nm == pytest.approx(20 * G * 0.05 * 0.03)
    assert req.peak_torque_nm == pytest.approx((20 * G * 0.05 + 20 * 2) * 0.03)
    assert req.service_factor == 2.0


def test_winding_two_operating_points_and_envelope():
    r = size(application="winding", material={"density_kg_m3": 920},
             params={"web_tension_n": 100, "speed_m_s": 1, "accel_time_s": 5,
                     "core_diameter_mm": 76, "full_roll_diameter_mm": 600, "roll_width_mm": 1000},
             duty={"load_class": "uniform", "hours_per_day": 20})
    assert [p.label for p in r.operating_points] == ["Full roll", "Empty core"]
    full, core = r.operating_points
    assert full.run_torque_nm == pytest.approx(30.0)
    assert core.run_torque_nm == pytest.approx(3.8)
    assert core.speed_rpm == pytest.approx(60 / (math.pi * 0.076))
    # Envelope: full-roll torque up to core speed (conservative)
    assert r.requirement.required_speed_rpm == pytest.approx(core.speed_rpm)
    assert r.requirement.required_torque_nm == pytest.approx(30.0)
    assert any("speed-controlled" in w for w in r.warnings)


# ── Safety rules ─────────────────────────────────────────────

def test_hardness_recorded_but_never_used():
    with_h = size(**CONVEYOR)
    no_h = size(**{**CONVEYOR, "material": {"name": "Polyurethane", "density_kg_m3": 1200}})
    assert with_h.requirement == no_h.requirement
    assert with_h.material_notes and "not used" in with_h.material_notes[0]


def test_missing_inputs_are_all_reported_at_once():
    r = size(application="conveyor")
    assert r.status == "REQUIREMENTS_INCOMPLETE"
    fields = {m.field for m in r.missing_inputs}
    assert {"part.shape", "params.incline_deg", "params.friction_coefficient",
            "params.speed_m_s", "params.accel_time_s", "params.drive_diameter_mm",
            "duty.load_class", "duty.hours_per_day"} <= fields
    assert r.requirement is None


def test_missing_density_blocks_calculation():
    r = size(**{**CONVEYOR, "material": {"name": "Unknown"}})
    assert r.status == "REQUIREMENTS_INCOMPLETE"
    assert "material.density_kg_m3" in {m.field for m in r.missing_inputs}


def test_invalid_input_rejected():
    r = size(**{**CONVEYOR, "params": {**CONVEYOR["params"], "friction_coefficient": -1}})
    assert r.status == "INVALID_INPUT"
    assert r.errors


def test_defaults_are_listed_as_assumptions():
    r = size(**CONVEYOR)
    text = " ".join(r.assumptions)
    assert "efficiency 1.0" in text and "extra process forces" in text


def test_service_factor_table_and_override():
    assert service_factor_for("uniform", 2) == 0.8
    assert service_factor_for("moderate", 10) == 1.25
    assert service_factor_for("heavy", 11) == 2.0
    r = size(**{**CONVEYOR, "duty": {"load_class": "moderate", "hours_per_day": 8,
                                      "service_factor_override": 1.6}})
    assert r.requirement.service_factor == 1.6
    assert {"sf_table", "sf_used"} <= {s.key for s in r.steps}


def test_zero_running_torque_falls_back_to_peak():
    r = size(application="rotary_table",
             params={"load_arrangement": "custom_inertia", "load_inertia_kg_m2": 1,
                     "motion_mode": "continuous", "target_speed_rpm": 30, "accel_time_s": 1},
             duty={"load_class": "uniform", "hours_per_day": 8})
    assert r.requirement.required_torque_nm == r.requirement.peak_torque_nm > 0


# ── Fit indicator ────────────────────────────────────────────

def test_fit_indicator_scoring():
    assert compute_fit(1.2, 1.0, 100, 100, 50)["percent"] == 100
    oversized = compute_fit(4.0, 1.0, 100, 100, 50)["percent"]
    overspeed = compute_fit(1.2, 1.0, 140, 100, 50)["percent"]
    assert oversized < 100 and overspeed < 100


# ── Selection engine: peak torque checks ─────────────────────

@pytest.fixture()
def tiny_db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    mfg = Manufacturer(name="TestMfg")
    db.add(mfg)
    db.commit()
    common = dict(manufacturer_id=mfg.id, voltage_v=24, continuous_power_w=100,
                  nominal_speed_rpm=3000, nominal_torque_nm=0.3, source="test",
                  verification_status="x", verification_date="2026-10-14")
    db.add_all([
        Motor(part_number="WITH_PEAK", max_torque_nm=0.6, **common),
        Motor(part_number="NO_PEAK", max_torque_nm=None, **common),
        Gearbox(manufacturer_id=mfg.id, part_number="GB30", gear_ratio=30, efficiency=0.8,
                max_input_speed_rpm=5000, max_output_torque_nm=20, source="test",
                verification_status="x", verification_date="2026-10-14"),
    ])
    db.commit()
    yield db
    db.close()


def _run(db, peak):
    # continuous output = 0.3 × 30 × 0.8 = 7.2 Nm ; output speed 100 rpm
    return {r["motor"]["part_number"]: r for r in get_recommendations(
        db, required_speed_rpm=95, required_torque_nm=5, service_factor=1.0,
        max_voltage_v=24, top_n=10, peak_torque_nm=peak)}


def test_peak_covered_by_continuous_output_meets_without_peak_data(tiny_db):
    res = _run(tiny_db, peak=7.0)
    assert res["NO_PEAK"]["engineering_status"] == "MEETS"
    assert res["WITH_PEAK"]["engineering_status"] == "MEETS"
    assert res["WITH_PEAK"]["fit"]["percent"] > 0


def test_peak_unverifiable_is_data_incomplete_not_assumed(tiny_db):
    # Peak 12 Nm: WITH_PEAK gives 0.6 × 30 × 0.8 = 14.4 Nm -> MEETS;
    # NO_PEAK has only 7.2 Nm continuous and no recorded peak -> DATA_INCOMPLETE
    res = _run(tiny_db, peak=12.0)
    assert res["WITH_PEAK"]["engineering_status"] == "MEETS"
    assert res["NO_PEAK"]["engineering_status"] == "DATA_INCOMPLETE"
    assert res["NO_PEAK"]["fit"] is None
    assert list(res)[0] == "WITH_PEAK"  # MEETS ranked first


def test_peak_above_verified_ratings_excluded(tiny_db):
    res = _run(tiny_db, peak=15.0)   # above motor peak (14.4) for WITH_PEAK
    assert "WITH_PEAK" not in res
    res = _run(tiny_db, peak=25.0)   # above gearbox rating (20) for all
    assert res == {}


def test_meets_candidates_ranked_by_fit():
    from app.database.database import SessionLocal
    from app.database.seed import seed_database
    seed_database()
    db = SessionLocal()
    try:
        res = get_recommendations(db, required_speed_rpm=47.7, required_torque_nm=0.049, service_factor=1.0,
                                  max_voltage_v=24, top_n=10, peak_torque_nm=0.069)
    finally:
        db.close()
    fits = [r["fit"]["percent"] for r in res if r["engineering_status"] == "MEETS"]
    assert len(fits) > 1 and fits == sorted(fits, reverse=True)


# ── API ──────────────────────────────────────────────────────

def test_size_endpoint():
    client = TestClient(app)
    r = client.post("/api/size", json=CONVEYOR)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "SIZED"
    assert data["requirement"]["design_torque_nm"] == pytest.approx(8.6254, abs=1e-4)
    assert data["steps"][0]["substitution"]


def test_size_endpoint_reports_missing():
    client = TestClient(app)
    data = client.post("/api/size", json={"application": "winding"}).json()
    assert data["status"] == "REQUIREMENTS_INCOMPLETE"
    assert any(m["field"] == "params.web_tension_n" for m in data["missing_inputs"])
