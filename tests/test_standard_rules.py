"""One selected standard: results come from that standard only; nothing is borrowed from another one."""
from unittest.mock import patch, MagicMock

import pytest

from app.engine.standard_rules import GENERAL, allowed, foreign_codes
from app.engine.project import shredder_template, evaluate_project
from app.engine.method_eval import MethodPlan, PlanInput, PlanStep


@pytest.mark.parametrize("method, selected, ok", [
    ("ISO 281", "ANSI/ABMA Std 11", True),          # same method, different name
    ("ISO 281", "ANSI/ABMA Std 9", True),
    ("ISO 281", "BS ISO 281", True),
    ("ISO 281", "AS 1403", False),
    ("ISO 281", GENERAL, False),
    ("", "AS 1403", True),                           # basic physics runs under any standard
    ("", GENERAL, True),
    (f"{GENERAL} — max shear", GENERAL, True),
    (f"{GENERAL} — max shear", "AS 1403", False),
    ("DIN 743-1:2000-05", "DIN 743", True),
    ("ISO 5048 / DIN 22101", "CEMA — Belt Conveyors for Bulk Materials", False),
    ("IS 800:2007", "IS 807", False),
])
def test_which_methods_run_under_the_selected_standard(method, selected, ok):
    assert allowed(method, selected) is ok


def test_other_standards_cited_in_steps_are_found():
    assert foreign_codes("DIN 743-1, Clause 5.2; key from DIN 6885; steel EN 42CrMo4", "DIN 743") == ["DIN 6885"]
    assert foreign_codes("per ISO 281", GENERAL) == ["ISO 281"]


def _shredder_values():
    return {"tau_s": 40, "t": 3, "b": 8, "z": 4, "D": 150, "n": 15, "N_sh": 4, "SF": 1.75, "L": 610,
            "tau_allow": 80, "life_req": 20000, "V": 230}


@pytest.mark.parametrize("selected, shaft, bearing", [
    ("ANSI/ABMA Std 11", "NOT_DEFINED", "DONE"),
    (GENERAL, "DONE", "NOT_DEFINED"),
    ("AS 1403", "NOT_DEFINED", "NOT_DEFINED"),
])
def test_project_steps_from_another_standard_are_not_defined(selected, shaft, bearing):
    plan = shredder_template()
    r = evaluate_project(plan, _shredder_values(), standard=selected)
    status = {c.id: res.status for c, res in zip(plan.calculations, r.calculations)}
    assert status["cutting_force"] == status["torque"] == status["power"] == "DONE"   # physics
    assert status["shaft"] == shaft and status["bearing_life"] == bearing
    if bearing == "NOT_DEFINED":
        res = r.calculations[[c.id for c in plan.calculations].index("bearing_life")]
        assert res.errors[0].startswith(f"Not defined in {selected}")


def test_no_standard_given_keeps_every_step():   # API callers that send no standard
    plan = shredder_template()
    r = evaluate_project(plan, _shredder_values())
    assert all(res.status != "NOT_DEFINED" for res in r.calculations)


def _gemini(monkeypatch):
    from app.ai import assistant
    assistant._CACHE.clear()
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")


def _reply(parsed):
    m = MagicMock(); m.parsed = parsed
    return m


def _plan(standard, note):
    return MethodPlan(title="Shaft", summary="Shaft size.", standard=standard,
                      inputs=[PlanInput(symbol="T", name="Torque", unit="N·m", value=50, quote="50 Nm"),
                              PlanInput(symbol="tau", name="Allowable shear stress", unit="MPa", typical_value=None,
                                        typical_note="From DIN 743 Table 3 — enter from your copy of the standard")],
                      steps=[PlanStep(symbol="d", name="Diameter", unit="mm", note=note,
                                      expression="(16 * T * 1000 / (pi * tau)) ** (1/3)")],
                      result_symbols=["d"])


def test_ai_plan_citing_another_standard_is_retried_then_refused(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    routing = _reply(MagicMock(topic="general", reason="Shaft."))
    borrowed = _plan("DIN 743", "DIN 743 clause 5; keyway factor from DIN 6885")
    with patch("app.ai.gemini_parser.genai") as genai:
        gen = genai.Client.return_value.models.generate_content
        gen.side_effect = [routing, _reply(borrowed), _reply(borrowed)]
        r = ask("shaft diameter for 50 Nm torque", standard="DIN 743")
    assert r.status == "STANDARD_MISMATCH" and r.plan is None and "DIN 6885" in r.message
    assert "REJECTED" in gen.call_args_list[2].kwargs["config"].system_instruction


def test_ai_plan_from_the_selected_standard_is_shown(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    with patch("app.ai.gemini_parser.genai") as genai:
        genai.Client.return_value.models.generate_content.side_effect = [
            _reply(MagicMock(topic="general", reason="Shaft.")), _reply(_plan("DIN 743-1:2000", "DIN 743-1 clause 5"))]
        r = ask("shaft diameter for 50 Nm torque", standard="DIN 743")
    assert r.status == "OK" and r.standard == "DIN 743"


def test_ai_says_not_defined_in_the_standard(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    nd = MethodPlan(title="Weld", summary="-", standard="NOT DEFINED IN DIN 743", inputs=[], steps=[],
                    result_symbols=[], limitations=["DIN 743 covers shafts, not welds."])
    with patch("app.ai.gemini_parser.genai") as genai:
        genai.Client.return_value.models.generate_content.side_effect = [
            _reply(MagicMock(topic="general", reason="Weld.")), _reply(nd)]
        r = ask("fillet weld for 40 kN", standard="DIN 743")
    assert r.status == "NOT_DEFINED" and "covers shafts, not welds" in r.message


def test_bearing_life_is_not_defined_under_a_non_bearing_standard(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    with patch("app.ai.gemini_parser.genai") as genai:
        gen = genai.Client.return_value.models.generate_content
        gen.side_effect = [_reply(MagicMock(topic="bearing_life", reason="Bearing."))]
        r = ask("ball bearing 2000 N at 1500 rpm", standard="AS 1403")
    assert r.status == "NOT_DEFINED" and gen.call_count == 1


def test_each_step_can_have_its_own_standard():
    plan = shredder_template()
    r = evaluate_project(plan, _shredder_values(), standard="ANSI/ABMA Std 11",
                         step_standards={"shaft": GENERAL})
    by_id = {c.id: res for c, res in zip(plan.calculations, r.calculations)}
    assert by_id["shaft"].status == "DONE" and by_id["shaft"].standard == GENERAL
    assert by_id["bearing_life"].status == "DONE" and by_id["bearing_life"].standard == "ANSI/ABMA Std 11"
    assert by_id["cutting_force"].standard == "ANSI/ABMA Std 11"


def test_not_defined_step_lists_only_standards_that_define_it():
    plan = shredder_template()
    r = evaluate_project(plan, _shredder_values(), standard="AS 1403")
    by_id = {c.id: res for c, res in zip(plan.calculations, r.calculations)}
    assert by_id["shaft"].options == [GENERAL]
    assert by_id["bearing_life"].options == ["ISO 281", "ANSI/ABMA Std 9", "ANSI/ABMA Std 11", "BS ISO 281"]
    # a step standard that does not define the step is still refused
    r = evaluate_project(plan, _shredder_values(), standard="AS 1403", step_standards={"shaft": "DIN 743"})
    assert {c.id: res.status for c, res in zip(plan.calculations, r.calculations)}["shaft"] == "NOT_DEFINED"


def test_step_standards_reach_the_api():
    from fastapi.testclient import TestClient
    from app.main import app
    plan = shredder_template()
    body = {"plan": plan.model_dump(), "values": _shredder_values(), "standard": "ANSI/ABMA Std 11",
            "step_standards": {"shaft": GENERAL}}
    calcs = TestClient(app).post("/api/project-evaluate", json=body).json()["calculations"]
    assert {c["id"]: c["status"] for c in calcs}["shaft"] == "DONE"
