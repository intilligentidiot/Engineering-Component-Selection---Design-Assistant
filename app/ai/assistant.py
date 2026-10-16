"""
One entry point for any engineering question typed by the user.

  1. route   — decide which kind of calculation is being asked for:
               motor_sizing  → checked motor + gearbox sizing module
               bearing_life  → checked ISO 281 bearing module
               general       → no checked module: the AI chooses the method
                               (MethodPlan) and the tool evaluates it
  2. extract — read the values the user actually wrote (each must be quoted
               verbatim from their text, or it is dropped)

The AI never produces result numbers: checked modules and the deterministic
method evaluator (app/engine/method_eval.py) do all arithmetic.

Provider follows AI_PROVIDER (mock | gemini | openai). The mock provider is
rule-based and cannot build methods for new topics.
"""
import os
import re
import logging
from typing import Optional, List, Dict, Any, Type

from pydantic import BaseModel, Field

from app.ai.sizing_parser import get_sizing_parser, SizingParseResult, ProviderError, _norm, _MACHINE_NAMES
from app.engine.method_eval import MethodPlan, validate_plan
from app.engine.project import ProjectPlan, validate_project, shredder_template, map_requested
from app.engine.conveyor_template import bulk_conveyor_template

logger = logging.getLogger(__name__)

TOPICS = ("project", "motor_sizing", "bearing_life", "general")


# ─────────────────────────────────────────────────────────────
# Structured-output call shared by the real providers
# ─────────────────────────────────────────────────────────────

def _provider() -> str:
    return os.environ.get("AI_PROVIDER", "mock").strip().lower()


def call_structured(schema: Type[BaseModel], system: str, text: str) -> BaseModel:
    provider = _provider()
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "GEMINI_API_KEY is missing.")
        from app.ai import gemini_parser as gp
        if not gp._GENAI_AVAILABLE:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "google-genai SDK is not installed.")
        client = gp.genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), contents=text,
            config=gp.genai_types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                                        response_schema=schema, temperature=0.0))
        if getattr(resp, "parsed", None) is not None:
            return resp.parsed
        import json
        return schema(**json.loads(resp.text or "{}"))
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "OPENAI_API_KEY is missing.")
        from app.ai import openai_parser as op
        if not op._OPENAI_AVAILABLE:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "openai SDK is not installed.")
        client = op.OpenAI(api_key=key)
        resp = client.responses.parse(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                                      input=[{"role": "system", "content": system}, {"role": "user", "content": text}],
                                      text_format=schema)
        return resp.output_parsed
    raise ProviderError("AI_NOT_CONFIGURED", "AI is not switched on for this tool.")


# ─────────────────────────────────────────────────────────────
# 1. Routing
# ─────────────────────────────────────────────────────────────

class TopicRouting(BaseModel):
    topic: str = Field(..., description="project, motor_sizing, bearing_life or general.")
    reason: str = Field(..., description="One plain-English sentence explaining the choice.")


ROUTER_INSTRUCTION = (
    "Decide what kind of engineering calculation the user is asking for. "
    "project: the user describes a whole machine or project they are designing or modifying (e.g. 'I am building a "
    "shredding machine', 'new project: a bottle capper') and needs to know what to calculate and what information "
    "is needed — several calculations for several parts; also when the user lists several specific results they "
    "need (e.g. belt tension, drive power, shaft torque, bending moment), and for bulk-material belt conveyors. "
    "motor_sizing: choosing or sizing a motor / gearbox / drive for a machine that moves something "
    "(conveyor, lift, turntable, linear axis, winder, or any machine with such a motion). "
    "bearing_life: rolling bearing life, load rating or bearing selection (ISO 281, L10). "
    "general: any other engineering calculation (shafts, keys, belts, gears, bolts, springs, pumps, fans, "
    "beams, heat, flow...). Reply with the topic and one short reason."
)

_BEARING_RE = re.compile(r"\bbearings?\b|\bL10h?\b|ISO\s*281|rating life|dynamic load rating", re.IGNORECASE)
_MOTOR_RE = re.compile(r"\b(?:motors?|gear ?box(?:es)?|gear ?motors?)\b", re.IGNORECASE)


_PROJECT_RE = re.compile(r"\bshred(?:der|ding|s)?\b", re.IGNORECASE)
# Bulk-material belt conveyors need the ISO 5048 / DIN 22101 method, not the unit-load conveyor model
_BULK_RE = re.compile(r"\b(?:ore|coal|sand|gravel|grain|aggregates?|bulk|clinker|limestone|cement|fertili[sz]er|"
                      r"idlers?|belt width)\b|t/h|\btph\b|tonn?es? per hour|tons? per hour|"
                      r"cent(?:er|re)[- ]to[- ]cent(?:er|re)", re.IGNORECASE)
_CONVEYOR_RE = re.compile(r"\bconveyors?\b|\bbelt\b", re.IGNORECASE)
# The user lists the results they want ("I need these values: …") → a project plan, not a single sizing
_ASKS_RE = re.compile(r"\bi need (?:this|these|the following|the)\b|\bcalculate the following\b|"
                      r"\bneed (?:these|this|the following) (?:values?|information|results?)\b", re.IGNORECASE)


def _mock_route(text: str) -> TopicRouting:
    if _PROJECT_RE.search(text):
        return TopicRouting(topic="project", reason="You described a shredding machine, so the full calculation plan is shown.")
    if _CONVEYOR_RE.search(text) and _BULK_RE.search(text):
        return TopicRouting(topic="project", reason="You described a bulk-material belt conveyor, so the ISO 5048 "
                                                    "conveyor calculation plan is shown.")
    if _ASKS_RE.search(text):
        return TopicRouting(topic="project", reason="You listed several results you need, so a calculation plan is shown.")
    machine = any(re.search(p, text, re.IGNORECASE) for _, p in _MACHINE_NAMES)
    if _BEARING_RE.search(text) and not machine:
        return TopicRouting(topic="bearing_life", reason="Your question is about a bearing's load or life.")
    if machine or _MOTOR_RE.search(text):
        return TopicRouting(topic="motor_sizing", reason="Your question is about sizing the drive for a machine.")
    return TopicRouting(topic="general", reason="Your question is not motor sizing or bearing life.")


def route(text: str) -> TopicRouting:
    if _provider() == "mock":
        return _mock_route(text)
    try:
        r = call_structured(TopicRouting, ROUTER_INSTRUCTION, text)
        if r.topic in TOPICS:
            return r
    except Exception as e:  # fall back to rules rather than failing the request
        logger.error("[Assistant] routing failed: %s", type(e).__name__)
    return _mock_route(text)


# ─────────────────────────────────────────────────────────────
# 2a. Bearing values
# ─────────────────────────────────────────────────────────────

class _Quote(BaseModel):
    field: str
    quote: str


class BearingExtraction(BaseModel):
    bearing_type: Optional[str] = Field(None, description="'ball' or 'roller' (tapered, cylindrical, spherical and needle are roller).")
    radial_load_n: Optional[float] = Field(None, description="Radial load in N (convert kN × 1000).")
    axial_load_n: Optional[float] = Field(None, description="Axial / thrust load in N.")
    x_factor: Optional[float] = Field(None, description="Radial factor X, only if stated.")
    y_factor: Optional[float] = Field(None, description="Axial factor Y, only if stated.")
    speed_rpm: Optional[float] = Field(None, description="Shaft speed in rpm.")
    dynamic_rating_kn: Optional[float] = Field(None, description="Basic dynamic load rating C in kN, only if stated.")
    required_life_h: Optional[float] = Field(None, description="Required life in hours.")
    reliability_pct: Optional[float] = Field(None, description="Required reliability in %, only if stated.")
    quotes: List[_Quote] = Field(default_factory=list, description="One entry per non-null field with the user's exact words.")


BEARING_INSTRUCTION = (
    "Extract rolling-bearing inputs the user actually wrote. Convert units to those in the field descriptions and "
    "copy the user's original words into quotes, one per non-null field. Never supply C, X, Y or any value from "
    "your own knowledge — leave it null."
)

_N = r"(\d+(?:\.\d+)?)"


def _mock_bearing(text: str) -> BearingExtraction:
    out: Dict[str, Any] = {}
    quotes: List[_Quote] = []

    def take(field, pattern, conv):
        if field in out:
            return
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            out[field] = conv(m)
            quotes.append(_Quote(field=field, quote=m.group(0)))

    force = lambda m: float(m.group(1)) * (1000 if m.group(2).lower() == "kn" else 1)
    take("bearing_type", r"\b(ball|roller|tapered|cylindrical|spherical|needle)\b",
         lambda m: "ball" if m.group(1).lower() == "ball" else "roller")
    take("axial_load_n", r"(?:axial|thrust|Fa)\s*(?:load|force)?\s*(?:of|=|:|is)?\s*" + _N + r"\s*(kN|N)\b", force)
    take("axial_load_n", _N + r"\s*(kN|N)\s*(?:axial|thrust)", force)
    take("radial_load_n", r"(?:radial|Fr)\s*(?:load|force)?\s*(?:of|=|:|is)?\s*" + _N + r"\s*(kN|N)\b", force)
    take("radial_load_n", _N + r"\s*(kN|N)\s*radial", force)
    if "radial_load_n" not in out:
        take("radial_load_n", r"(?:bearing\s+)?load\s*(?:of|=|:|is)?\s*" + _N + r"\s*(kN|N)\b", force)
    take("speed_rpm", _N + r"\s*(?:rpm|rev/min|r/min)\b", lambda m: float(m.group(1)))
    take("dynamic_rating_kn", r"(?:\bC\b|dynamic (?:load )?rating|load rating)\s*(?:of|=|:|is)?\s*" + _N + r"\s*kN", lambda m: float(m.group(1)))
    take("required_life_h", r"(?:life|L10h?)\s*(?:of|=|:|is)?\s*" + _N + r"\s*(?:h|hrs?|hours?)\b", lambda m: float(m.group(1)))
    take("required_life_h", _N + r"\s*(?:h|hrs?|hours?)\s*(?:of\s+)?(?:life|service)", lambda m: float(m.group(1)))
    take("x_factor", r"\bX\s*=\s*" + _N, lambda m: float(m.group(1)))
    take("y_factor", r"\bY\s*=\s*" + _N, lambda m: float(m.group(1)))
    take("reliability_pct", _N + r"\s*%\s*reliab", lambda m: float(m.group(1)))
    return BearingExtraction(**out, quotes=quotes)


class ExtractedField(BaseModel):
    field: str
    value: Any
    quote: str


def extract_bearing(text: str) -> List[ExtractedField]:
    ex = _mock_bearing(text) if _provider() == "mock" else call_structured(BearingExtraction, BEARING_INSTRUCTION, text)
    quotes = {q.field: q.quote for q in ex.quotes}
    norm_text = _norm(text)
    out = []
    for field in BearingExtraction.model_fields:
        if field == "quotes":
            continue
        val = getattr(ex, field)
        q = quotes.get(field)
        if val is None or not q or _norm(q) not in norm_text:
            continue
        if field == "bearing_type" and val not in ("ball", "roller"):
            continue
        if field != "bearing_type" and (not isinstance(val, (int, float)) or val < 0 or not re.search(r"\d", q)):
            continue
        out.append(ExtractedField(field=field, value=val, quote=q))
    return out


# ─────────────────────────────────────────────────────────────
# 2b. AI-chosen method for other topics
# ─────────────────────────────────────────────────────────────

METHOD_INSTRUCTION = (
    "You are an engineering calculation planner. For the user's question, choose the appropriate recognised method "
    "or standard and return it as a MethodPlan: the inputs needed (with units), and the calculation as a sequence of "
    "formulas. Rules: "
    "1) Do NOT compute any results yourself — only write formulas; the tool evaluates them. "
    "2) Formulas may use only earlier symbols, numbers, + - * / ** and the listed maths functions, with unit "
    "conversion factors written explicitly so units are consistent. "
    "3) Fill an input's value only if the user stated it, and copy their exact words into quote. "
    "4) You may give a typical_value with a typical_note (source and usual range) for material or catalogue "
    "properties, but never for the user's own dimensions, loads, speeds or operating conditions. "
    "5) Name the standard in `standard` and list limitations honestly. Keep it to the steps an engineer would show."
)


def plan_method(text: str) -> MethodPlan:
    plan = call_structured(MethodPlan, METHOD_INSTRUCTION, text)
    norm_text = _norm(text)
    for i in plan.inputs:   # a value counts as "given" only if the user's words are really in the text
        if i.value is not None and not (i.quote and _norm(i.quote) in norm_text and re.search(r"\d", i.quote)):
            i.value, i.quote = None, None
    return plan


# ─────────────────────────────────────────────────────────────
# 2c. Whole-project calculation plan
# ─────────────────────────────────────────────────────────────

PROJECT_INSTRUCTION = (
    "You are planning the engineering calculations for the user's machine project. Return a ProjectPlan: "
    "every piece of information needed (inputs, with units and where the engineer gets each one) and every "
    "calculation needed, in the order an engineer would do them, so that results feed later steps. "
    "Rules: "
    "1) Use kind 'motor_selection' for choosing the motor + gearbox (link required_speed_rpm, required_torque_nm, "
    "service_factor, max_voltage_v) and kind 'bearing_life' for rolling bearings (link radial_load_n, speed_rpm and "
    "required_life_h and/or dynamic_rating_kn; set bearing_type). Use kind 'formula' for everything else. "
    "2) Do NOT compute results — only write formulas; the tool evaluates them. Formulas may use only earlier symbols, "
    "numbers, + - * / ** and the listed maths functions, with unit conversion factors written explicitly. "
    "3) Fill an input's value only if the user stated it, with their exact words in quote. "
    "4) typical_value only for material or catalogue properties, with typical_note giving the source and range; "
    "never for the user's own dimensions, loads, speeds or operating conditions. "
    "5) Name standards where they apply and list limitations honestly. "
    "6) Keep it practical: the calculations a design engineer must show for this machine, typically 5 to 10. "
    "7) If the user lists specific results they need, calculate every one of them as a step, using their wording "
    "in the step name. "
    "8) Use the recognised method for the machine type (e.g. ISO 5048 / DIN 22101 or CEMA for bulk belt conveyors), "
    "never a simplified method meant for a different kind of machine."
)

_SHRED_VALUES = [
    ("n", r"(\d+(?:\.\d+)?)\s*(?:rpm|rev/min)\b", 1.0),
    ("D", r"(?:rotor|cutter|blade)\s*(?:diameter|dia\.?)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*mm", 1.0),
    ("D", r"(\d+(?:\.\d+)?)\s*mm\s*(?:rotor|cutter|blade)s?\b", 1.0),
    ("t", r"(\d+(?:\.\d+)?)\s*mm\s*thick", 1.0),
    ("b", r"(?:blade|cutter)s?\s*(?:width|wide)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*mm", 1.0),
    ("tau_s", r"shear strength\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*MPa", 1.0),
    ("L", r"bearing (?:span|distance)\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*mm", 1.0),
    ("life_req", r"(\d+(?:\.\d+)?)\s*(?:h|hours?)\s*(?:of\s+)?(?:bearing\s+)?life", 1.0),
    ("V", r"(\d+(?:\.\d+)?)\s*(?:v|volts?|vac|vdc)\b", 1.0),
]


_CONVEYOR_VALUES = [
    ("v", r"(\d+(?:\.\d+)?)\s*m/s\b"),
    ("D", r"pulley\s*(?:diameter|dia\.?)?\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*mm"),
    ("D", r"(\d+(?:\.\d+)?)\s*mm\s*(?:diameter\s+)?(?:drive\s+)?pulley"),
    ("L", r"cent(?:er|re)[- ]to[- ]cent(?:er|re)(?:\s+distance)?\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*(?:m|meters?|metres?)\b"),
    ("L", r"(?:conveyor\s+)?length\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*(?:m|meters?|metres?)\b"),
    ("L", r"(\d+(?:\.\d+)?)\s*(?:m|meters?|metres?)\s*long\b"),
    ("B", r"belt\s*width\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*mm"),
    ("B", r"(\d+(?:\.\d+)?)\s*mm\s*(?:wide\s+)?belt\b"),
    ("Q", r"(\d+(?:\.\d+)?)\s*(?:t/h|tph|tonn?es? per hour|tons? per hour)"),
    ("H", r"lift(?:\s*height)?\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*m\b"),
    ("theta", r"wrap(?:\s*angle)?\s*(?:of|is|:)?\s*(\d+(?:\.\d+)?)\s*(?:°|deg)"),
    ("V", r"(\d+(?:\.\d+)?)\s*(?:v|volts?|vac|vdc)\b"),
]


def _fill(plan: ProjectPlan, text: str, patterns) -> ProjectPlan:
    by_symbol = {i.symbol: i for i in plan.inputs}
    for sym, pat in patterns:
        inp = by_symbol[sym]
        if inp.value is not None:
            continue
        mm = re.search(pat, text, re.IGNORECASE)
        if mm:
            inp.value, inp.quote = float(mm.group(1)), mm.group(0)
    return plan


def _mock_project(text: str) -> ProjectPlan:
    if _CONVEYOR_RE.search(text) and _BULK_RE.search(text) and not _PROJECT_RE.search(text):
        plan = bulk_conveyor_template()
        H = next(i for i in plan.inputs if i.symbol == "H")
        flat = re.search(r"\bhorizontal\b|\bflat\b|\blevel\b", text, re.IGNORECASE)
        if flat:
            H.value, H.quote = 0.0, flat.group(0)
        return _fill(plan, text, _CONVEYOR_VALUES)
    if not _PROJECT_RE.search(text):
        raise ProviderError("AI_NOT_CONFIGURED", "AI is not switched on for this tool.")
    m = _PROJECT_RE.search(text)
    plan = shredder_template(machine=m.group(0))
    by_symbol = {i.symbol: i for i in plan.inputs}
    if re.search(r"\btwin[- ]shaft|\btwo[- ]shaft|\bdouble[- ]shaft", text, re.IGNORECASE):
        q = re.search(r"\btwin[- ]shaft|\btwo[- ]shaft|\bdouble[- ]shaft", text, re.IGNORECASE).group(0)
        by_symbol["N_sh"].value, by_symbol["N_sh"].quote = 2, q
    elif re.search(r"\bsingle[- ]shaft", text, re.IGNORECASE):
        q = re.search(r"\bsingle[- ]shaft", text, re.IGNORECASE).group(0)
        by_symbol["N_sh"].value, by_symbol["N_sh"].quote = 1, q
    for sym, pat, k in _SHRED_VALUES:
        inp = by_symbol[sym]
        if inp.value is not None:
            continue
        mm = re.search(pat, text, re.IGNORECASE)
        if mm:
            inp.value, inp.quote = float(mm.group(1)) * k, mm.group(0)
    return plan


def requested_items(text: str) -> List[str]:
    """Results the user listed, e.g. one per line ("Pulley shaft torque") or after "I need:"."""
    items: List[str] = []
    for line in re.split(r"[\r\n]+", text):
        line = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip(" .;:")
        tail = re.split(r"\b(?:i need|calculate|need)\b\s*:?", line, flags=re.IGNORECASE)
        parts = re.split(r"\s*,\s*|\s+and\s+", tail[-1]) if len(tail) > 1 and ":" in line else [line]
        for part in parts:
            part = part.strip(" .;:")
            words = part.split()
            if (2 <= len(words) <= 10 and not re.search(r"\d", part) and not _ASKS_RE.search(part)
                    and not re.search(r"\b(?:i'?m|i am|we are|designing|building)\b", part, re.IGNORECASE)):
                items.append(part)
    return items


def plan_project(text: str) -> ProjectPlan:
    plan = _plan_project(text)
    if not plan.requested:
        items = requested_items(text)
        if items:
            map_requested(plan, items)
    return plan


def _plan_project(text: str) -> ProjectPlan:
    if _provider() == "mock":
        return _mock_project(text)
    plan = call_structured(ProjectPlan, PROJECT_INSTRUCTION, text)
    plan.origin = "AI"
    norm_text = _norm(text)
    for i in plan.inputs:   # a value counts as "given" only if the user's words are really in the text
        if i.value is not None and not (i.quote and _norm(i.quote) in norm_text
                                        and (re.search(r"\d", i.quote) or i.symbol.lower().startswith("n_sh"))):
            i.value, i.quote = None, None
    return plan


# ─────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────

class AskResult(BaseModel):
    topic: str
    reason: str
    provider: str
    sizing: Optional[SizingParseResult] = None
    bearing_values: List[ExtractedField] = []
    plan: Optional[MethodPlan] = None
    project: Optional[ProjectPlan] = None
    message: Optional[str] = None
    status: str = "OK"   # OK | AI_NOT_CONFIGURED | INVALID_PLAN | ERROR


AI_OFF_MESSAGE = ("This question needs the AI to choose a calculation method, and the AI is not switched on for "
                  "this tool yet (set AI_PROVIDER and an API key). Without it, the tool can do motor sizing, "
                  "bearing life, and full project plans for shredders and bulk belt conveyors. "
                  "If you already know the torque and speed, use the 'Advanced: Torque & RPM' tab.")


def ask(text: str) -> AskResult:
    provider = _provider()
    r = route(text)
    res = AskResult(topic=r.topic, reason=r.reason, provider=provider)
    try:
        if r.topic == "project":
            project = plan_project(text)
            problems = validate_project(project)
            if problems:
                res.status, res.message = "INVALID_PLAN", ("The AI's project plan could not be checked, so it was not used: "
                                                           + " ".join(problems[:3]) + " Try rephrasing the question.")
            else:
                res.project = project
        elif r.topic == "motor_sizing":
            res.sizing = get_sizing_parser().parse(text)
        elif r.topic == "bearing_life":
            res.bearing_values = extract_bearing(text)
        else:
            plan = plan_method(text)
            problems = validate_plan(plan)
            if problems:
                res.status, res.message = "INVALID_PLAN", ("The AI's method could not be checked, so it was not used: "
                                                           + " ".join(problems[:3]) + " Try rephrasing the question.")
            else:
                res.plan = plan
    except ProviderError as e:
        res.status = "AI_NOT_CONFIGURED" if e.status in ("AI_NOT_CONFIGURED", "ERROR_CONFIGURATION_MISSING") else "ERROR"
        res.message = AI_OFF_MESSAGE if res.status == "AI_NOT_CONFIGURED" else e.message
    except Exception as e:
        logger.error("[Assistant] %s failed: %s", r.topic, type(e).__name__)
        res.status, res.message = "ERROR", f"The question could not be processed ({type(e).__name__}). Please try again or rephrase."
    return res
