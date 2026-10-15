"""
Stage 8.x — plain-text reader for the sizing form.

No real AI calls: the mock parser is deterministic and the Gemini / OpenAI
SDKs are patched at their call sites.
"""
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.ai.sizing_parser import (
    MockSizingParser, SizingRequirementParser, SizingExtraction, FieldQuote,
    GeminiSizingParser, OpenAISizingParser, get_sizing_parser, ProviderError,
)
from app.engine.sizing import size_application, SizingRequest
from app.main import app

CONVEYOR_TEXT = (
    "Conveyor moving 20 polyurethane blocks 200x100x50 mm, density 1200 kg/m3, Shore A 90. "
    "Belt speed 0.5 m/s, reaches full speed in 0.5 s, 100 mm drive pulley, 10° incline, friction 0.3. "
    "Moderate shocks, 8 hours a day, 24 V supply."
)


def as_dict(result):
    return {v.path: v.value for v in result.values}


def to_request(result, **extra_params):
    body = {"material": {}, "part": {}, "params": {}, "duty": {}}
    for v in result.values:
        grp, _, key = v.path.partition(".")
        if grp == "application":
            body["application"] = v.value
        elif grp in body:
            body[grp][key] = v.value
    body["params"].update(extra_params)
    return SizingRequest(**body)


# ── Mock (rule-based) extraction ─────────────────────────────

def test_conveyor_sentence_fills_form_and_sizes_like_worked_example():
    r = MockSizingParser().parse(CONVEYOR_TEXT)
    d = as_dict(r)
    assert r.parser_status == "PARSED"
    assert d["application"] == "conveyor"
    assert (d["part.length_mm"], d["part.width_mm"], d["part.height_mm"]) == (200, 100, 50)
    assert d["part.quantity"] == 20
    assert d["material.density_kg_m3"] == 1200
    assert d["params.incline_deg"] == 10
    assert d["limits.max_voltage_v"] == 24
    res = size_application(to_request(r, belt_mass_kg=6))
    assert res.requirement.design_torque_nm == pytest.approx(8.6254, abs=1e-4)


def test_every_value_has_a_verbatim_quote():
    r = MockSizingParser().parse(CONVEYOR_TEXT)
    for v in r.values:
        assert v.quote.lower() in CONVEYOR_TEXT.lower()


@pytest.mark.parametrize("text,expected", [
    ("Lift a 100 kg load at 0.2 m/s with a 200 mm drum, 2 falls",
     {"application": "hoist", "part.mass_kg": 100, "params.drum_diameter_mm": 200, "params.rope_falls": 2}),
    ("vertical ball screw axis, 50 kg payload, 10 mm lead, efficiency 90%",
     {"application": "screw_axis", "params.axis_angle_deg": 90, "params.screw_lead_mm": 10, "params.screw_efficiency": 0.9}),
    ("Winder, 100 N tension, line speed 60 m/min, core 76 mm, full roll diameter 600 mm, 1000 mm wide, 24/7",
     {"application": "winding", "params.speed_m_s": 1.0, "params.web_tension_n": 100,
      "params.core_diameter_mm": 76, "params.full_roll_diameter_mm": 600, "duty.hours_per_day": 24}),
    ("Indexing turntable, 8 parts around a circle at radius 300 mm, 45° steps in 1 s",
     {"application": "rotary_table", "params.motion_mode": "index", "params.load_radius_mm": 300,
      "params.index_angle_deg": 45, "params.index_time_s": 1}),
    ("density 1.2 g/cm3, 500 mm/s", {"material.density_kg_m3": 1200, "params.speed_m_s": 0.5}),
])
def test_common_phrasings(text, expected):
    d = as_dict(MockSizingParser().parse(text))
    for k, v in expected.items():
        assert d[k] == pytest.approx(v) if isinstance(v, float) else d[k] == v, k


def test_density_is_never_guessed_from_material_name():
    r = MockSizingParser().parse("Conveyor for blocks made of steel, 200x100x50 mm")
    d = as_dict(r)
    assert d["material.name"] == "steel"
    assert "material.density_kg_m3" not in d
    assert any("density of steel" in c for c in r.clarifications)


def test_no_density_question_when_part_mass_given():
    r = MockSizingParser().parse("Conveyor carrying parts made of rubber, 5 kg each")
    assert not any("density" in c for c in r.clarifications)


def test_nothing_found_gives_guidance():
    r = MockSizingParser().parse("I need something to move boxes")
    assert r.parser_status == "NOTHING_FOUND"
    assert r.clarifications


# ── Verification guards (apply to every provider) ────────────

class _FakeProvider(SizingRequirementParser):
    name = "fake"

    def __init__(self, extraction):
        self._ex = extraction

    def extract(self, text):
        return self._ex


def test_value_with_invented_quote_is_rejected():
    ex = SizingExtraction(
        application="conveyor", density_kg_m3=7850, speed_m_s=0.5,
        quotes=[FieldQuote(field="application", quote="conveyor"),
                FieldQuote(field="density_kg_m3", quote="steel is 7850 kg/m3"),   # not in text
                FieldQuote(field="speed_m_s", quote="0.5 m/s")],
    )
    r = _FakeProvider(ex).parse("A conveyor of steel parts at 0.5 m/s")
    d = as_dict(r)
    assert "material.density_kg_m3" not in d
    assert d["params.speed_m_s"] == 0.5
    assert any(x.field == "material.density_kg_m3" for x in r.rejected)


def test_value_without_quote_or_number_is_rejected():
    ex = SizingExtraction(friction_coefficient=0.3, speed_m_s=1.0,
                          quotes=[FieldQuote(field="speed_m_s", quote="fast")])
    r = _FakeProvider(ex).parse("It runs fast on a slider bed")
    assert as_dict(r) == {}
    assert {x.field for x in r.rejected} == {"params.friction_coefficient", "params.speed_m_s"}


def test_invalid_category_and_out_of_range_rejected():
    ex = SizingExtraction(application="mixer", guide_friction=30,
                          quotes=[FieldQuote(field="application", quote="mixer"),
                                  FieldQuote(field="guide_friction", quote="friction 30")])
    r = _FakeProvider(ex).parse("mixer with friction 30")
    assert as_dict(r) == {}
    assert len(r.rejected) == 2


def test_provider_error_is_controlled():
    class Broken(SizingRequirementParser):
        name = "broken"
        def extract(self, text):
            raise RuntimeError("boom")
    r = Broken().parse("conveyor at 0.5 m/s")
    assert r.parser_status == "ERROR_UNEXPECTED"
    assert r.values == []


# ── Real providers (mocked SDKs) ─────────────────────────────

def _extraction():
    return SizingExtraction(application="conveyor", speed_m_s=0.5,
                            quotes=[FieldQuote(field="application", quote="conveyor"),
                                    FieldQuote(field="speed_m_s", quote="0.5 m/s")])


def test_gemini_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = GeminiSizingParser(api_key=None).parse("conveyor at 0.5 m/s")
    assert r.parser_status == "ERROR_CONFIGURATION_MISSING"


def test_gemini_structured_output_is_verified():
    resp = MagicMock()
    resp.parsed = _extraction()
    with patch("app.ai.gemini_parser.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = resp
        r = GeminiSizingParser(api_key="k").parse("a conveyor at 0.5 m/s")
    assert as_dict(r) == {"application": "conveyor", "params.speed_m_s": 0.5}
    kwargs = genai.Client.return_value.models.generate_content.call_args.kwargs
    assert kwargs["contents"] == "a conveyor at 0.5 m/s"


def test_openai_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = OpenAISizingParser(api_key=None).parse("conveyor at 0.5 m/s")
    assert r.parser_status == "ERROR_CONFIGURATION_MISSING"


def test_openai_structured_output_is_verified():
    resp = MagicMock()
    resp.output_parsed = _extraction()
    with patch("app.ai.openai_parser.OpenAI") as client:
        client.return_value.responses.parse.return_value = resp
        r = OpenAISizingParser(api_key="k").parse("a conveyor at 0.5 m/s")
    assert as_dict(r) == {"application": "conveyor", "params.speed_m_s": 0.5}


def test_provider_selection(monkeypatch):
    for name, cls in [("mock", MockSizingParser), ("gemini", GeminiSizingParser), ("openai", OpenAISizingParser)]:
        monkeypatch.setenv("AI_PROVIDER", name)
        assert isinstance(get_sizing_parser(), cls)
    monkeypatch.setenv("AI_PROVIDER", "nope")
    with pytest.raises(RuntimeError):
        get_sizing_parser()


# ── API ──────────────────────────────────────────────────────

def test_parse_sizing_endpoint(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    data = TestClient(app).post("/api/parse-sizing", json={"text": CONVEYOR_TEXT}).json()
    assert data["parser_status"] == "PARSED"
    assert data["provider"] == "mock"
    paths = {v["path"] for v in data["values"]}
    assert {"application", "params.speed_m_s", "material.density_kg_m3"} <= paths
