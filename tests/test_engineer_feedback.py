"""
Engineer feedback round: bearing life (ISO 281), suggested values for missing
inputs, and understanding machine names by their motion.
"""
import pytest
from fastapi.testclient import TestClient

from app.engine.bearing import bearing_life, BearingRequest
from app.engine.sizing import size_application, SizingRequest
from app.engine.sizing.suggestions import suggestions_for
from app.ai.sizing_parser import MockSizingParser, SizingRequirementParser, SizingExtraction, FieldQuote
from app.main import app

client = TestClient(app)


# ── Bearing life (ISO 281) — hand-checked examples ───────────

def test_ball_bearing_life_and_requirement_check():
    # P = Fr = 2000 N; L10 = (14000/2000)^3 = 343 Mrev; L10h = 343e6 / (60·1500) = 3811 h
    r = bearing_life(BearingRequest(bearing_type="ball", radial_load_n=2000, speed_rpm=1500,
                                    dynamic_rating_kn=14, required_life_h=20000))
    assert r.equivalent_load_n == 2000
    assert r.life_h == pytest.approx(3811.1, abs=0.1)
    assert r.status == "DOES_NOT_MEET"
    assert [s.key for s in r.steps] == ["exponent", "p_eq", "l10", "l10h"]


def test_minimum_rating_for_required_life():
    # C_min = 2000 · (60·1500·20000/1e6)^(1/3) = 2000 · 1800^(1/3) = 24.33 kN
    r = bearing_life(BearingRequest(bearing_type="ball", radial_load_n=2000, speed_rpm=1500, required_life_h=20000))
    assert r.status == "MIN_RATING_CALCULATED"
    assert r.min_dynamic_rating_kn == pytest.approx(24.329, abs=1e-3)


def test_roller_bearing_with_axial_load_and_reliability():
    # P = 0.4·5000 + 1.6·1000 = 3600 N; L10h = (60000/3600)^(10/3)·1e6/(60·500); × a1(99 %) = 0.25
    r = bearing_life(BearingRequest(bearing_type="roller", radial_load_n=5000, axial_load_n=1000,
                                    x_factor=0.4, y_factor=1.6, speed_rpm=500, dynamic_rating_kn=60,
                                    reliability_pct=99))
    expected = 0.25 * (60000 / 3600) ** (10 / 3) * 1e6 / (60 * 500)
    assert r.equivalent_load_n == pytest.approx(3600)
    assert r.life_h == pytest.approx(expected)


def test_bearing_x_y_and_rating_never_assumed():
    r = bearing_life(BearingRequest(bearing_type="ball", radial_load_n=2000, axial_load_n=500, speed_rpm=1500))
    assert r.status == "REQUIREMENTS_INCOMPLETE"
    assert {m.field for m in r.missing_inputs} == {"x_factor", "y_factor", "dynamic_rating_kn"}


def test_bearing_endpoint():
    data = client.post("/api/bearing-life", json={"bearing_type": "ball", "radial_load_n": 2000,
                                                  "speed_rpm": 1500, "dynamic_rating_kn": 14}).json()
    assert data["status"] == "LIFE_CALCULATED"
    assert data["life_h"] == pytest.approx(3811.1, abs=0.1)


# ── Suggested values ─────────────────────────────────────────

def test_suggestions_never_cover_machine_geometry():
    for app_name in ["conveyor", "hoist", "rotary_table", "screw_axis", "rack_pinion_axis", "winding"]:
        keys = set(suggestions_for(app_name))
        assert not any(k.endswith(("_mm", "speed_m_s", "mass_kg", "density_kg_m3", "web_tension_n")) for k in keys)


def test_screw_efficiency_suggestion_depends_on_screw_type():
    assert suggestions_for("screw_axis", "ball screw")["params.screw_efficiency"]["value"] == 0.9
    assert suggestions_for("screw_axis", "lead screw")["params.screw_efficiency"]["value"] == 0.2


def test_incomplete_result_carries_suggestions_and_used_list_is_reported():
    base = dict(application="conveyor", part={"shape": "mass", "mass_kg": 10},
                params={"incline_deg": 0, "speed_m_s": 0.5, "drive_diameter_mm": 100})
    r = size_application(SizingRequest(**base))
    assert r.status == "REQUIREMENTS_INCOMPLETE"
    assert r.suggestions["params.friction_coefficient"]["value"] == 0.5

    filled = dict(base, params={**base["params"], "friction_coefficient": 0.5, "accel_time_s": 1.0},
                  duty={"load_class": "moderate", "hours_per_day": 8},
                  suggested=["params.friction_coefficient", "params.accel_time_s", "duty.load_class", "duty.hours_per_day"])
    r = size_application(SizingRequest(**filled))
    assert r.status == "SIZED"
    assert len(r.suggested_used) == 4
    assert any(line.startswith("Friction coefficient: 0.5 (suggested)") for line in r.suggested_used)


# ── Machine names understood by motion ───────────────────────

@pytest.mark.parametrize("text,app_name", [
    ("belt feeder moving 5 kg parts", "conveyor"),
    ("winch lifting 50 kg", "hoist"),
    ("dial table with 6 fixtures", "rotary_table"),
    ("electric cylinder pushing 20 kg", "screw_axis"),
    ("reel for wire, 50 N tension", "winding"),
])
def test_other_machine_names_map_to_motion(text, app_name):
    r = MockSizingParser().parse(text)
    assert {v.path: v.value for v in r.values}["application"] == app_name
    assert r.machine_as_written and r.machine_explanation


@pytest.mark.parametrize("text,name", [("bearing load 2000 N at 1500 rpm", "bearing"),
                                       ("bucket elevator for grain", "bucket elevator"), ("pump 2 kW", "pump")])
def test_unsupported_machines_are_explained_not_forced(text, name):
    r = MockSizingParser().parse(text)
    assert r.parser_status == "UNSUPPORTED_MACHINE"
    assert r.unsupported_machine == name
    assert not any(v.path == "application" for v in r.values)
    assert r.unsupported_message


def test_bearing_message_points_to_bearing_tab():
    r = MockSizingParser().parse("bearing load 2000 N")
    assert "Bearing Life" in r.unsupported_message


def test_ai_machine_name_must_appear_in_text():
    class Fake(SizingRequirementParser):
        name = "fake"
        def extract(self, text):
            return SizingExtraction(application="conveyor", machine_as_written="belt feeder",
                                    machine_explanation="A belt feeder moves parts along a belt.",
                                    quotes=[FieldQuote(field="application", quote="feeder")])
    r = Fake().parse("a feeder for screws")
    assert r.machine_as_written is None          # "belt feeder" is not in the text
    assert {v.path: v.value for v in r.values}["application"] == "conveyor"
