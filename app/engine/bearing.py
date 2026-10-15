"""
Bearing basic rating life check — ISO 281 method.

Two modes, chosen by which inputs are given:
  * Check a bearing:   C (catalogue dynamic load rating) given  → life in hours,
                       compared with the required life if one is given.
  * Size a bearing:    C not given, required life given        → minimum C needed.

Equations (ISO 281):
  P    = Fr                       when Fa = 0
  P    = X·Fr + Y·Fa              otherwise (X, Y from the bearing catalogue)
  L10  = (C / P)^p                million revolutions; p = 3 ball, 10/3 roller
  L10h = L10 · 10^6 / (60 · n)    hours
  Lnh  = a1 · L10h                life at the chosen reliability (a1 table)
  C_min = P · (60 · n · L_req / (a1 · 10^6))^(1/p)

Scope: basic rating life only. The ISO 281 life modification factor a_ISO
(lubrication, contamination, fatigue load limit) is NOT included — real life
can be lower than this in poor lubrication or contaminated conditions.
X, Y and C are never assumed: they come from the bearing manufacturer's catalogue.
"""
import math
from typing import Optional, List, Literal, Dict
from pydantic import BaseModel

from app.engine.sizing.schemas import SizingStep, StepInput, MissingInput

# ISO 281 reliability factor a1 (to be verified against ISO 281 by the engineering owner)
RELIABILITY_A1: Dict[float, float] = {90: 1.0, 95: 0.64, 96: 0.55, 97: 0.47, 98: 0.37, 99: 0.25}


class BearingRequest(BaseModel):
    bearing_type: Optional[Literal["ball", "roller"]] = None
    radial_load_n: Optional[float] = None
    axial_load_n: Optional[float] = None
    x_factor: Optional[float] = None
    y_factor: Optional[float] = None
    speed_rpm: Optional[float] = None
    dynamic_rating_kn: Optional[float] = None
    required_life_h: Optional[float] = None
    reliability_pct: float = 90


class BearingResult(BaseModel):
    status: Literal["MEETS", "DOES_NOT_MEET", "LIFE_CALCULATED", "MIN_RATING_CALCULATED",
                    "REQUIREMENTS_INCOMPLETE", "INVALID_INPUT"]
    missing_inputs: List[MissingInput] = []
    errors: List[str] = []
    steps: List[SizingStep] = []
    equivalent_load_n: Optional[float] = None
    life_h: Optional[float] = None
    min_dynamic_rating_kn: Optional[float] = None
    notes: List[str] = []


def _f(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 1e4 else f"{x:.4g}"


def bearing_life(req: BearingRequest) -> BearingResult:
    missing: List[MissingInput] = []
    errors: List[str] = []
    steps: List[SizingStep] = []

    def need(field, label, val, positive=True):
        if val is None:
            missing.append(MissingInput(field=field, label=label))
        elif positive and val <= 0:
            errors.append(f"{label} must be greater than 0.")
        return val

    def step(key, label, formula, subst, result, unit, inputs=None, note=None):
        steps.append(SizingStep(key=key, label=label, formula=formula,
                                substitution=f"{subst} = {_f(result)} {unit}".strip(), result=result, unit=unit,
                                inputs={k: StepInput(value=v, unit=u, origin=o) for k, (v, u, o) in (inputs or {}).items()},
                                note=note))
        return result

    btype = need("bearing_type", "Bearing type (ball or roller)", req.bearing_type, positive=False)
    Fr = need("radial_load_n", "Radial load (N)", req.radial_load_n)
    n = need("speed_rpm", "Shaft speed (rpm)", req.speed_rpm)
    Fa = req.axial_load_n or 0.0
    if Fa < 0:
        errors.append("Axial load cannot be negative.")
    if Fa > 0:
        need("x_factor", "Radial factor X (from the bearing catalogue)", req.x_factor, positive=False)
        need("y_factor", "Axial factor Y (from the bearing catalogue)", req.y_factor, positive=False)
    if req.dynamic_rating_kn is None and req.required_life_h is None:
        missing.append(MissingInput(field="dynamic_rating_kn",
                                    label="Either the bearing's dynamic load rating C (kN, from the catalogue) "
                                          "or the required life (hours)"))
    if req.dynamic_rating_kn is not None and req.dynamic_rating_kn <= 0:
        errors.append("Dynamic load rating must be greater than 0.")
    if req.required_life_h is not None and req.required_life_h <= 0:
        errors.append("Required life must be greater than 0.")
    if req.reliability_pct not in RELIABILITY_A1:
        errors.append(f"Reliability must be one of {sorted(RELIABILITY_A1)} %.")
    if missing or errors:
        return BearingResult(status="INVALID_INPUT" if errors else "REQUIREMENTS_INCOMPLETE",
                             missing_inputs=missing, errors=errors)

    p = 3.0 if btype == "ball" else 10.0 / 3.0
    p_txt = "3" if btype == "ball" else "10/3"
    step("exponent", "Life exponent", "p = 3 (ball) or 10/3 (roller)", f"p ({btype})", p, "",
         {"bearing_type": (btype, "", "USER")})
    if Fa == 0:
        P = step("p_eq", "Equivalent dynamic load", "P = Fr (no axial load)", f"P = {_f(Fr)}", Fr, "N",
                 {"Fr": (Fr, "N", "USER")})
    else:
        X, Y = req.x_factor, req.y_factor
        P = step("p_eq", "Equivalent dynamic load", "P = X × Fr + Y × Fa",
                 f"P = {_f(X)} × {_f(Fr)} + {_f(Y)} × {_f(Fa)}", X * Fr + Y * Fa, "N",
                 {"X": (X, "", "USER"), "Fr": (Fr, "N", "USER"), "Y": (Y, "", "USER"), "Fa": (Fa, "N", "USER")},
                 note="X and Y must come from the bearing catalogue for this Fa/Fr ratio.")
    if P <= 0:
        return BearingResult(status="INVALID_INPUT", errors=["Equivalent load must be greater than 0."], steps=steps)

    a1 = RELIABILITY_A1[req.reliability_pct]
    notes = ["Basic rating life per ISO 281. The life modification factor a_ISO (lubrication, contamination) "
             "is not included — real life can be lower in poor lubrication or dirty conditions."]
    status, life_h, c_min = "LIFE_CALCULATED", None, None

    if req.dynamic_rating_kn is not None:
        C = req.dynamic_rating_kn * 1000
        L10 = step("l10", "Basic rating life (millions of revolutions)", "L10 = (C / P)^p",
                   f"L10 = ({_f(C)} / {_f(P)})^{p_txt}", (C / P) ** p, "million rev",
                   {"C": (req.dynamic_rating_kn, "kN", "USER")})
        L10h = step("l10h", "Basic rating life (hours)", "L10h = L10 × 10⁶ / (60 × n)",
                    f"L10h = {_f(L10)} × 10⁶ / (60 × {_f(n)})", L10 * 1e6 / (60 * n), "h",
                    {"n": (n, "rpm", "USER")})
        life = L10h
        if a1 != 1.0:
            life = step("lnh", f"Life at {req.reliability_pct:g} % reliability", "Lnh = a1 × L10h",
                        f"Lnh = {_f(a1)} × {_f(L10h)}", a1 * L10h, "h", {"a1": (a1, "", "CONSTANT")})
        life_h = life
        if req.required_life_h is not None:
            ok = life >= req.required_life_h
            status = "MEETS" if ok else "DOES_NOT_MEET"
            notes.append(f"Calculated life {_f(life)} h {'≥' if ok else '<'} required {_f(req.required_life_h)} h.")
    else:
        Lr = req.required_life_h
        Cmin = step("c_min", "Minimum dynamic load rating needed", "C_min = P × (60 × n × L_req / (a1 × 10⁶))^(1/p)",
                    f"C_min = {_f(P)} × (60 × {_f(n)} × {_f(Lr)} / ({_f(a1)} × 10⁶))^(1/{p_txt})",
                    P * (60 * n * Lr / (a1 * 1e6)) ** (1 / p), "N",
                    {"L_req": (Lr, "h", "USER"), "n": (n, "rpm", "USER")})
        c_min = Cmin / 1000
        status = "MIN_RATING_CALCULATED"
        notes.append(f"Choose a bearing whose catalogue dynamic load rating C is at least {_f(Cmin / 1000)} kN.")
    return BearingResult(status=status, steps=steps, equivalent_load_n=P, life_h=life_h,
                         min_dynamic_rating_kn=c_min, notes=notes)
