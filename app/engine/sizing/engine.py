"""
Stage 8 — deterministic application sizing.

Turns material + part + application + motion inputs into the output-shaft
requirement (speed, continuous torque, peak torque, service factor, power)
that the existing selection engine consumes.

Rules (docs/STAGE_8_APPLICATION_SIZING_SPEC.md):
  * Only the equations written here are used — no guessing.
  * A missing required input stops the calculation (REQUIREMENTS_INCOMPLETE).
  * Optional inputs that fall back to a default are recorded as assumptions.
  * Hardness is recorded but never used in an equation.
"""
import math
from typing import Optional, Dict, Any, List, Tuple

from app.engine.sizing.schemas import (
    SizingRequest, SizingResult, SizingStep, StepInput, MissingInput,
    OperatingPoint, SizedRequirement,
)
from app.engine.sizing.defaults import (
    G, DEFAULTS_VERSION, service_factor_for, hours_band_label, LOAD_CLASS_LABELS,
)


def _f(x: float) -> str:
    """Compact number formatting for substitutions."""
    return f"{x:.4g}"


class _Incomplete(Exception):
    """Raised once required inputs are known to be missing or invalid."""


class _Ctx:
    def __init__(self, application: str):
        self.application = application
        self.steps: List[SizingStep] = []
        self.missing: List[MissingInput] = []
        self.errors: List[str] = []
        self.assumptions: List[str] = []
        self.warnings: List[str] = []
        self.material_notes: List[str] = []

    # ── input helpers ─────────────────────────────────────────
    def req(self, field: str, label: str, value, *, gt: Optional[float] = None,
            ge: Optional[float] = None, le: Optional[float] = None):
        """Required user input. Records missing / out-of-range, returns value or None."""
        if value is None:
            self.missing.append(MissingInput(field=field, label=label))
            return None
        self._check_range(label, value, gt, ge, le)
        return value

    def opt(self, label: str, value, default, assumption: str, *,
            gt: Optional[float] = None, ge: Optional[float] = None, le: Optional[float] = None):
        """Optional user input; falls back to a default that is shown as an assumption."""
        if value is None:
            self.assumptions.append(assumption)
            return default, "DEFAULT"
        self._check_range(label, value, gt, ge, le)
        return value, "USER"

    def _check_range(self, label, value, gt, ge, le):
        if gt is not None and not value > gt:
            self.errors.append(f"{label} must be greater than {_f(gt)} (got {_f(value)}).")
        if ge is not None and not value >= ge:
            self.errors.append(f"{label} must be at least {_f(ge)} (got {_f(value)}).")
        if le is not None and not value <= le:
            self.errors.append(f"{label} must be at most {_f(le)} (got {_f(value)}).")

    def checkpoint(self):
        if self.missing or self.errors:
            raise _Incomplete()

    # ── trace helper ──────────────────────────────────────────
    def step(self, key: str, label: str, formula: str, substitution: str,
             result: float, unit: str, inputs: Optional[Dict[str, Tuple[Any, str, str]]] = None,
             note: Optional[str] = None) -> float:
        self.steps.append(SizingStep(
            key=key, label=label, formula=formula,
            substitution=f"{substitution} = {_f(result)} {unit}".strip(),
            result=result, unit=unit,
            inputs={k: StepInput(value=v, unit=u, origin=o) for k, (v, u, o) in (inputs or {}).items()},
            note=note,
        ))
        return result


# ─────────────────────────────────────────────────────────────
# Material + part → load mass (spec §2)
# ─────────────────────────────────────────────────────────────

def _record_material(ctx: _Ctx, req: SizingRequest):
    mat = req.material
    if mat.hardness_value is not None:
        scale = mat.hardness_scale or "hardness"
        ctx.material_notes.append(
            f"{scale} {_f(mat.hardness_value)} recorded for reference. Hardness is not used in any "
            f"calculation — there is no reliable equation linking hardness to force or friction. "
            f"If it affects grip or friction, enter that friction coefficient directly."
        )


def _collect_part(ctx: _Ctx, req: SizingRequest) -> Dict[str, Any]:
    """Collect (but do not compute) the inputs needed for the load mass, so every
    missing field across the whole form is reported in one go."""
    p, mat = req.part, req.material
    vals: Dict[str, Any] = {"shape": ctx.req("part.shape", "Part shape", p.shape)}
    shape = vals["shape"]
    if shape == "mass":
        vals["m_part"] = ctx.req("part.mass_kg", "Part mass (kg)", p.mass_kg, gt=0)
    elif shape is not None:
        vals["rho"] = ctx.req("material.density_kg_m3", "Material density (kg/m³)", mat.density_kg_m3, gt=0)
        if shape == "block":
            vals["L"] = ctx.req("part.length_mm", "Part length (mm)", p.length_mm, gt=0)
            vals["W"] = ctx.req("part.width_mm", "Part width (mm)", p.width_mm, gt=0)
            vals["H"] = ctx.req("part.height_mm", "Part height (mm)", p.height_mm, gt=0)
        elif shape == "cylinder":
            vals["D"] = ctx.req("part.diameter_mm", "Part diameter (mm)", p.diameter_mm, gt=0)
            vals["L"] = ctx.req("part.length_mm", "Part length (mm)", p.length_mm, gt=0)
        elif shape == "tube":
            vals["Do"] = ctx.req("part.outer_diameter_mm", "Tube outer diameter (mm)", p.outer_diameter_mm, gt=0)
            vals["Di"] = ctx.req("part.inner_diameter_mm", "Tube inner diameter (mm)", p.inner_diameter_mm, ge=0)
            vals["L"] = ctx.req("part.length_mm", "Part length (mm)", p.length_mm, gt=0)
            if vals["Do"] is not None and vals["Di"] is not None and vals["Di"] >= vals["Do"]:
                ctx.errors.append("Tube inner diameter must be smaller than the outer diameter.")
        elif shape == "sphere":
            vals["D"] = ctx.req("part.diameter_mm", "Part diameter (mm)", p.diameter_mm, gt=0)
        else:  # "volume"
            vals["Vc"] = ctx.req("part.volume_cm3", "Part volume (cm³)", p.volume_cm3, gt=0)
    vals["m_carrier"], vals["o_c"] = ctx.opt(
        "Carrier / fixture mass", p.carrier_mass_kg, 0.0,
        "No carrier, pallet or fixture mass entered — taken as 0 kg.", ge=0)
    return vals


def _compute_load_mass(ctx: _Ctx, req: SizingRequest, v: Dict[str, Any]) -> float:
    """Total moved load mass in kg (parts × quantity + carrier). Call after checkpoint()."""
    shape, mm = v["shape"], 1e-3
    if shape == "mass":
        m_part = ctx.step("part_mass", "Part mass", "m_part (entered directly)", "m_part",
                          v["m_part"], "kg", {"m_part": (v["m_part"], "kg", "USER")})
    else:
        if shape == "block":
            L, W, H = v["L"], v["W"], v["H"]
            V = ctx.step("volume", "Part volume (block)", "V = L × W × H",
                         f"V = {_f(L*mm)} m × {_f(W*mm)} m × {_f(H*mm)} m", L*mm * W*mm * H*mm, "m³",
                         {"L": (L, "mm", "USER"), "W": (W, "mm", "USER"), "H": (H, "mm", "USER")})
        elif shape == "cylinder":
            D, L = v["D"], v["L"]
            V = ctx.step("volume", "Part volume (solid cylinder)", "V = π × D² × L / 4",
                         f"V = π × {_f(D*mm)}² × {_f(L*mm)} / 4", math.pi * (D*mm)**2 * L*mm / 4, "m³",
                         {"D": (D, "mm", "USER"), "L": (L, "mm", "USER")})
        elif shape == "tube":
            Do, Di, L = v["Do"], v["Di"], v["L"]
            V = ctx.step("volume", "Part volume (tube)", "V = π × (Do² − Di²) × L / 4",
                         f"V = π × ({_f(Do*mm)}² − {_f(Di*mm)}²) × {_f(L*mm)} / 4",
                         math.pi * ((Do*mm)**2 - (Di*mm)**2) * L*mm / 4, "m³",
                         {"Do": (Do, "mm", "USER"), "Di": (Di, "mm", "USER"), "L": (L, "mm", "USER")})
        elif shape == "sphere":
            D = v["D"]
            V = ctx.step("volume", "Part volume (sphere)", "V = π × D³ / 6",
                         f"V = π × {_f(D*mm)}³ / 6", math.pi * (D*mm)**3 / 6, "m³", {"D": (D, "mm", "USER")})
        else:
            Vc = v["Vc"]
            V = ctx.step("volume", "Part volume (entered)", "V = volume_cm³ × 10⁻⁶",
                         f"V = {_f(Vc)} × 10⁻⁶", Vc * 1e-6, "m³", {"V": (Vc, "cm³", "USER")})
        rho = v["rho"]
        m_part = ctx.step("part_mass", "Part mass", "m_part = ρ × V",
                          f"m_part = {_f(rho)} × {_f(V)}", rho * V, "kg",
                          {"ρ": (rho, "kg/m³", "USER"), "V": (V, "m³", "DERIVED")})
    N, m_c = req.part.quantity, v["m_carrier"]
    return ctx.step("load_mass", "Total moved load mass", "m_load = N × m_part + m_carrier",
                    f"m_load = {N} × {_f(m_part)} + {_f(m_c)}", N * m_part + m_c, "kg",
                    {"N": (N, "parts", "USER"), "m_part": (m_part, "kg", "DERIVED"),
                     "m_carrier": (m_c, "kg", v["o_c"])})


# ─────────────────────────────────────────────────────────────
# Application models (spec §3). Each returns a dict:
#   points: [(label, n_rpm, T_run, T_peak)], envelope (n, T_run, T_peak),
#   hold_torque (torque while dwelling, for RMS), t_acc
# ─────────────────────────────────────────────────────────────

def _conveyor(ctx: _Ctx, req: SizingRequest) -> Dict[str, Any]:
    p = req.params
    part = _collect_part(ctx, req)
    theta = ctx.req("params.incline_deg", "Conveyor incline (deg, 0 = flat)", p.incline_deg, ge=0, le=60)
    mu = ctx.req("params.friction_coefficient", "Friction coefficient (belt on bed / rolling)",
                 p.friction_coefficient, ge=0, le=1.5)
    v = ctx.req("params.speed_m_s", "Belt speed (m/s)", p.speed_m_s, gt=0)
    t_acc = ctx.req("params.accel_time_s", "Time to reach full speed (s)", p.accel_time_s, gt=0)
    D_mm = ctx.req("params.drive_diameter_mm", "Drive pulley / roller diameter (mm)", p.drive_diameter_mm, gt=0)
    m_belt, o_b = ctx.opt("Belt moving mass", p.belt_mass_kg, 0.0,
                          "Belt / chain moving mass not entered — taken as 0 kg.", ge=0)
    eta, o_e = ctx.opt("Drive efficiency", p.drive_efficiency, 1.0,
                       "Gearbox drives the pulley directly (no extra chain/belt stage, efficiency 1.0).", gt=0, le=1)
    F_x, o_x = ctx.opt("Extra force", p.extra_force_n, 0.0,
                       "No extra process forces (scrapers, pushers…) entered — taken as 0 N.", ge=0)
    ctx.checkpoint()
    m_load = _compute_load_mass(ctx, req, part)

    th = math.radians(theta)
    r = D_mm / 2000
    m = ctx.step("moving_mass", "Total moving mass", "m = m_load + m_belt",
                 f"m = {_f(m_load)} + {_f(m_belt)}", m_load + m_belt, "kg",
                 {"m_load": (m_load, "kg", "DERIVED"), "m_belt": (m_belt, "kg", o_b)})
    F_g = ctx.step("f_gravity", "Force to lift the load up the incline", "F_grav = m × g × sin θ",
                   f"F_grav = {_f(m)} × {G} × sin {_f(theta)}°", m * G * math.sin(th), "N",
                   {"θ": (theta, "deg", "USER"), "g": (G, "m/s²", "CONSTANT")})
    F_f = ctx.step("f_friction", "Friction force", "F_fric = μ × m × g × cos θ",
                   f"F_fric = {_f(mu)} × {_f(m)} × {G} × cos {_f(theta)}°", mu * m * G * math.cos(th), "N",
                   {"μ": (mu, "", "USER")},
                   note="Uses the full moving mass (conservative: the belt return side really carries less).")
    F_run = ctx.step("f_run", "Steady running force", "F_run = F_grav + F_fric + F_extra",
                     f"F_run = {_f(F_g)} + {_f(F_f)} + {_f(F_x)}", F_g + F_f + F_x, "N",
                     {"F_extra": (F_x, "N", o_x)})
    a = ctx.step("accel", "Acceleration", "a = v / t_acc", f"a = {_f(v)} / {_f(t_acc)}", v / t_acc, "m/s²",
                 {"v": (v, "m/s", "USER"), "t_acc": (t_acc, "s", "USER")},
                 note="Linear speed ramp assumed.")
    F_a = ctx.step("f_accel", "Extra force to accelerate", "F_acc = m × a", f"F_acc = {_f(m)} × {_f(a)}", m * a, "N")
    T_run = ctx.step("t_run", "Running torque at gearbox output", "T_run = F_run × (D/2) / η",
                     f"T_run = {_f(F_run)} × {_f(r)} / {_f(eta)}", F_run * r / eta, "N·m",
                     {"D": (D_mm, "mm", "USER"), "η": (eta, "", o_e)})
    T_pk = ctx.step("t_peak", "Peak torque while accelerating", "T_peak = (F_run + F_acc) × (D/2) / η",
                    f"T_peak = ({_f(F_run)} + {_f(F_a)}) × {_f(r)} / {_f(eta)}", (F_run + F_a) * r / eta, "N·m")
    n = ctx.step("n_out", "Required output speed", "n = 60 × v / (π × D)",
                 f"n = 60 × {_f(v)} / (π × {_f(D_mm/1000)})", 60 * v / (math.pi * D_mm / 1000), "rpm")
    if theta > 0:
        ctx.warnings.append("Inclined conveyor: the load can run back when stopped. "
                            "A brake or self-locking drive may be needed.")
    hold = F_g * r / eta if theta > 0 else 0.0
    return {"points": [("Running", n, T_run, T_pk)], "envelope": (n, T_run, T_pk),
            "hold_torque": hold, "t_acc": t_acc}


def _hoist(ctx: _Ctx, req: SizingRequest) -> Dict[str, Any]:
    p = req.params
    part = _collect_part(ctx, req)
    v = ctx.req("params.speed_m_s", "Lifting speed (m/s)", p.speed_m_s, gt=0)
    t_acc = ctx.req("params.accel_time_s", "Time to reach full speed (s)", p.accel_time_s, gt=0)
    D_mm = ctx.req("params.drum_diameter_mm", "Drum diameter to rope centre (mm)", p.drum_diameter_mm, gt=0)
    falls, o_f = ctx.opt("Rope falls", p.rope_falls, 1, "Single rope line (1 fall) assumed.", ge=1)
    eta, o_e = ctx.opt("Rope / sheave efficiency", p.rope_efficiency, 1.0,
                       "Rope and sheave losses not entered — efficiency 1.0 used.", gt=0, le=1)
    m_hook, o_h = ctx.opt("Hook / carriage mass", p.hook_mass_kg, 0.0,
                          "No hook / carriage mass entered — taken as 0 kg.", ge=0)
    m_cw, o_cw = ctx.opt("Counterweight", p.counterweight_kg, 0.0, "No counterweight.", ge=0)
    ctx.checkpoint()
    m_load = _compute_load_mass(ctx, req, part)
    if m_cw >= m_load + m_hook:
        ctx.errors.append("Counterweight is heavier than the load — this hoist model does not cover that case.")
        ctx.checkpoint()

    m_net = ctx.step("net_mass", "Net hanging mass", "m_net = m_load + m_hook − m_cw",
                     f"m_net = {_f(m_load)} + {_f(m_hook)} − {_f(m_cw)}", m_load + m_hook - m_cw, "kg",
                     {"m_hook": (m_hook, "kg", o_h), "m_cw": (m_cw, "kg", o_cw)})
    m_mov = m_load + m_hook + m_cw
    a = ctx.step("accel", "Acceleration", "a = v / t_acc", f"a = {_f(v)} / {_f(t_acc)}", v / t_acc, "m/s²",
                 note="Linear speed ramp assumed.")
    F_s = ctx.step("f_static", "Static rope pull", "F_static = m_net × g",
                   f"F_static = {_f(m_net)} × {G}", m_net * G, "N", {"g": (G, "m/s²", "CONSTANT")})
    F_p = ctx.step("f_peak", "Rope pull while accelerating upward", "F_peak = m_net × g + m_moving × a",
                   f"F_peak = {_f(m_net)} × {G} + {_f(m_mov)} × {_f(a)}", m_net * G + m_mov * a, "N")
    r = D_mm / 2000
    k = falls * eta
    T_run = ctx.step("t_run", "Holding / running torque at drum", "T_run = F_static / (falls × η) × (D/2)",
                     f"T_run = {_f(F_s)} / ({falls} × {_f(eta)}) × {_f(r)}", F_s / k * r, "N·m",
                     {"falls": (falls, "", o_f), "η": (eta, "", o_e), "D": (D_mm, "mm", "USER")})
    T_pk = ctx.step("t_peak", "Peak torque at drum", "T_peak = F_peak / (falls × η) × (D/2)",
                    f"T_peak = {_f(F_p)} / ({falls} × {_f(eta)}) × {_f(r)}", F_p / k * r, "N·m")
    n = ctx.step("n_out", "Required drum speed", "n = 60 × (falls × v) / (π × D)",
                 f"n = 60 × ({falls} × {_f(v)}) / (π × {_f(D_mm/1000)})",
                 60 * falls * v / (math.pi * D_mm / 1000), "rpm")
    ctx.warnings.append("Vertical load: a holding brake or self-locking drive is required. "
                        "Lowering feeds energy back into the drive.")
    ctx.warnings.append("This is a sizing estimate, not a certified hoist design (FEM/ISO hoist "
                        "classification is out of scope).")
    return {"points": [("Lifting", n, T_run, T_pk)], "envelope": (n, T_run, T_pk),
            "hold_torque": T_run, "t_acc": t_acc}


def _rotary_table(ctx: _Ctx, req: SizingRequest) -> Dict[str, Any]:
    p = req.params
    arr = ctx.req("params.load_arrangement", "How the load sits on the table", p.load_arrangement)
    mode = ctx.req("params.motion_mode", "Continuous rotation or indexing", p.motion_mode)
    if arr == "custom_inertia":
        J_in = ctx.req("params.load_inertia_kg_m2", "Load inertia (kg·m²)", p.load_inertia_kg_m2, gt=0)
    elif arr is not None:
        part = _collect_part(ctx, req)
        R_mm = ctx.req("params.load_radius_mm", "Load radius (mm)", p.load_radius_mm, gt=0)
    J_tab, o_t = ctx.opt("Table inertia", p.table_inertia_kg_m2, 0.0,
                         "Table's own inertia not entered — taken as 0 (results will be low if the table is heavy).",
                         ge=0)
    T_f, o_f = ctx.opt("Bearing friction torque", p.friction_torque_nm, 0.0,
                       "Bearing friction torque not entered — taken as 0 N·m.", ge=0)
    eta, o_e = ctx.opt("Drive efficiency", p.drive_efficiency, 1.0,
                       "Gearbox drives the table directly (efficiency 1.0).", gt=0, le=1)
    if mode == "continuous":
        n_t = ctx.req("params.target_speed_rpm", "Table speed (rpm)", p.target_speed_rpm, gt=0)
        t_acc = ctx.req("params.accel_time_s", "Time to reach full speed (s)", p.accel_time_s, gt=0)
    elif mode == "index":
        ang = ctx.req("params.index_angle_deg", "Index angle per move (deg)", p.index_angle_deg, gt=0)
        t_mv = ctx.req("params.index_time_s", "Time for one index move (s)", p.index_time_s, gt=0)
    ctx.checkpoint()

    if arr == "custom_inertia":
        J_load = ctx.step("j_load", "Load inertia (entered)", "J_load (entered from CAD)", "J_load", J_in, "kg·m²",
                          {"J_load": (J_in, "kg·m²", "USER")})
    else:
        m_load = _compute_load_mass(ctx, req, part)
        R = R_mm / 1000
        if arr == "solid_disc":
            J_load = ctx.step("j_load", "Load inertia (solid disc on the axis)", "J_load = ½ × m × R²",
                              f"J_load = 0.5 × {_f(m_load)} × {_f(R)}²", 0.5 * m_load * R**2, "kg·m²",
                              {"R": (R_mm, "mm", "USER")})
        else:
            J_load = ctx.step("j_load", "Load inertia (parts at a radius)", "J_load = m × R²",
                              f"J_load = {_f(m_load)} × {_f(R)}²", m_load * R**2, "kg·m²",
                              {"R": (R_mm, "mm", "USER")},
                              note="Treats each part as small compared with its radius.")

    J = ctx.step("j_total", "Total inertia", "J = J_load + J_table",
                 f"J = {_f(J_load)} + {_f(J_tab)}", J_load + J_tab, "kg·m²",
                 {"J_table": (J_tab, "kg·m²", o_t)})
    if mode == "continuous":
        w = ctx.step("omega", "Angular speed", "ω = 2π × n / 60", f"ω = 2π × {_f(n_t)} / 60",
                     2 * math.pi * n_t / 60, "rad/s", {"n": (n_t, "rpm", "USER")})
        alpha = ctx.step("alpha", "Angular acceleration", "α = ω / t_acc", f"α = {_f(w)} / {_f(t_acc)}",
                         w / t_acc, "rad/s²", {"t_acc": (t_acc, "s", "USER")}, note="Linear speed ramp assumed.")
        n = n_t
        index = None
    else:
        phi = math.radians(ang)
        w = ctx.step("omega", "Peak angular speed (triangular move)", "ω_peak = 2 × Δφ / t_move",
                     f"ω_peak = 2 × {_f(phi)} / {_f(t_mv)}", 2 * phi / t_mv, "rad/s",
                     {"Δφ": (ang, "deg", "USER"), "t_move": (t_mv, "s", "USER")},
                     note="Accelerate for half the move, decelerate for the other half.")
        alpha = ctx.step("alpha", "Angular acceleration", "α = 4 × Δφ / t_move²",
                         f"α = 4 × {_f(phi)} / {_f(t_mv)}²", 4 * phi / t_mv**2, "rad/s²")
        n = ctx.step("n_out", "Peak table speed", "n = ω_peak × 60 / 2π", f"n = {_f(w)} × 60 / 2π",
                     w * 60 / (2 * math.pi), "rpm")
        t_acc = t_mv / 2
        index = t_mv
    T_run = ctx.step("t_run", "Running torque (friction)", "T_run = T_friction / η",
                     f"T_run = {_f(T_f)} / {_f(eta)}", T_f / eta, "N·m",
                     {"T_friction": (T_f, "N·m", o_f), "η": (eta, "", o_e)})
    T_pk = ctx.step("t_peak", "Peak torque while accelerating", "T_peak = (J × α + T_friction) / η",
                    f"T_peak = ({_f(J)} × {_f(alpha)} + {_f(T_f)}) / {_f(eta)}", (J * alpha + T_f) / eta, "N·m")
    return {"points": [("Rotating" if index is None else "Index move", n, T_run, T_pk)],
            "envelope": (n, T_run, T_pk), "hold_torque": 0.0, "t_acc": t_acc, "index_move_s": index}


def _linear_axis(ctx: _Ctx, req: SizingRequest, kind: str) -> Dict[str, Any]:
    p = req.params
    part = _collect_part(ctx, req)
    theta = ctx.req("params.axis_angle_deg", "Axis angle (deg, 0 = horizontal, 90 = vertical)",
                    p.axis_angle_deg, ge=0, le=90)
    mu = ctx.req("params.guide_friction", "Guide friction coefficient", p.guide_friction, ge=0, le=1)
    v = ctx.req("params.speed_m_s", "Travel speed (m/s)", p.speed_m_s, gt=0)
    t_acc = ctx.req("params.accel_time_s", "Time to reach full speed (s)", p.accel_time_s, gt=0)
    F_p, o_p = ctx.opt("Process force", p.process_force_n, 0.0,
                       "No process force (pressing, cutting…) entered — taken as 0 N.", ge=0)
    if kind == "screw":
        L_mm = ctx.req("params.screw_lead_mm", "Screw lead (mm per turn)", p.screw_lead_mm, gt=0)
        eta = ctx.req("params.screw_efficiency", "Screw efficiency (from screw datasheet)",
                      p.screw_efficiency, gt=0, le=1)
        o_e = "USER"
        J_s, o_j = ctx.opt("Screw inertia", p.screw_inertia_kg_m2, 0.0,
                           "Screw inertia not entered — taken as 0.", ge=0)
    else:
        D_mm = ctx.req("params.pinion_diameter_mm", "Pinion / pulley pitch diameter (mm)",
                       p.pinion_diameter_mm, gt=0)
        eta, o_e = ctx.opt("Drive efficiency", p.drive_efficiency, 1.0,
                           "Rack/belt losses not entered — efficiency 1.0 used.", gt=0, le=1)
    ctx.checkpoint()
    m_load = _compute_load_mass(ctx, req, part)

    th = math.radians(theta)
    F_run = ctx.step("f_run", "Steady axial force",
                     "F_run = m × g × (sin θ + μ × cos θ) + F_process",
                     f"F_run = {_f(m_load)} × {G} × (sin {_f(theta)}° + {_f(mu)} × cos {_f(theta)}°) + {_f(F_p)}",
                     m_load * G * (math.sin(th) + mu * math.cos(th)) + F_p, "N",
                     {"θ": (theta, "deg", "USER"), "μ": (mu, "", "USER"), "F_process": (F_p, "N", o_p),
                      "g": (G, "m/s²", "CONSTANT")})
    a = ctx.step("accel", "Acceleration", "a = v / t_acc", f"a = {_f(v)} / {_f(t_acc)}", v / t_acc, "m/s²",
                 {"v": (v, "m/s", "USER"), "t_acc": (t_acc, "s", "USER")}, note="Linear speed ramp assumed.")
    F_acc = ctx.step("f_peak", "Axial force while accelerating", "F_peak = F_run + m × a",
                     f"F_peak = {_f(F_run)} + {_f(m_load)} × {_f(a)}", F_run + m_load * a, "N")
    if kind == "screw":
        L = L_mm / 1000
        T_run = ctx.step("t_run", "Running torque at screw", "T_run = F_run × lead / (2π × η)",
                         f"T_run = {_f(F_run)} × {_f(L)} / (2π × {_f(eta)})", F_run * L / (2 * math.pi * eta), "N·m",
                         {"lead": (L_mm, "mm", "USER"), "η": (eta, "", o_e)})
        alpha = 2 * math.pi * a / L
        T_pk = ctx.step("t_peak", "Peak torque at screw", "T_peak = F_peak × lead / (2π × η) + J_screw × α",
                        f"T_peak = {_f(F_acc)} × {_f(L)} / (2π × {_f(eta)}) + {_f(J_s)} × {_f(alpha)}",
                        F_acc * L / (2 * math.pi * eta) + J_s * alpha, "N·m",
                        {"J_screw": (J_s, "kg·m²", o_j)})
        n = ctx.step("n_out", "Required screw speed", "n = 60 × v / lead",
                     f"n = 60 × {_f(v)} / {_f(L)}", 60 * v / L, "rpm")
        hold = m_load * G * math.sin(th) * L / (2 * math.pi * eta)
    else:
        r = D_mm / 2000
        T_run = ctx.step("t_run", "Running torque at pinion", "T_run = F_run × (D/2) / η",
                         f"T_run = {_f(F_run)} × {_f(r)} / {_f(eta)}", F_run * r / eta, "N·m",
                         {"D": (D_mm, "mm", "USER"), "η": (eta, "", o_e)})
        T_pk = ctx.step("t_peak", "Peak torque at pinion", "T_peak = F_peak × (D/2) / η",
                        f"T_peak = {_f(F_acc)} × {_f(r)} / {_f(eta)}", F_acc * r / eta, "N·m")
        n = ctx.step("n_out", "Required pinion speed", "n = 60 × v / (π × D)",
                     f"n = 60 × {_f(v)} / (π × {_f(D_mm/1000)})", 60 * v / (math.pi * D_mm / 1000), "rpm")
        hold = m_load * G * math.sin(th) * r / eta
    if theta > 0:
        ctx.warnings.append("Inclined / vertical axis: the load can drive the axis backwards when power is off. "
                            "A brake may be needed.")
    return {"points": [("Moving", n, T_run, T_pk)], "envelope": (n, T_run, T_pk),
            "hold_torque": hold, "t_acc": t_acc}


def _winding(ctx: _Ctx, req: SizingRequest) -> Dict[str, Any]:
    p = req.params
    rho = ctx.req("material.density_kg_m3", "Material density (kg/m³)", req.material.density_kg_m3, gt=0)
    F_t = ctx.req("params.web_tension_n", "Web tension (N)", p.web_tension_n, gt=0)
    v = ctx.req("params.speed_m_s", "Line speed (m/s)", p.speed_m_s, gt=0)
    t_acc = ctx.req("params.accel_time_s", "Time to reach full speed (s)", p.accel_time_s, gt=0)
    Dc = ctx.req("params.core_diameter_mm", "Core diameter (mm)", p.core_diameter_mm, gt=0)
    Dm = ctx.req("params.full_roll_diameter_mm", "Full roll diameter (mm)", p.full_roll_diameter_mm, gt=0)
    W = ctx.req("params.roll_width_mm", "Roll width (mm)", p.roll_width_mm, gt=0)
    J_c, o_c = ctx.opt("Core inertia", p.core_inertia_kg_m2, 0.0,
                       "Core / shaft inertia not entered — taken as 0.", ge=0)
    if Dc is not None and Dm is not None and Dm <= Dc:
        ctx.errors.append("Full roll diameter must be larger than the core diameter.")
    ctx.checkpoint()

    dc, dm, w = Dc / 1000, Dm / 1000, W / 1000
    m_roll = ctx.step("roll_mass", "Material mass on a full roll", "m_roll = ρ × π/4 × (D_max² − D_core²) × W",
                      f"m_roll = {_f(rho)} × π/4 × ({_f(dm)}² − {_f(dc)}²) × {_f(w)}",
                      rho * math.pi / 4 * (dm**2 - dc**2) * w, "kg",
                      {"ρ": (rho, "kg/m³", "USER"), "D_max": (Dm, "mm", "USER"),
                       "D_core": (Dc, "mm", "USER"), "W": (W, "mm", "USER")})
    J = ctx.step("j_roll", "Full roll inertia", "J = ½ × m_roll × (r_max² + r_core²) + J_core",
                 f"J = 0.5 × {_f(m_roll)} × ({_f(dm/2)}² + {_f(dc/2)}²) + {_f(J_c)}",
                 0.5 * m_roll * ((dm / 2)**2 + (dc / 2)**2) + J_c, "kg·m²",
                 {"J_core": (J_c, "kg·m²", o_c)})
    ctx.step("p_web", "Web power (same at every diameter)", "P = F_t × v",
             f"P = {_f(F_t)} × {_f(v)}", F_t * v, "W", {"F_t": (F_t, "N", "USER"), "v": (v, "m/s", "USER")})
    T_max = ctx.step("t_run_full", "Torque at full roll", "T_full = F_t × D_max / 2",
                     f"T_full = {_f(F_t)} × {_f(dm)} / 2", F_t * dm / 2, "N·m")
    n_min = ctx.step("n_full", "Speed at full roll", "n_full = 60 × v / (π × D_max)",
                     f"n_full = 60 × {_f(v)} / (π × {_f(dm)})", 60 * v / (math.pi * dm), "rpm")
    T_min = ctx.step("t_run_core", "Torque at empty core", "T_core = F_t × D_core / 2",
                     f"T_core = {_f(F_t)} × {_f(dc)} / 2", F_t * dc / 2, "N·m")
    n_max = ctx.step("n_core", "Speed at empty core", "n_core = 60 × v / (π × D_core)",
                     f"n_core = 60 × {_f(v)} / (π × {_f(dc)})", 60 * v / (math.pi * dc), "rpm")
    a = v / t_acc
    T_pk_full = ctx.step("t_peak", "Peak torque at full roll while accelerating",
                         "T_peak = T_full + J × (2 × a / D_max)",
                         f"T_peak = {_f(T_max)} + {_f(J)} × (2 × {_f(a)} / {_f(dm)})",
                         T_max + J * (2 * a / dm), "N·m", note="Linear speed ramp assumed.")
    T_pk_core = T_min + J_c * (2 * a / dc)
    ctx.warnings.append(
        f"Winding needs a speed-controlled motor: the shaft must run from {_f(n_min)} rpm (full roll) "
        f"up to {_f(n_max)} rpm (empty core). Selection checks the drive can give the full-roll torque "
        f"all the way up to the core speed (conservative)."
    )
    return {"points": [("Full roll", n_min, T_max, T_pk_full), ("Empty core", n_max, T_min, T_pk_core)],
            "envelope": (n_max, T_max, T_pk_full), "hold_torque": None, "t_acc": t_acc, "continuous_only": True}


_MODELS = {
    "conveyor": _conveyor,
    "hoist": _hoist,
    "rotary_table": _rotary_table,
    "screw_axis": lambda c, r: _linear_axis(c, r, "screw"),
    "rack_pinion_axis": lambda c, r: _linear_axis(c, r, "rack"),
    "winding": _winding,
}


# ─────────────────────────────────────────────────────────────
# Duty cycle + service factor (spec §4)
# ─────────────────────────────────────────────────────────────

def _continuous_torque(ctx: _Ctx, req: SizingRequest, model: Dict[str, Any]) -> float:
    n, T_run, T_pk = model["envelope"]
    d = req.duty
    t_acc = model["t_acc"]

    if model.get("index_move_s") is not None:
        t_dw, o_d = ctx.opt("Dwell time", d.dwell_time_s, 0.0,
                            "No dwell time between index moves entered — table assumed to move non-stop.", ge=0)
        ctx.checkpoint()
        t_mv = model["index_move_s"]
        # accelerate t/2 at T_peak, decelerate t/2 at T_peak (conservative), dwell at 0
        T_cont = ctx.step("t_rms", "Thermal (RMS) torque over one index cycle",
                          "T_rms = √( (T_peak² × t_move) / (t_move + t_dwell) )",
                          f"T_rms = √( ({_f(T_pk)}² × {_f(t_mv)}) / ({_f(t_mv)} + {_f(t_dw)}) )",
                          math.sqrt(T_pk**2 * t_mv / (t_mv + t_dw)), "N·m",
                          {"t_dwell": (t_dw, "s", o_d)},
                          note="Deceleration counted at full peak torque (conservative).")
    elif d.run_time_s is not None and not model.get("continuous_only"):
        t_run = ctx.req("duty.run_time_s", "Run time per cycle (s)", d.run_time_s, ge=0)
        t_dw, o_d = ctx.opt("Dwell time", d.dwell_time_s, 0.0, "No dwell time per cycle entered — taken as 0 s.", ge=0)
        ctx.checkpoint()
        T_hold = model["hold_torque"] or 0.0
        total = 2 * t_acc + t_run + t_dw
        T_cont = ctx.step("t_rms", "Thermal (RMS) torque over one cycle",
                          "T_rms = √( (2 × T_peak² × t_acc + T_run² × t_run + T_hold² × t_dwell) / (2 × t_acc + t_run + t_dwell) )",
                          f"T_rms = √( (2 × {_f(T_pk)}² × {_f(t_acc)} + {_f(T_run)}² × {_f(t_run)} + "
                          f"{_f(T_hold)}² × {_f(t_dw)}) / {_f(total)} )",
                          math.sqrt((2 * T_pk**2 * t_acc + T_run**2 * t_run + T_hold**2 * t_dw) / total), "N·m",
                          {"t_run": (t_run, "s", "USER"), "t_dwell": (t_dw, "s", o_d)},
                          note="Deceleration counted at full peak torque (conservative). "
                               "Holding torque during dwell assumes the motor holds the load (no brake).")
    else:
        if d.run_time_s is not None and model.get("continuous_only"):
            ctx.assumptions.append("Winding is treated as continuous running; the cycle times entered are not used.")
        else:
            ctx.assumptions.append("Continuous running assumed (no stop/start cycle entered): "
                                   "continuous torque = running torque.")
        T_cont = T_run

    if T_cont <= 0:
        ctx.assumptions.append("Running torque is zero (no friction or load force entered), so the continuous "
                               "torque requirement is set equal to the peak torque (conservative).")
        T_cont = T_pk
    return T_cont


def _collect_duty(ctx: _Ctx, req: SizingRequest):
    """Collected up-front so duty gaps are reported together with all other missing inputs."""
    d = req.duty
    lc = ctx.req("duty.load_class", "How smooth or shock-loaded the work is", d.load_class)
    h = ctx.req("duty.hours_per_day", "Running hours per day", d.hours_per_day, gt=0, le=24)
    if d.service_factor_override is not None:
        ctx._check_range("Service factor override", d.service_factor_override, 0, None, 5)
    return lc, h


def _service_factor(ctx: _Ctx, req: SizingRequest, lc: str, h: float) -> float:
    d = req.duty
    sf_table = service_factor_for(lc, h)
    ctx.step("sf_table", "Service factor from table",
             "SF = table[load class, hours/day]",
             f"SF = table[{LOAD_CLASS_LABELS[lc]}, {hours_band_label(h)}]", sf_table, "",
             {"load_class": (lc, "", "USER"), "hours_per_day": (h, "h", "USER")},
             note=f"Default table version {DEFAULTS_VERSION} — awaiting engineering sign-off.")
    if d.service_factor_override is not None:
        sf = d.service_factor_override
        ctx.step("sf_used", "Service factor used (user override)", "SF = user override",
                 f"SF (table said {_f(sf_table)})", sf, "", {"SF": (sf, "", "USER")})
        return sf
    return sf_table


# ─────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────

def size_application(req: SizingRequest) -> SizingResult:
    ctx = _Ctx(req.application)
    _record_material(ctx, req)
    try:
        lc, h = _collect_duty(ctx, req)
        model = _MODELS[req.application](ctx, req)
        T_cont = _continuous_torque(ctx, req, model)
        sf = _service_factor(ctx, req, lc, h)
    except _Incomplete:
        return SizingResult(
            status="INVALID_INPUT" if ctx.errors else "REQUIREMENTS_INCOMPLETE",
            application=req.application,
            missing_inputs=ctx.missing, errors=ctx.errors,
            steps=ctx.steps, assumptions=ctx.assumptions, warnings=ctx.warnings,
            material_notes=ctx.material_notes, defaults_version=DEFAULTS_VERSION,
        )

    n, _, T_pk = model["envelope"]
    T_d = ctx.step("t_design", "Design continuous torque", "T_design = T_continuous × SF",
                   f"T_design = {_f(T_cont)} × {_f(sf)}", T_cont * sf, "N·m")
    T_dp = ctx.step("t_design_peak", "Design peak torque", "T_design_peak = T_peak × SF",
                    f"T_design_peak = {_f(T_pk)} × {_f(sf)}", T_pk * sf, "N·m")
    P = ctx.step("power", "Required output power", "P = T_design × 2π × n / 60",
                 f"P = {_f(T_d)} × 2π × {_f(n)} / 60", T_d * 2 * math.pi * n / 60, "W")

    return SizingResult(
        status="SIZED",
        application=req.application,
        steps=ctx.steps,
        operating_points=[OperatingPoint(label=l, speed_rpm=s, run_torque_nm=tr, peak_torque_nm=tp)
                          for (l, s, tr, tp) in model["points"]],
        requirement=SizedRequirement(
            required_speed_rpm=n, required_torque_nm=T_cont, peak_torque_nm=T_pk,
            service_factor=sf, design_torque_nm=T_d, design_peak_torque_nm=T_dp, required_power_w=P,
        ),
        assumptions=ctx.assumptions, warnings=ctx.warnings,
        material_notes=ctx.material_notes, defaults_version=DEFAULTS_VERSION,
    )
