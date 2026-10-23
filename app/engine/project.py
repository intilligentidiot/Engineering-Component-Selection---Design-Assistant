"""
Project calculation plans.

A ProjectPlan lists, for a whole machine, the information needed and every
calculation to do, in order. Calculations are one of:

  formula          — steps evaluated deterministically by the tool (method_eval);
                     the method comes from the AI or a built-in template
  bearing_life     — the checked ISO 281 module (app/engine/bearing.py)
  motor_selection  — the checked motor + gearbox selection (app/engine/recommend.py)

All calculations share one set of symbols, so results flow forward: e.g. the
rotor torque calculated in step 3 feeds the shaft, bearing and motor steps.
A calculation whose information is missing is reported as waiting (with what it
needs) while the others still run.
"""
import math
import re
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field

from app.engine.method_eval import (
    PlanStep, EvaluatedStep, PlanError, CONSTS, FUNCS, _SYMBOL, _parse, _check, _names, _eval, _Sub, _fmt, _MAX_ABS,
)
from app.engine.bearing import bearing_life, BearingRequest
import ast

KINDS = ("formula", "bearing_life", "motor_selection")
LINK_PARAMS = {
    "bearing_life": {"radial_load_n", "axial_load_n", "x_factor", "y_factor", "speed_rpm", "dynamic_rating_kn", "required_life_h"},
    "motor_selection": {"required_speed_rpm", "required_torque_nm", "peak_torque_nm", "service_factor", "max_voltage_v"},
}
REQUIRED_LINKS = {
    "bearing_life": {"radial_load_n", "speed_rpm"},
    "motor_selection": {"required_speed_rpm", "required_torque_nm", "max_voltage_v"},
}


# ─────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────

class EstimateInput(BaseModel):
    symbol: str = Field(..., description="Identifier used in the estimate formula.")
    name: str = Field(..., description="Plain-English name.")
    unit: str = Field(..., description="Unit the value is entered in.")
    from_input: Optional[str] = Field(None, description="Main-plan input symbol whose value pre-fills this one.")
    typical_value: Optional[float] = Field(None, description="Typical value (design convention or material property).")
    typical_note: Optional[str] = Field(None, description="Source and usual range of the typical value.")


class EstimateHelper(BaseModel):
    title: str = Field(..., description="e.g. 'Estimate from belt width and thickness'.")
    note: str = Field(..., description="What the estimate assumes and what to replace it with.")
    inputs: List[EstimateInput] = Field(default_factory=list)
    expression: str = Field(..., description="Formula using only the estimate's own input symbols.")


class ProjectInput(BaseModel):
    symbol: str = Field(..., description="Identifier used in formulas, e.g. tau_s.")
    name: str = Field(..., description="Plain-English name, e.g. 'Material shear strength'.")
    unit: str = Field(..., description="Unit the value is entered in.")
    source_hint: str = Field(..., description="Where the engineer gets this value, e.g. 'Material datasheet'.")
    optional: bool = Field(False, description="True if calculations can run without it.")
    value: Optional[float] = Field(None, description="Only if the user stated it (converted to unit).")
    quote: Optional[str] = Field(None, description="The user's exact words for value.")
    typical_value: Optional[float] = Field(None, description="Typical value for material/catalogue properties only.")
    typical_note: Optional[str] = Field(None, description="Source and usual range of the typical value.")
    estimate: Optional[EstimateHelper] = Field(None, description="Optional helper to estimate this value from easier inputs.")


class Link(BaseModel):
    param: str = Field(..., description="Parameter of the checked module, e.g. radial_load_n.")
    symbol: str = Field(..., description="Symbol (input or earlier result) that supplies it.")


class ProjectCalc(BaseModel):
    id: str = Field(..., description="Short id, e.g. 'cutting_force'.")
    title: str = Field(..., description="Calculation title, e.g. 'Cutting force per blade'.")
    purpose: str = Field(..., description="One sentence on why this calculation is needed.")
    kind: str = Field("formula", description="formula, bearing_life or motor_selection.")
    standard: Optional[str] = Field(None, description="Standard or reference followed, if any.")
    steps: List[PlanStep] = Field(default_factory=list, description="Formula steps (kind = formula).")
    links: List[Link] = Field(default_factory=list, description="Module inputs (kind = bearing_life / motor_selection).")
    bearing_type: Optional[str] = Field(None, description="'ball' or 'roller' for bearing_life.")
    note: Optional[str] = None


class RequestedItem(BaseModel):
    text: str = Field(..., description="A result the user explicitly asked for, in their words.")
    symbol: Optional[str] = Field(None, description="Symbol of the step (or input) that answers it; null if none does.")


class ProjectPlan(BaseModel):
    title: str = Field(..., description="e.g. 'Plastic shredder — calculation plan'.")
    machine: str = Field(..., description="The machine as the user described it.")
    summary: str = Field(..., description="Two or three sentences describing the plan.")
    origin: str = Field("AI", description="'AI' or 'TEMPLATE'.")
    inputs: List[ProjectInput] = Field(default_factory=list)
    calculations: List[ProjectCalc] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    requested: List[RequestedItem] = Field(default_factory=list,
                                           description="Each specific result the user listed, mapped to the step that answers it.")
    key_symbols: List[str] = Field(default_factory=list,
                                   description="Symbols of the main results to show at the top when the user listed none.")


class CalcResult(BaseModel):
    id: str
    status: str            # DONE | WAITING | ERROR
    waiting_for: List[str] = []
    errors: List[str] = []
    steps: List[EvaluatedStep] = []
    bearing: Optional[Dict[str, Any]] = None
    motors: Optional[List[Dict[str, Any]]] = None
    internet: Optional[List[Dict[str, Any]]] = None      # Source B products (when requested)
    internet_source: Optional[str] = None                # LIVE | MOCK | UNAVAILABLE
    used: Dict[str, float] = {}


class ProjectResult(BaseModel):
    status: str            # EVALUATED | INVALID_PLAN
    errors: List[str] = []
    calculations: List[CalcResult] = []
    missing_inputs: List[str] = []


# ─────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────

def validate_project(plan: ProjectPlan) -> List[str]:
    problems: List[str] = []
    defined = set(CONSTS)
    for i in plan.inputs:
        if not _SYMBOL.match(i.symbol) or i.symbol in FUNCS or i.symbol in defined:
            problems.append(f"Invalid or duplicate input symbol '{i.symbol}'.")
        defined.add(i.symbol)
        if i.estimate:
            own = {e.symbol for e in i.estimate.inputs}
            try:
                tree = _parse(i.estimate.expression)
                _check(tree)
                unknown = sorted({n for n in _names(tree) if n not in own})
                if unknown:
                    problems.append(f"Estimate for '{i.name}' uses undefined symbol(s): {', '.join(unknown)}.")
            except PlanError as e:
                problems.append(f"Estimate for '{i.name}': {e}")
    if not plan.calculations:
        problems.append("The plan has no calculations.")
    for c in plan.calculations:
        if c.kind not in KINDS:
            problems.append(f"'{c.title}': unknown calculation kind '{c.kind}'.")
            continue
        if c.kind == "formula":
            if not c.steps:
                problems.append(f"'{c.title}' has no formula steps.")
            for s in c.steps:
                if not _SYMBOL.match(s.symbol) or s.symbol in FUNCS or s.symbol in defined:
                    problems.append(f"'{c.title}': invalid or duplicate symbol '{s.symbol}'.")
                try:
                    tree = _parse(s.expression)
                    _check(tree)
                    unknown = sorted({n for n in _names(tree) if n not in defined})
                    if unknown:
                        problems.append(f"'{c.title}' uses undefined symbol(s): {', '.join(unknown)}.")
                except PlanError as e:
                    problems.append(f"'{c.title}': {e}")
                defined.add(s.symbol)
        else:
            params = {l.param for l in c.links}
            bad = params - LINK_PARAMS[c.kind]
            if bad:
                problems.append(f"'{c.title}': unknown parameter(s) {', '.join(sorted(bad))}.")
            if not REQUIRED_LINKS[c.kind] <= params:
                problems.append(f"'{c.title}': missing link(s) {', '.join(sorted(REQUIRED_LINKS[c.kind] - params))}.")
            for l in c.links:
                if l.symbol not in defined:
                    problems.append(f"'{c.title}': '{l.symbol}' is not defined before this calculation.")
            if c.kind == "bearing_life" and c.bearing_type not in ("ball", "roller"):
                problems.append(f"'{c.title}': bearing type must be 'ball' or 'roller'.")
    for rq in plan.requested:
        if rq.symbol is not None and rq.symbol not in defined:
            rq.symbol = None   # an unknown link is shown as "not calculated by this plan", never guessed
    return problems


# Names and units for module parameters, used when the AI left one unlinked
LINK_NAMES = {
    "radial_load_n": ("Radial load on the bearing", "N"),
    "axial_load_n": ("Axial load on the bearing", "N"),
    "x_factor": ("Bearing radial load factor X", "-"),
    "y_factor": ("Bearing axial load factor Y", "-"),
    "speed_rpm": ("Bearing shaft speed", "rpm"),
    "dynamic_rating_kn": ("Bearing dynamic load rating C", "kN"),
    "required_life_h": ("Required bearing life", "h"),
    "required_speed_rpm": ("Required output speed", "rpm"),
    "required_torque_nm": ("Required output torque", "N·m"),
    "peak_torque_nm": ("Peak output torque", "N·m"),
    "service_factor": ("Service factor", "-"),
    "max_voltage_v": ("Maximum supply voltage", "V"),
}
_ASK_HINT = "Not worked out by this plan: enter it from your design or a separate calculation."


def repair_project(plan: ProjectPlan) -> List[str]:
    """Make an AI plan usable instead of rejecting it whole. Nothing is guessed:
    a checked-module value the AI left unlinked becomes an input the engineer
    must enter, and a calculation that still cannot be checked is left out with
    a note. Returns the problems left (empty when the plan can be used)."""
    # Module calculations define no symbols, so running them last never breaks a formula
    plan.calculations = ([c for c in plan.calculations if c.kind == "formula"] +
                         [c for c in plan.calculations if c.kind != "formula"])
    defined = set(CONSTS) | {i.symbol for i in plan.inputs}
    for c in plan.calculations:
        if c.kind == "formula":
            defined |= {s.symbol for s in c.steps}
    for c in plan.calculations:
        if c.kind not in LINK_PARAMS:
            continue
        have = {l.param for l in c.links}
        for param in sorted(REQUIRED_LINKS[c.kind] - have):
            sym = re.sub(r"\W", "_", f"{c.id}_{param}")
            c.links.append(Link(param=param, symbol=sym))
        for l in c.links:
            if l.symbol not in defined and _SYMBOL.match(l.symbol) and l.symbol not in FUNCS:
                name, unit = LINK_NAMES.get(l.param, (l.param, "-"))
                plan.inputs.append(ProjectInput(symbol=l.symbol, name=f"{name} ({c.title})", unit=unit,
                                                source_hint=_ASK_HINT))
                defined.add(l.symbol)

    for _ in range(len(plan.calculations) + 1):
        problems = validate_project(plan)
        if not problems:
            return []
        broken = [c for c in plan.calculations if any(f"'{c.title}'" in p for p in problems)]
        if not broken:
            return problems
        for c in broken:
            reason = next(p for p in problems if f"'{c.title}'" in p).replace(f"'{c.title}': ", "").replace(f"'{c.title}' ", "")
            plan.limitations.append(f"Left out: '{c.title}' — the AI's version could not be checked ({reason})")
        gone = {id(c) for c in broken}
        plan.calculations = [c for c in plan.calculations if id(c) not in gone]
    return validate_project(plan)


_STOP = {"the", "of", "a", "an", "and", "for", "to", "at", "on", "in", "required", "total", "value", "values"}


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in _STOP and len(w) > 2}


def map_requested(plan: ProjectPlan, items: List[str]) -> ProjectPlan:
    """Link each result the user listed to the step whose name best matches it (by shared words)."""
    candidates = [(s.symbol, s.name) for c in plan.calculations for s in c.steps]
    out = []
    for text in items:
        want = _words(text)
        best, score = None, 0
        for sym, name in candidates:
            sc = len(want & _words(name))
            if sc > score:
                best, score = sym, sc
        out.append(RequestedItem(text=text, symbol=best if score >= max(1, (len(want) + 1) // 2) else None))
    plan.requested = out
    return plan


# ─────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────

def evaluate_project(plan: ProjectPlan, values: Dict[str, Any], db=None, include_internet: bool = False) -> ProjectResult:
    problems = validate_project(plan)
    if problems:
        return ProjectResult(status="INVALID_PLAN", errors=problems)

    names = {i.symbol: f"{i.name} ({i.unit})" if i.unit else i.name for i in plan.inputs}
    env: Dict[str, float] = {}
    for i in plan.inputs:
        v = values.get(i.symbol)
        if v is None or v == "":
            continue
        try:
            env[i.symbol] = float(v)
        except (TypeError, ValueError):
            return ProjectResult(status="INVALID_PLAN", errors=[f"{i.name} must be a number."])
    missing_inputs = [i.symbol for i in plan.inputs if not i.optional and i.symbol not in env]

    results: List[CalcResult] = []
    for c in plan.calculations:
        if c.kind == "formula":
            results.append(_run_formula(c, env, names))
            for s in c.steps:
                names.setdefault(s.symbol, f"{s.name} (from '{c.title}')")
        else:
            results.append(_run_module(c, env, names, db, include_internet))
    return ProjectResult(status="EVALUATED", calculations=results, missing_inputs=missing_inputs)


def _run_formula(c: ProjectCalc, env: Dict[str, float], names: Dict[str, str]) -> CalcResult:
    own = set()
    needs = []
    for s in c.steps:
        for n in _names(_parse(s.expression)):
            if n not in env and n not in own and n not in CONSTS:
                needs.append(names.get(n, n))
        own.add(s.symbol)
    if needs:
        return CalcResult(id=c.id, status="WAITING", waiting_for=sorted(set(needs)))
    steps: List[EvaluatedStep] = []
    local = dict(env)
    for s in c.steps:
        try:
            r = _eval(_parse(s.expression), local)
        except ZeroDivisionError:
            return CalcResult(id=c.id, status="ERROR", steps=steps, errors=[f"'{s.name}' divides by zero — check the inputs."])
        except (ValueError, OverflowError, PlanError) as e:
            return CalcResult(id=c.id, status="ERROR", steps=steps, errors=[f"'{s.name}' could not be calculated ({e})."])
        if isinstance(r, complex) or math.isnan(r) or abs(r) > _MAX_ABS:
            return CalcResult(id=c.id, status="ERROR", steps=steps, errors=[f"'{s.name}' gave an invalid number."])
        subst = ast.unparse(_Sub(local).visit(_parse(s.expression)))
        steps.append(EvaluatedStep(symbol=s.symbol, name=s.name, unit=s.unit, formula=f"{s.symbol} = {s.expression}",
                                   substitution=f"{s.symbol} = {subst} = {_fmt(r)} {s.unit}".strip(), result=r, note=s.note))
        local[s.symbol] = r
    env.update({st.symbol: st.result for st in steps})
    return CalcResult(id=c.id, status="DONE", steps=steps)


def _run_module(c: ProjectCalc, env: Dict[str, float], names: Dict[str, str], db,
                include_internet: bool = False) -> CalcResult:
    args = {l.param: env[l.symbol] for l in c.links if l.symbol in env}
    needs = [names.get(l.symbol, l.symbol) for l in c.links
             if l.symbol not in env and l.param in REQUIRED_LINKS[c.kind]]
    if c.kind == "bearing_life" and "dynamic_rating_kn" not in args and "required_life_h" not in args:
        needs += [names.get(l.symbol, l.symbol) for l in c.links
                  if l.param in ("dynamic_rating_kn", "required_life_h") and l.symbol not in env]
    if needs:
        return CalcResult(id=c.id, status="WAITING", waiting_for=sorted(set(needs)), used=args)

    if c.kind == "bearing_life":
        r = bearing_life(BearingRequest(bearing_type=c.bearing_type, **args))
        if r.status in ("REQUIREMENTS_INCOMPLETE", "INVALID_INPUT"):
            return CalcResult(id=c.id, status="ERROR", used=args,
                              errors=r.errors or [m.label for m in r.missing_inputs])
        return CalcResult(id=c.id, status="DONE", used=args, bearing=r.model_dump())

    # motor_selection
    if db is None:
        return CalcResult(id=c.id, status="ERROR", used=args, errors=["Component database not available."])
    from app.engine.recommend import get_recommendations
    try:
        recs = get_recommendations(db, required_speed_rpm=args["required_speed_rpm"],
                                   required_torque_nm=args["required_torque_nm"],
                                   service_factor=args.get("service_factor", 1.0),
                                   max_voltage_v=args["max_voltage_v"], top_n=3,
                                   peak_torque_nm=args.get("peak_torque_nm"))
    except Exception as e:
        return CalcResult(id=c.id, status="ERROR", used=args, errors=[f"Selection failed: {e}"])
    motors = [{"motor": r["motor"]["part_number"], "motor_maker": r["motor"]["manufacturer"],
               "gearbox": r["gearbox"]["part_number"], "ratio": r["gearbox"]["ratio"],
               "output_speed_rpm": r["performance"]["output_speed_rpm"],
               "output_torque_nm": r["performance"]["output_torque_nm"],
               "status": r["engineering_status"], "fit": (r["fit"] or {}).get("percent")} for r in recs]
    result = CalcResult(id=c.id, status="DONE", used=args, motors=motors)
    if include_internet:
        _add_internet(result, args, db)
    return result


def _add_internet(result: CalcResult, args: Dict[str, float], db) -> None:
    """Source B: internet-discovered gearmotors, evaluated by the same deterministic checks."""
    import os
    from app.engine.discover import discover_and_evaluate_components
    try:
        found = discover_and_evaluate_components(
            db=db, required_speed_rpm=args["required_speed_rpm"], required_torque_nm=args["required_torque_nm"],
            service_factor=args.get("service_factor", 1.0), max_voltage_v=args["max_voltage_v"], top_n=5,
            peak_torque_nm=args.get("peak_torque_nm"))
    except Exception:
        result.internet, result.internet_source = [], "UNAVAILABLE"
        return
    result.internet_source = "LIVE" if os.environ.get("SERPAPI_KEY") else "MOCK"
    result.internet = [{"manufacturer": f.get("manufacturer"), "product": f.get("product_name"),
                        "part_number": f.get("part_number"), "status": f.get("engineering_status"),
                        "fit": (f.get("fit") or {}).get("percent"), "url": f.get("product_url"),
                        "datasheet": f.get("datasheet_url"), "source": f.get("source"),
                        "output_torque_nm": (f.get("performance") or {}).get("output_torque_nm"),
                        "output_speed_rpm": (f.get("performance") or {}).get("output_speed_rpm")} for f in found]


# ─────────────────────────────────────────────────────────────
# Built-in template: shredder (works without the AI)
# ─────────────────────────────────────────────────────────────

def _i(symbol, name, unit, source, optional=False, typical=None, note=None, estimate=None):
    return ProjectInput(symbol=symbol, name=name, unit=unit, source_hint=source, optional=optional,
                        typical_value=typical, typical_note=note, estimate=estimate)


def _e(symbol, name, unit, typical=None, note=None, from_input=None):
    return EstimateInput(symbol=symbol, name=name, unit=unit, typical_value=typical, typical_note=note, from_input=from_input)


# Allowable shaft shear stress from the ASME shaft code rule (used by the shredder template)
ASME_SHEAR_ESTIMATE = EstimateHelper(
    title="Estimate from the shaft steel's strength (ASME shaft code rule)",
    note=("τ_allow = smaller of 0.3 × yield strength and 0.18 × tensile strength, reduced by 25 % where the shaft "
          "has a keyway. Strengths come from the material certificate."),
    inputs=[_e("Sy_e", "Yield strength of the shaft steel", "MPa"),
            _e("Sut_e", "Tensile strength of the shaft steel", "MPa"),
            _e("k_kw", "Keyway factor (1 = no keyway)", "", typical=0.75,
               note="ASME shaft code: 0.75 (25 % reduction) where there is a keyway, 1.0 without.")],
    expression="min(0.3 * Sy_e, 0.18 * Sut_e) * k_kw")


def shredder_template(machine: str = "Shredding machine") -> ProjectPlan:
    S = lambda sym, name, unit, expr, note=None: PlanStep(symbol=sym, name=name, unit=unit, expression=expr, note=note)
    return ProjectPlan(
        title="Shredder — calculation plan",
        machine=machine,
        origin="TEMPLATE",
        summary=("Rotary cutting shredder: the cutting force from the material's shear strength gives the rotor torque, "
                 "then power, motor + gearbox, shaft size and bearing life. Results flow from one step to the next."),
        inputs=[
            _i("tau_s", "Material shear strength", "MPa", "Material datasheet (ultimate shear strength of the material being shredded)"),
            _i("t", "Thickness of material cut per blade", "mm", "Largest piece / wall thickness the blades must cut"),
            _i("b", "Blade cutting width", "mm", "Your cutter design (width of each blade / hook)"),
            _i("z", "Blades cutting at the same time", "", "Your cutter design (blades engaged at once, per shaft)"),
            _i("D", "Cutter (rotor) diameter", "mm", "Your cutter design"),
            _i("n", "Rotor speed", "rpm", "Your design choice (slow-running shredders usually run at low rpm)"),
            _i("N_sh", "Cutter shafts driven by this motor", "", "1 for a single-shaft shredder, 2 for a twin-shaft driven by one motor"),
            _i("SF", "Service factor", "", "Service-factor table, heavy-shock row", typical=1.75,
               note="Heavy-shock row of the tool's service-factor table: 1.75 for 3–10 h/day, 2.0 for over 10 h/day."),
            _i("L", "Bearing span (distance between the two shaft bearings)", "mm", "Your shaft / frame design"),
            _i("tau_allow", "Allowable shear stress of the shaft steel", "MPa",
               "Shaft material: e.g. 0.3 × yield strength (ASME shaft code), reduced by 25 % where there is a keyway",
               estimate=ASME_SHEAR_ESTIMATE.model_copy(deep=True)),
            _i("life_req", "Required bearing life", "h", "Your target service life (running hours)", optional=True),
            _i("C", "Bearing dynamic load rating (if a bearing is already chosen)", "kN", "Bearing catalogue", optional=True),
            _i("V", "Supply voltage (maximum)", "V", "Your power supply"),
        ],
        calculations=[
            ProjectCalc(id="cutting_force", title="Cutting force", purpose="Force needed to shear the material.",
                        steps=[S("F_b", "Cutting force per blade", "N", "tau_s * t * b", "Shear strength × cut area (MPa × mm² = N)."),
                               S("F", "Total cutting force (blades cutting at once)", "N", "F_b * z")]),
            ProjectCalc(id="torque", title="Rotor torque", purpose="Torque the drive must deliver to the cutter shafts.",
                        steps=[S("T_sh", "Torque per cutter shaft", "N·m", "F * D / 2 / 1000", "Force × cutter radius."),
                               S("T_tot", "Total torque at the drive", "N·m", "T_sh * N_sh")]),
            ProjectCalc(id="power", title="Power", purpose="Power the motor must supply at the cutters.",
                        steps=[S("P", "Shaft power", "W", "T_tot * 2 * pi * n / 60"),
                               S("P_d", "Design power (with service factor)", "kW", "P * SF / 1000")]),
            ProjectCalc(id="motor", title="Motor + gearbox selection", kind="motor_selection",
                        purpose="Find motor + gearbox combinations that deliver the torque at the rotor speed.",
                        links=[Link(param="required_speed_rpm", symbol="n"), Link(param="required_torque_nm", symbol="T_tot"),
                               Link(param="service_factor", symbol="SF"), Link(param="max_voltage_v", symbol="V")]),
            ProjectCalc(id="shaft", title="Cutter shaft diameter", purpose="Minimum shaft size for combined torsion and bending.",
                        standard="Combined torsion + bending, maximum-shear-stress theory (ASME shaft-design approach)",
                        steps=[S("M", "Bending moment (cutting force at mid-span)", "N·m", "F * L / 4 / 1000",
                                 "Simply supported shaft, force at mid-span (conservative)."),
                               S("d", "Minimum shaft diameter", "mm",
                                 "(16 * 1000 / (pi * tau_allow) * sqrt((SF * M) ** 2 + (SF * T_sh) ** 2)) ** (1 / 3)",
                                 "d = [16/(π·τ_allow) · √(M² + T²)]^(1/3), with service factor on both.")]),
            ProjectCalc(id="bearing_load", title="Bearing load", purpose="Radial load on each shaft bearing.",
                        steps=[S("Fr_b", "Radial load per bearing", "N", "F / 2", "Cutting force shared by the two bearings.")]),
            ProjectCalc(id="bearing_life", title="Bearing life (ISO 281)", kind="bearing_life", bearing_type="roller",
                        standard="ISO 281", purpose="Check the bearing life, or find the minimum bearing rating needed.",
                        note="Spherical roller bearings are usual for shredders, so roller-bearing life is used.",
                        links=[Link(param="radial_load_n", symbol="Fr_b"), Link(param="speed_rpm", symbol="n"),
                               Link(param="required_life_h", symbol="life_req"), Link(param="dynamic_rating_kn", symbol="C")]),
        ],
        key_symbols=["F", "T_sh", "T_tot", "P", "P_d", "d"],
        limitations=[
            "Simplified cutting model: real shredding forces depend on blade geometry, material toughness and feeding — "
            "confirm with test data or the shredder manufacturer.",
            "Jam / stall torque and start-up inertia are covered only through the service factor.",
            "Shaft check is static strength only — fatigue, keyway stress concentration and deflection are not included.",
            "Built-in template, not yet approved by an engineer.",
        ],
    )
