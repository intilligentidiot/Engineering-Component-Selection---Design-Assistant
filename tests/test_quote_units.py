"""The tool converts the user's own words itself; the AI's arithmetic is never used (live-test findings)."""
from unittest.mock import patch, MagicMock

import pytest

from app.engine.quote_units import checked_value
from app.engine.method_eval import MethodPlan, PlanInput, PlanStep


@pytest.mark.parametrize("quote, ai, unit, expected", [
    ("160 bar", 16000000, "Pa", 16000000),          # tool's conversion
    ("160 bar", 16, "MPa", 16),
    ("450 lbf radial load", 2001.6, "N", 2001.70),  # tool's exact value replaces the AI's rounding
    ("C = 3150 lbf", 14.01, "kN", 14.0119),
    ("4 in pulley", 101.6, "mm", 101.6),
    ("60 ft/min", 0.3048, "m/s", 0.3048),
    ("300 lb-ft torque", 406.7, "N·m", 406.745),
    ("200x100x50 mm", 100, "mm", 100),               # every number in "200x100x50 mm" is in mm
    ("200x100x50 mm", 50, "mm", 50),
    ("two welds", 2, "", 2),                         # number words
    ("90% efficient", 0.9, None, 0.9),
    ("1440 rpm", 1440, "rpm", 1440),
    ("2,500 N", 2500, "N", 2500),
])
def test_tool_works_out_the_value(quote, ai, unit, expected):
    assert checked_value(quote, ai, unit) == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize("quote, ai, unit", [
    ("160 bar", 1600, "Pa"),      # AI converted wrongly
    ("400 V", 230, "V"),          # a number the user did not write
    ("4 in pulley", 4, "mm"),     # unit not converted
    ("flat", 0, "deg"),
])
def test_wrong_or_unwritten_numbers_are_not_used(quote, ai, unit):
    assert checked_value(quote, ai, unit) is None


def _gemini(monkeypatch):
    from app.ai import assistant
    assistant._CACHE.clear()
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")


def _reply(parsed):
    m = MagicMock(); m.parsed = parsed
    return m


def _routing():
    return _reply(MagicMock(topic="general", reason="Cylinder sizing."))


def _cylinder(expression="sqrt(4 * F / (pi * P)) * 1000", unit="Pa", value=16000000, quote="160 bar"):
    return MethodPlan(title="Cylinder bore", summary="Bore from force and pressure.", standard=None,
                      inputs=[PlanInput(symbol="F", name="Force", unit="N", value=50000, quote="50 kN"),
                              PlanInput(symbol="P", name="Pressure", unit=unit, value=value, quote=quote)],
                      steps=[PlanStep(symbol="D", name="Bore", unit="mm", expression=expression)],
                      result_symbols=["D"])


def test_method_inputs_use_the_tools_conversion(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    with patch("app.ai.gemini_parser.genai") as genai:
        genai.Client.return_value.models.generate_content.side_effect = [_routing(), _reply(_cylinder(value=1600))]
        r = ask("Hydraulic cylinder to push 50 kN at 160 bar, find bore")
    values = {i.symbol: i.value for i in r.plan.inputs}
    assert values["F"] == 50000 and values["P"] is None    # 1600 Pa is not what the user wrote


def test_rejected_plan_gets_one_retry_with_the_reason(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    bad = _cylinder(expression="sqrt(4 * F / (pi * P)) * 1000 if P > 0 else 0")
    with patch("app.ai.gemini_parser.genai") as genai:
        gen = genai.Client.return_value.models.generate_content
        gen.side_effect = [_routing(), _reply(bad), _reply(_cylinder())]
        r = ask("Hydraulic cylinder to push 50 kN at 160 bar, find bore")
    assert r.status == "OK" and r.plan is not None
    assert "REJECTED" in gen.call_args_list[2].kwargs["config"].system_instruction


def test_non_engineering_question_gets_a_clear_message(monkeypatch):
    from app.ai.assistant import ask
    _gemini(monkeypatch)
    empty = MethodPlan(title="None", summary="Not a calculation.", standard=None, inputs=[], steps=[], result_symbols=[])
    with patch("app.ai.gemini_parser.genai") as genai:
        genai.Client.return_value.models.generate_content.side_effect = [_routing(), _reply(empty)]
        r = ask("what is the weather in Sydney tomorrow")
    assert r.status == "NOT_A_CALCULATION" and "does not look like an engineering" in r.message
