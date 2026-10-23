"""
Whole-project calculation plans (app/engine/project.py) and their entry from
the main box. The shredder template is hand-checked; AI plans use a patched SDK.
"""
import math
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.engine.project import shredder_template, validate_project, evaluate_project, ProjectCalc, Link
from app.engine.method_eval import PlanStep
from app.ai.assistant import ask
from app.main import app

client = TestClient(app)
FULL = dict(tau_s=25, t=5, b=20, z=2, D=300, n=20, N_sh=2, SF=1.75, L=600, tau_allow=40, life_req=20000, V=400)


@pytest.fixture(autouse=True)
def mock_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")


def _results(r):
    return {s.symbol: s.result for c in r.calculations for s in c.steps}


def test_shredder_template_is_valid():
    assert validate_project(shredder_template()) == []


def test_shredder_hand_checked_chain():
    r = evaluate_project(shredder_template(), FULL)
    v = _results(r)
    assert v["F_b"] == pytest.approx(25 * 5 * 20)             # 2500 N
    assert v["F"] == pytest.approx(5000)
    assert v["T_sh"] == pytest.approx(750)                    # 5000 N × 0.15 m
    assert v["T_tot"] == pytest.approx(1500)
    assert v["P"] == pytest.approx(1500 * 2 * math.pi * 20 / 60)
    M, T = 750, 750
    assert v["d"] == pytest.approx((16 * 1000 / (math.pi * 40) * math.hypot(1.75 * M, 1.75 * T)) ** (1 / 3))
    bearing = next(c for c in r.calculations if c.id == "bearing_life").bearing
    assert bearing["min_dynamic_rating_kn"] == pytest.approx(2500 * (60 * 20 * 20000 / 1e6) ** 0.3 / 1000)


def test_missing_information_waits_but_other_steps_run():
    r = evaluate_project(shredder_template(), {"tau_s": 25, "t": 5, "b": 20, "z": 2})
    status = {c.id: c.status for c in r.calculations}
    assert status["cutting_force"] == "DONE"
    assert status["torque"] == "WAITING"
    torque = next(c for c in r.calculations if c.id == "torque")
    assert any("Cutter (rotor) diameter" in w for w in torque.waiting_for)
    assert "D" in r.missing_inputs and "life_req" not in r.missing_inputs   # optional


def test_motor_step_uses_checked_selection():
    from app.database.database import SessionLocal
    from app.database.seed import seed_database
    seed_database()
    db = SessionLocal()
    try:
        # tiny shredder → small motor that the built-in list can supply
        # F = 1·3·3 = 9 N; T = 9 N × 0.02 m = 0.18 N·m at 38 rpm (same size as the small conveyor sample)
        vals = dict(FULL, tau_s=1, t=3, b=3, z=1, D=40, n=38, N_sh=1, SF=1.0, V=24)
        r = evaluate_project(shredder_template(), vals, db)
    finally:
        db.close()
    motor = next(c for c in r.calculations if c.id == "motor")
    assert motor.status == "DONE" and motor.motors
    assert all(m["status"] == "MEETS" for m in motor.motors[:1])


def test_unsafe_or_broken_ai_plan_is_rejected():
    p = shredder_template()
    p.calculations.append(ProjectCalc(id="x", title="Bad", purpose="x",
                                      steps=[PlanStep(symbol="q", name="q", unit="", expression="__import__('os')")]))
    p.calculations.append(ProjectCalc(id="y", title="Bad link", purpose="x", kind="bearing_life", bearing_type="ball",
                                      links=[Link(param="radial_load_n", symbol="nope"), Link(param="speed_rpm", symbol="n")]))
    problems = validate_project(p)
    assert any("Bad'" in x for x in problems) and any("nope" in x for x in problems)


def test_shredder_question_opens_project_with_values_from_text():
    r = ask("I'm designing a twin-shaft plastic shredder, 300 mm rotor, 20 rpm, 400 V, material 5 mm thick")
    assert r.topic == "project" and r.status == "OK" and r.project.origin == "TEMPLATE"
    given = {i.symbol: i.value for i in r.project.inputs if i.value is not None}
    assert given == {"D": 300, "n": 20, "V": 400, "t": 5, "N_sh": 2}


def test_other_project_without_ai_is_honest(monkeypatch):
    from app.ai import assistant
    monkeypatch.setattr(assistant, "_mock_route", lambda text: assistant.TopicRouting(topic="project", reason="x"))
    r = ask("I'm designing a bottle capping machine")
    assert r.status == "AI_NOT_CONFIGURED" and r.project is None


def test_ai_project_value_must_be_in_text(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    plan = shredder_template()
    plan.origin = "TEMPLATE"
    by = {i.symbol: i for i in plan.inputs}
    by["n"].value, by["n"].quote = 20, "20 rpm"          # in the text
    by["D"].value, by["D"].quote = 500, "500 mm rotor"   # invented — not in the text
    routing = MagicMock(); routing.parsed = MagicMock(topic="project", reason="A shredder project.")
    planned = MagicMock(); planned.parsed = plan
    with patch("app.ai.gemini_parser.genai") as genai:
        genai.Client.return_value.models.generate_content.side_effect = [routing, planned]
        r = ask("new shredder project at 20 rpm")
    by = {i.symbol: i for i in r.project.inputs}
    assert r.project.origin == "AI"
    assert by["n"].value == 20 and by["D"].value is None


def test_project_evaluate_endpoint():
    out = client.post("/api/project-evaluate", json={"plan": shredder_template().model_dump(), "values": FULL}).json()
    assert out["status"] == "EVALUATED"
    assert {c["id"]: c["status"] for c in out["calculations"]}["shaft"] == "DONE"


# ── Bulk belt conveyor (ISO 5048) — engineer's test case ─────

from app.engine.conveyor_template import bulk_conveyor_template
from app.ai.sizing_parser import MockSizingParser

ENGINEER_TEXT = (
    "I'm designing a heavy-duty belt conveyor drive pulley for iron ore, belt width 1200 mm, belt speed 2.5 m/s, "
    "pulley diameter 630 mm, center-to-center distance 150 meters\n\n"
    "Total equivalent belt tension\nRequired drive power\nPulley shaft torque\nShaft bending moment\n"
    "Allowable bending stress of the shaft material\n\ni need this value or information"
)
CONV = dict(Q=1000, v=2.5, L=150, H=0, D=630, m_B=25, m_R=20, f=0.02, C=1.6, F_S2=0, mu=0.25, theta=180,
            eta=0.9, a=300, Sy=350, n_s=2.5, SF=1.25, V=400, life_req=40000)


def test_bulk_conveyor_template_hand_checked():
    assert validate_project(bulk_conveyor_template()) == []
    v = _results(evaluate_project(bulk_conveyor_template(), CONV))
    m_G = 1000 / (3.6 * 2.5)
    F_U = 1.6 * 0.02 * 150 * 9.80665 * (20 + 2 * 25 + m_G)
    assert v["F_U"] == pytest.approx(F_U)                               # ≈ 8525 N
    assert v["P_A"] == pytest.approx(F_U * 2.5 / 1000)                  # ≈ 21.3 kW
    assert v["T"] == pytest.approx(F_U * 0.315)                         # ≈ 2685 N·m
    T2 = F_U / (math.exp(0.25 * math.pi) - 1)
    assert v["R"] == pytest.approx(F_U + 2 * T2)                        # at 180° wrap R = T1 + T2
    assert v["M"] == pytest.approx((F_U + 2 * T2) / 2 * 0.3)
    assert v["sigma_allow"] == pytest.approx(140)


def test_engineer_text_opens_conveyor_plan_with_requested_results():
    r = ask(ENGINEER_TEXT)
    assert r.topic == "project" and r.project.title.startswith("Bulk belt conveyor")
    given = {i.symbol: i.value for i in r.project.inputs if i.value is not None}
    assert given == {"v": 2.5, "D": 630, "L": 150, "B": 1200}
    assert [(q.text, q.symbol) for q in r.project.requested] == [
        ("Total equivalent belt tension", "R"), ("Required drive power", "P_A"), ("Pulley shaft torque", "T"),
        ("Shaft bending moment", "M"), ("Allowable bending stress of the shaft material", "sigma_allow")]


def test_small_parts_conveyor_still_uses_motor_sizing():
    assert ask("Conveyor moving 20 plastic blocks 200x100x50 mm, belt speed 0.5 m/s").topic == "motor_sizing"


def test_material_name_not_taken_from_unrelated_words():
    r = MockSizingParser().parse("conveyor, shaft material\n\ni need this value")
    assert not any(v.path == "material.name" for v in r.values)


FULL_ENGINEER_QUERY = """I'm designing a belt conveyor for iron ore, capacity 1000 t/h, belt speed 2.5 m/s, belt width 1200 mm, centre-to-centre distance 150 m, horizontal.
Drive pulley diameter 630 mm, wrap angle 180°, pulley friction 0.25 (rubber lagging, wet conditions).
Belt mass 25 kg/m, idler rotating mass 20 kg/m, no special resistances, length coefficient C = 1.6.
Pulley shaft: yield strength 350 MPa, safety factor 2.5, bearing-to-hub distance 300 mm.
Service factor 1.25, 400 V supply, bearing life 40000 hours.

Total equivalent belt tension
Required drive power
Pulley shaft torque
Shaft bending moment
Allowable bending stress of the shaft material

i need this value or information"""


def test_full_query_with_two_items_left_out_is_completed_by_suggestions():
    p = ask(FULL_ENGINEER_QUERY).project
    assert [i.symbol for i in p.inputs if i.value is None and i.typical_value is not None] == ["f", "eta"]
    assert [i.symbol for i in p.inputs if i.value is None and i.typical_value is None and not i.optional] == []
    vals = {i.symbol: (i.value if i.value is not None else i.typical_value) for i in p.inputs}
    got = _results(evaluate_project(p, vals))
    answers = {q.text: got[q.symbol] for q in p.requested}
    assert answers["Total equivalent belt tension"] == pytest.approx(22814, abs=1)
    assert answers["Required drive power"] == pytest.approx(21.31, abs=0.01)
    assert answers["Pulley shaft torque"] == pytest.approx(2685.5, abs=0.5)
    assert answers["Shaft bending moment"] == pytest.approx(3422.1, abs=0.5)
    assert answers["Allowable bending stress of the shaft material"] == pytest.approx(140)


def test_project_motor_step_can_include_internet_results(monkeypatch):
    import app.engine.discover as disc
    seen = {}
    def fake(**kw):
        seen.update(kw)
        return [{"manufacturer": "Maker", "product_name": "Gearmotor", "part_number": "GM-1",
                 "engineering_status": "DATA_INCOMPLETE", "fit": None, "product_url": "https://example.com",
                 "performance": {}}]
    monkeypatch.setattr(disc, "discover_and_evaluate_components", fake)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    from app.engine.conveyor_template import bulk_conveyor_template
    from app.database.database import SessionLocal
    db = SessionLocal()
    try:
        r = evaluate_project(bulk_conveyor_template(), CONV, db=db, include_internet=True)
    finally:
        db.close()
    motor = next(c for c in r.calculations if c.id == "motor")
    assert motor.internet_source == "MOCK" and motor.internet[0]["part_number"] == "GM-1"
    assert seen["required_torque_nm"] == pytest.approx(next(s.result for c in r.calculations for s in c.steps if s.symbol == "T"))


# ── Estimate helpers ─────────────────────────────────────────

from app.engine.method_eval import MethodPlan, PlanInput, evaluate_method as _eval_method


def _run_estimate(helper, values):
    plan = MethodPlan(title=helper.title, summary=helper.note,
                      inputs=[PlanInput(symbol=x.symbol, name=x.name, unit=x.unit) for x in helper.inputs],
                      steps=[PlanStep(symbol="est_value", name="estimate", unit="", expression=helper.expression)],
                      result_symbols=["est_value"])
    return _eval_method(plan, values).results[0].result


def test_belt_mass_estimate():
    m_B = next(i for i in bulk_conveyor_template().inputs if i.symbol == "m_B")
    # 1.2 m wide × 0.016 m thick × 1150 kg/m³ = 22.08 kg/m
    assert _run_estimate(m_B.estimate, {"B_e": 1200, "t_b": 16, "rho_b": 1150}) == pytest.approx(22.08)
    assert next(x for x in m_B.estimate.inputs if x.symbol == "B_e").from_input == "B"


def test_idler_mass_estimate():
    m_R = next(i for i in bulk_conveyor_template().inputs if i.symbol == "m_R")
    # 3 × 8 kg / 1.2 m + 1 × 20 kg / 3 m = 20 + 6.67 = 26.67 kg/m
    assert _run_estimate(m_R.estimate, {"m_rc": 8, "z_c": 3, "a_c": 1.2, "m_rr": 20, "z_r": 1, "a_r": 3}) == pytest.approx(26.667, abs=1e-3)


def test_asme_allowable_shear_estimate():
    tau = next(i for i in shredder_template().inputs if i.symbol == "tau_allow")
    # min(0.3 × 350, 0.18 × 600) × 0.75 = min(105, 108) × 0.75 = 78.75 MPa
    assert _run_estimate(tau.estimate, {"Sy_e": 350, "Sut_e": 600, "k_kw": 0.75}) == pytest.approx(78.75)


def test_broken_estimate_formula_is_rejected():
    p = bulk_conveyor_template()
    m_B = next(i for i in p.inputs if i.symbol == "m_B")
    m_B.estimate.expression = "B_e * unknown_thing"
    assert any("unknown_thing" in x for x in validate_project(p))


# ── AI plans are repaired, not thrown away (hydraulic press feedback) ─────

from app.engine.project import ProjectPlan, ProjectInput, repair_project


def _press_plan():
    return ProjectPlan(
        title="Portable 10 t hydraulic press", machine="portable 10 tonne hydraulic press", summary="x",
        inputs=[ProjectInput(symbol="F_t", name="Press force", unit="t", source_hint="user", value=10, quote="10 tonne"),
                ProjectInput(symbol="p", name="System pressure", unit="MPa", source_hint="pump datasheet", typical_value=20)],
        calculations=[
            # a bearing check with no links at all — the case seen live
            ProjectCalc(id="pump_bearing", title="Pump Shaft Bearing Life", purpose="x", kind="bearing_life", bearing_type="ball"),
            ProjectCalc(id="bore", title="Cylinder bore", purpose="x", steps=[
                PlanStep(symbol="F_N", name="Force", unit="N", expression="F_t * 1000 * 9.81"),
                PlanStep(symbol="d_bore", name="Bore", unit="mm", expression="sqrt(4 * F_N / (pi * p))")]),
            ProjectCalc(id="frame", title="Frame stress", purpose="x", steps=[
                PlanStep(symbol="sigma", name="Stress", unit="MPa", expression="F_N / A_col")]),   # A_col never defined
        ])


def test_ai_plan_missing_module_links_become_inputs():
    plan = _press_plan()
    assert repair_project(plan) == []
    ids = [c.id for c in plan.calculations]
    assert ids == ["bore", "pump_bearing"]                       # broken one left out, module check runs last
    asked = {i.symbol: i for i in plan.inputs}
    assert "pump_bearing_radial_load_n" in asked and "pump_bearing_speed_rpm" in asked
    assert asked["pump_bearing_radial_load_n"].value is None    # asked for, never guessed
    assert asked["pump_bearing_speed_rpm"].unit == "rpm"
    assert any("Frame stress" in l and "Left out" in l for l in plan.limitations)
    r = evaluate_project(plan, {"F_t": 10, "p": 20, "pump_bearing_radial_load_n": 500, "pump_bearing_speed_rpm": 1450})
    assert r.status == "EVALUATED"
    assert round(_results(r)["d_bore"], 1) == round(math.sqrt(4 * 98100 / (math.pi * 20)), 1)


def test_ai_plan_with_nothing_usable_is_still_rejected():
    plan = _press_plan()
    plan.calculations = [plan.calculations[2]]
    assert repair_project(plan)        # problems remain → not used
