"""
AI_PROVIDER=claude — the Anthropic SDK is mocked; no network, no real key.
The same safety rules apply as for Gemini/OpenAI: values without the user's own
words are dropped, and the AI never produces result numbers.
"""
from unittest.mock import patch, MagicMock
import pytest

from app.ai.assistant import ask
from app.ai.claude_client import claude_structured
from app.ai.claude_parser import ClaudeRequirementParser
from app.ai.openai_parser import _AIExtractedRequirements
from app.ai.provider import get_parser
from app.ai.sizing_parser import (ClaudeSizingParser, SizingExtraction, FieldQuote, ProviderError,
                                  get_sizing_parser)
from app.engine.method_eval import MethodPlan, PlanInput, PlanStep

PATCH = "app.ai.claude_client.anthropic.Anthropic"


def _resp(parsed, stop_reason="end_turn"):
    r = MagicMock()
    r.parsed_output = parsed
    r.stop_reason = stop_reason
    return r


@pytest.fixture
def claude_env(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_EFFORT", raising=False)


def test_provider_selection(claude_env):
    assert isinstance(get_sizing_parser(), ClaudeSizingParser)
    assert isinstance(get_parser(), ClaudeRequirementParser)


def test_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError) as e:
        claude_structured(_AIExtractedRequirements, "sys", "text")
    assert e.value.status == "ERROR_CONFIGURATION_MISSING"


def test_request_shape(claude_env):
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.return_value = _resp(_AIExtractedRequirements(required_speed_rpm=35))
        out = claude_structured(_AIExtractedRequirements, "the system text", "35 rpm")
    kw = client.return_value.beta.messages.parse.call_args.kwargs
    assert out.required_speed_rpm == 35
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_format"] is _AIExtractedRequirements
    assert kw["system"] == "the system text"
    assert kw["messages"] == [{"role": "user", "content": "35 rpm"}]
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]


def test_model_and_effort_from_env(claude_env, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("CLAUDE_EFFORT", "low")
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.return_value = _resp(_AIExtractedRequirements())
        claude_structured(_AIExtractedRequirements, "s", "t")
    kw = client.return_value.beta.messages.parse.call_args.kwargs
    assert kw["model"] == "claude-sonnet-5-5" and kw["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_unusable_answer_is_an_error(claude_env, stop):
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.return_value = _resp(None, stop_reason=stop)
        with pytest.raises(ProviderError):
            claude_structured(_AIExtractedRequirements, "s", "t")


def test_sizing_values_are_verified_against_user_words(claude_env):
    ex = SizingExtraction(application="conveyor", speed_m_s=0.5, payload_mass_kg=99,
                          quotes=[FieldQuote(field="application", quote="conveyor"),
                                  FieldQuote(field="speed_m_s", quote="0.5 m/s"),
                                  FieldQuote(field="payload_mass_kg", quote="99 kg")])   # not in the text
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.return_value = _resp(ex)
        r = ClaudeSizingParser().parse("a conveyor at 0.5 m/s")
    fields = {v.path for v in r.values}
    assert "params.speed_m_s" in fields and not any("mass" in f for f in fields)


def test_advanced_tab_parser(claude_env):
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.return_value = _resp(
            _AIExtractedRequirements(required_torque_nm=1, required_speed_rpm=35, max_voltage_v=20))
        r = ClaudeRequirementParser().parse("I need 1 Nm at 35 RPM, maximum 20 V")
    assert r.parser_status == "PARSED" and r.requirements.required_torque_nm == 1


def test_auth_error_becomes_clear_message(claude_env):
    import anthropic, httpx
    err = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=httpx.Request("POST", "https://x")), body=None)
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.side_effect = err
        r = ClaudeRequirementParser().parse("1 Nm")
    assert r.parser_status == "ERROR_PROVIDER_AUTH" and "ANTHROPIC_API_KEY" in r.clarifications[0]


def test_general_question_plan(claude_env):
    plan = MethodPlan(
        title="Solid shaft diameter for torsion", standard="τ = 16T / πd³", summary="Minimum diameter.",
        inputs=[PlanInput(symbol="T", name="Torque", unit="N·m", value=50, quote="50 Nm"),
                PlanInput(symbol="tau_allow", name="Allowable shear stress", unit="MPa")],
        steps=[PlanStep(symbol="d", name="Minimum shaft diameter", unit="mm",
                        expression="(16 * T * 1000 / (pi * tau_allow)) ** (1/3)")])
    routing = MagicMock(topic="general", reason="Shaft sizing.")
    with patch(PATCH) as client:
        client.return_value.beta.messages.parse.side_effect = [_resp(routing), _resp(plan)]
        r = ask("shaft diameter for 50 Nm torque, steel")
    assert r.topic == "general" and r.status == "OK"
    assert next(i for i in r.plan.inputs if i.symbol == "T").value == 50
