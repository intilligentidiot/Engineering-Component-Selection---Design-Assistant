# Stage 8 — Application-Based Sizing: Inputs & Equations Specification

**Status:** IMPLEMENTED with conservative defaults (2026-10-14). The defaults still need engineering sign-off: see [ENGINEERING_DEFAULTS_TO_REVIEW.md](ENGINEERING_DEFAULTS_TO_REVIEW.md).
**Scope:** This document defines how the tool turns *material + geometry + application + motion/load* inputs into *required output speed, torque, power and service factor*. Those values feed the existing motor/gearbox selection engine (Source A + Source B).

The rules below carry over from earlier stages and are not up for negotiation:

1. **AI only interprets language.** The parser may pull values from text. It must never supply densities, coefficients, efficiencies or results.
2. **Every number is either a user input, a sourced library value, a physical constant, or a computed result.** Each one is shown in the trace with its origin.
3. **Missing inputs are never defaulted silently.** A missing required input stops the calculation with `REQUIREMENTS_INCOMPLETE` and a list of what is missing.
4. **Only the equations in this document are used.** An application that isn't defined here isn't supported yet. The tool says so; it does not approximate.

---

## 1. Pipeline and data contract

```
MaterialInput ─► PartInput ─► LoadModel ─► ApplicationModel ─► MotionProfile
                                   │
                                   ▼
                      OutputShaftRequirement (per operating point)
                                   │
                         + DutyClass ─► Service Factor
                         + Constraints (voltage, envelope…)
                                   ▼
                     SizedRequirement ─► existing selection engine
```

Each step emits one or more `CalculationTrace` objects (`app/engine/trace.py`). The UI shows the full chain:
material → density → volume → mass → force → torque → speed → power → SF → design requirement.

### 1.1 Origin tags (new field on every trace input)

| Tag | Meaning |
|---|---|
| `USER` | Entered or confirmed by the engineer |
| `LIBRARY:<id>` | Taken from the material/coefficient library, which has a citation |
| `CONSTANT` | Physical constant (g = 9.80665 m/s², π) |
| `DERIVED:<calc_id>` | Output of an earlier trace step |
| `AI_EXTRACTED` | Parsed from text. **The user must confirm it before it counts as `USER`.** |

### 1.2 Units

All internal maths uses SI: m, kg, s, N, N·m, rad/s, W. The UI may accept mm, g/cm³ and so on, but converts on entry and shows the conversion in the trace. RPM is used only at the boundaries: `n = ω · 60 / (2π)`.

---

## 2. Material and part → mass

### 2.1 Material inputs

| Field | Unit | Required | Used in equations? |
|---|---|---|---|
| `material_name` | text | yes | No. Used for identification and library lookup only |
| `density` ρ | kg/m³ | yes (unless mass is given directly) | **Yes**: m = ρ·V |
| `hardness` (scale + value, e.g. Shore A 70) | — | optional | **No (see 2.2)** |

### 2.2 Hardness: an explicit decision

There is **no deterministic equation** from Shore A/D hardness to force, friction or torque that holds across materials. Published Shore-to-modulus correlations are empirical, depend on the material, and carry wide scatter. So hardness is:

- **recorded and shown** with the material,
- **not used** in any v1 sizing equation,
- reserved for a possible later application model (for example a cutting or compression process) where a *measured* process force or coefficient for that material is supplied.

If hardness changes a coefficient the engineer needs (such as friction of a soft part on a belt), the engineer enters that coefficient directly as a `USER` value. The tool does **not** convert hardness into μ.

### 2.3 Geometry → volume

| Shape | Inputs | Volume |
|---|---|---|
| Rectangular block | L, W, H | V = L·W·H |
| Solid cylinder | D, L | V = π·D²·L / 4 |
| Hollow cylinder / tube | D_o, D_i, L | V = π·(D_o² − D_i²)·L / 4 |
| Sphere | D | V = π·D³ / 6 |
| Direct volume (from CAD) | V | V |
| **Direct mass** (bypass) | m | not needed; skip ρ·V |

### 2.4 Mass

```
m_part  = ρ · V
m_load  = N_parts · m_part + m_carrier
```

`N_parts` is the number of parts moved at once. `m_carrier` covers fixtures, pallets, belt sections, tables and so on (`USER`, may be 0).

### 2.5 Material library

The library is a local table: `material_id, name, density_kg_m3, hardness_scale, hardness_value, source_citation, verified_by, verified_date`.

- **Density values must not be pre-filled from AI or memory.** Every library row needs a datasheet or standard citation, the same rule as motor specs.
- If a material is missing from the library, the user enters ρ directly (`USER`).

---

## 3. Application models (v1 set)

Notation: g = 9.80665 m/s². Every result here is at the **gearbox output shaft**, which is what the selection engine compares against.

Every model produces these **operating points**:

| Symbol | Meaning |
|---|---|
| `T_run` | Steady-state torque at constant speed |
| `T_acc` | Torque during acceleration (includes T_run) |
| `n_out` | Required output-shaft speed |
| `P_run`, `P_peak` | T·ω at run and at peak |

`a = v / t_acc` and `α = ω / t_acc` assume a linear (trapezoidal) ramp. That assumption is printed in the trace.

### 3.1 Belt / roller conveyor, unit loads (horizontal or inclined)

**Scope:** discrete parts on a belt or driven rollers. **Not** bulk material, because CEMA bulk-conveyor methods are out of scope for v1.

| Input | Unit | Origin |
|---|---|---|
| m_load (from §2), m_belt (moving belt mass) | kg | DERIVED / USER |
| incline θ (0 = horizontal) | deg | USER |
| μ: belt-on-bed sliding coefficient **or** rolling-resistance coefficient | — | USER (no default) |
| belt speed v | m/s | USER |
| acceleration time t_acc | s | USER |
| drive pulley diameter D | m | USER |
| η_drive (pulley/chain stage between gearbox and pulley; 1.0 if direct) | — | USER |
| F_extra (scrapers, pushers, process force) | N | USER, may be 0 |

```
m        = m_load + m_belt
F_grav   = m · g · sin θ
F_fric   = μ · m · g · cos θ
F_run    = F_grav + F_fric + F_extra
F_acc    = m · a ,  a = v / t_acc
r        = D / 2
T_run    = F_run · r / η_drive
T_acc    = (F_run + F_acc) · r / η_drive   (+ J_pulleys · α if pulley inertia is given)
n_out    = 60 · v / (π · D)
```

Note: the friction term uses the full moving mass. That is conservative, because the return side of the belt really sees less normal force. The trace states this.

### 3.2 Vertical lift / hoist (drum and rope)

| Input | Unit | Origin |
|---|---|---|
| m_load, m_hook (hook/carriage) | kg | DERIVED / USER |
| m_cw counterweight | kg | USER, may be 0 |
| lift speed v_load | m/s | USER |
| t_acc | s | USER |
| drum diameter D_drum (to rope centreline) | m | USER |
| reeving ratio i_r (rope falls; 1 = single line) | — | USER |
| η_rope (reeving/sheave efficiency) | — | USER |

```
m_net    = m_load + m_hook − m_cw
F_static = m_net · g
F_peak   = m_net · g + (m_load + m_hook + m_cw) · a        (worst case: lifting while accelerating)
F_drum   = F / (i_r · η_rope)
T_run    = F_drum(F_static) · D_drum / 2
T_acc    = F_drum(F_peak)   · D_drum / 2
v_rope   = i_r · v_load
n_out    = 60 · v_rope / (π · D_drum)
```

**Mandatory flags** (shown, never decided by the tool): a vertical load needs a holding brake or a self-locking drive; lowering is regenerative. Hoisting standards such as FEM/ISO classification are **out of scope**. The UI states that this result is not a certified hoist design.

### 3.3 Rotary table / turntable / indexer

| Input | Unit | Origin |
|---|---|---|
| Load inertia J_load (from shape, below) or user-supplied | kg·m² | DERIVED / USER |
| Table inertia J_table | kg·m² | USER (from CAD) |
| Either target speed n_out **or** index move (angle Δφ in time t_move) | rpm / deg, s | USER |
| t_acc (for continuous rotation) | s | USER |
| Bearing friction: friction torque T_f directly, **or** μ_b · (m_total·g) · r_b | N·m | USER |
| η_drive (belt/pinion stage after the gearbox) | — | USER |

Load inertia about the table axis:

| Load form | J |
|---|---|
| Solid disc/cylinder on axis | ½ · m · r² |
| Hollow cylinder on axis | ½ · m · (r_o² + r_i²) |
| N parts at radius R (small vs R) | N · m_part · R² |
| Part off-axis (parallel axis) | J_cm + m · d² |

```
J_total = J_load + J_table
Continuous: ω = 2π · n_out / 60 ;  α = ω / t_acc
Index (triangular profile): ω_peak = 2·Δφ / t_move ; α = 4·Δφ / t_move²
T_run   = T_f / η_drive
T_acc   = (J_total · α + T_f) / η_drive
```

### 3.4 Linear axis: lead screw / ball screw

| Input | Unit | Origin |
|---|---|---|
| m_load + m_carriage | kg | DERIVED / USER |
| axis angle θ (0 horizontal, 90 vertical) | deg | USER |
| μ_guide (linear guide friction) | — | USER |
| F_process (pressing, cutting…) | N | USER, may be 0 |
| speed v, t_acc | m/s, s | USER |
| lead L | m/rev | USER |
| η_screw | — | USER or screw datasheet (a ball-screw efficiency is **not** assumed) |
| J_screw (or screw d, length, ρ_screw → J = π·ρ·ℓ·d⁴/32) | kg·m² | USER / DERIVED |

```
F_run   = m·g·(sin θ + μ_guide·cos θ) + F_process
F_acc   = F_run + m·a
T_run   = F_run · L / (2π · η_screw)
T_acc   = F_acc · L / (2π · η_screw) + J_screw · α ,  α = 2π · a / L
n_out   = 60 · v / L
```

Flag on vertical axes: back-driving and brake requirement (same rule as 3.2).

### 3.5 Linear axis: rack & pinion / timing belt

This is the same as §3.4 with the pinion or pulley pitch diameter D in place of the screw:
`T = F · (D/2) / η_drive`, `n_out = 60·v/(π·D)`, `α = a / (D/2)`.

### 3.6 Winding / unwinding (centre-driven roll)

Web tension depends on the material and process. **It is a `USER` input and is never derived from hardness or density.**

| Input | Unit | Origin |
|---|---|---|
| web tension F_t | N | USER |
| line speed v | m/s | USER |
| core diameter D_core, full roll diameter D_max, roll width W | m | USER |
| material density ρ (for roll mass) | kg/m³ | USER / LIBRARY |
| core inertia J_core | kg·m² | USER |
| t_acc | s | USER |

```
m_roll   = ρ · π/4 · (D_max² − D_core²) · W
J_roll   = ½ · m_roll · ((D_max/2)² + (D_core/2)²) + J_core
P_web    = F_t · v                                   (constant across diameter)
At full roll:  T_run,max = F_t · D_max / 2 ;  n_min = 60·v/(π·D_max)
At core:       T_run,min = F_t · D_core / 2 ;  n_max = 60·v/(π·D_core)
T_acc,max = T_run,max + J_roll · (2·a / D_max)
```

**Important:** winding produces **two operating points**, not one: high torque at low speed and low torque at high speed. The selection engine must verify **both** (see §5.2). A single-point check is not valid here.

### 3.7 Not in v1 (needs its own definition before support)

Bulk-material conveyors (CEMA), screw conveyors, mixers/agitators, pumps/fans (affinity laws), crushers, extruders, presses/punching (needs shear strength, not hardness), vehicles/traction. The parser maps these to `APPLICATION_NOT_SUPPORTED`.

---

## 4. Duty cycle and service factor

### 4.1 Duty cycle → thermal (RMS) torque

When the user gives a motion profile (accelerate / run / decelerate / dwell times):

```
T_rms = sqrt( Σ (T_i² · t_i) / Σ t_i )
```

`T_rms` is checked against **continuous** ratings. `T_acc` (the peak) is checked against **peak** ratings. For continuous running with no profile, T_rms = T_run.

Deceleration torque defaults to **not** reducing the requirement. Taking credit for it means entering t_dec and T_dec explicitly.

### 4.2 Service factor

SF is **looked up, not computed**. Proposed table: AGMA-style, electric-motor prime mover. **The values below must be confirmed by the engineering owner and versioned (`sf_table_version`) before release.**

| Load class \ Hours/day | < 3 h | 3–10 h | > 10 h |
|---|---|---|---|
| Uniform | 0.80 | 1.00 | 1.25 |
| Moderate shock | 1.00 | 1.25 | 1.50 |
| Heavy shock | 1.50 | 1.75 | 2.00 |

- The user selects the load class and hours. The AI may *suggest* a class from the text, but the user must confirm it.
- **Start/stop frequency:** if starts/hour exceed a threshold (owner to define), raise a warning. No automatic SF change in v1.
- The user may override the SF. The trace then shows both "table SF" and "user override SF".

---

## 5. Output: `SizedRequirement` → selection engine

```
n_out_req           = n_out                       (or the range [n_min, n_max] for winding)
T_cont_design       = T_rms · SF
T_peak_design       = T_acc · SF
P_req               = T_cont_design · ω_out
V_supply_max        = USER constraint (unchanged from today)
operating_points[]  = list of (n, T_cont, T_peak), one entry or more
```

### 5.1 Changes needed in the existing evaluator

Today, `app/engine/recommend.py` checks one torque value against `motor.nominal_torque_nm × ratio × η`. The new checks per operating point are:

| Check | Uses | Missing data → |
|---|---|---|
| Continuous torque: `T_motor,nom · i · η ≥ T_cont_design` | nominal torque, ratio, η | DATA_INCOMPLETE |
| Peak torque: `T_motor,max · i · η ≥ T_peak_design` | motor max/peak torque | MEETS only if the continuous output already covers the peak (this proves it); otherwise DATA_INCOMPLETE. Never assumed. |
| Gearbox rating: `T_gb,max_out ≥ T_peak_design` | gearbox rated output torque | DATA_INCOMPLETE |
| Speed: `n_motor / i` within the speed tolerance band | nominal speed, ratio | DATA_INCOMPLETE |
| Gearbox input speed: `n_motor ≤ n_gb,max_in` | gearbox max input | DATA_INCOMPLETE |
| Voltage: `V_motor ≤ V_supply_max` | motor voltage | DATA_INCOMPLETE |

**Status rule** (same for Source A and Source B):
- any check has verified data that fails → `DOES_NOT_MEET`
- otherwise, any check lacks verified data → `DATA_INCOMPLETE`
- otherwise → `MEETS`

### 5.2 Multi-point (winding)
A candidate is `MEETS` only if **every** operating point passes. The trace shows each point separately.

### 5.3 Speed tolerance
The current code hard-codes the window at `n_req ≤ n_out ≤ 1.5·n_req`. This becomes a user setting, `speed_tolerance` (for example −0 % / +10 %), shown in the trace. Under-speed is only allowed if the user explicitly permits it.

---

## 6. Fit / compatibility indicator

This is a **secondary comparison aid**. It never replaces the status and is never labelled "safety %", "confidence %" or "probability".

- It is computed **only for `MEETS` candidates**.
- For `DOES_NOT_MEET`, show the failing check and the shortfall %. For `DATA_INCOMPLETE`, show "x of y checks verified". **No fit % is shown for either.**

Proposed formula (weights and breakpoints to be signed off):

```
torque_score = 1.0                         if 1.0 ≤ m_T ≤ 1.5        m_T = T_available_cont / T_cont_design
             = 1.0 − 0.5·(m_T − 1.5)/1.5   if 1.5 < m_T ≤ 3.0        (penalises oversizing)
             = 0.25                        if m_T > 3.0
speed_score  = max(0, 1 − |n_out − n_req| / (tol · n_req))
power_score  = same shape as torque_score, applied to P_motor_cont / P_req
Fit %        = round(100 · (0.4·torque_score + 0.4·speed_score + 0.2·power_score))
```

Label in the UI: **"Fit to requirement: 92 % (comparison only — status: MEETS)"**.

---

## 7. Worked example (conveyor, §3.1): this becomes a unit test

Inputs (all `USER`): block 200×100×50 mm, ρ = 1200 kg/m³, 20 parts on the belt, belt moving mass 6 kg, incline 10°, μ = 0.30 (slider bed), v = 0.5 m/s, t_acc = 0.5 s, D = 100 mm, η_drive = 1.0, F_extra = 0, moderate shock, 3–10 h/day.

| Step | Equation | Result |
|---|---|---|
| Volume | 0.2·0.1·0.05 | 0.001 m³ |
| Part mass | 1200·0.001 | 1.20 kg |
| Moving mass | 20·1.2 + 6 | 30.0 kg |
| F_grav | 30·9.80665·sin10° | 51.09 N |
| F_fric | 0.30·30·9.80665·cos10° | 86.92 N |
| F_run | 51.09 + 86.92 | 138.01 N |
| a, F_acc | 0.5/0.5 = 1.0 m/s²; 30·1.0 | 30.00 N |
| T_run | 138.01·0.05 | **6.90 N·m** |
| T_acc | 168.01·0.05 | **8.40 N·m** |
| n_out | 60·0.5/(π·0.1) | **95.49 rpm** |
| P_run / P_peak | T·(v/r = 10 rad/s) | 69.0 W / 84.0 W |
| SF | Moderate, 3–10 h | 1.25 |
| T_cont_design | 6.90·1.25 (continuous, T_rms = T_run) | **8.63 N·m** |
| T_peak_design | 8.40·1.25 | **10.50 N·m** |

Hardness was entered (for example Shore A 90) and is **shown but not used**, as §2.2 requires.

Each application in §3 needs one hand-checked example like this in `tests/test_sizing.py` before it is enabled.

---

## 8. AI parser changes (Stage 7 extension)

`ParsedRequirements` gains nested optional blocks: `material`, `part_geometry`, `application_type` (an enum of §3 models plus `NOT_SUPPORTED`), `motion`, `load`, `duty`. Rules:

- Extract **only values stated in the text**, each with the source span.
- Never fill ρ, μ, η, tension or SF from model knowledge. If one is absent, add it to `missing_fields` and generate a clarification question.
- `missing_fields` is now computed **per application model**, from the required-input tables above.
- Every extracted value arrives as `AI_EXTRACTED` and becomes `USER` only after the user confirms it in the form.

---

## 9. Implementation plan (after sign-off)

| Step | Work | Files |
|---|---|---|
| 8.1 | Origin tags on traces; trace-chain container | `app/engine/trace.py` |
| 8.2 | Mass/geometry module + tests | `app/engine/sizing/geometry.py` |
| 8.3 | Application models §3.1–3.6, one per file, each with its §7-style test | `app/engine/sizing/*.py`, `tests/test_sizing.py` |
| 8.4 | Duty/RMS + versioned SF table | `app/engine/sizing/duty.py` |
| 8.5 | `SizedRequirement` + `POST /api/size` (returns the trace chain only) | `app/api/routes.py` |
| 8.6 | Evaluator: continuous + peak + multi-point + unified status rule, shared by Source A and Source B | `app/engine/recommend.py`, `app/engine/discover.py` |
| 8.7 | Fit indicator (MEETS only) | `app/engine/fit.py` |
| 8.8 | Material library table with citations (empty until rows are sourced) | `app/database/models.py` |
| 8.9 | Parser schema extension | `app/ai/*` |
| 8.10 | UI: "Application sizing" wizard as the primary tab; the current torque/RPM form stays as "Advanced / manual" | `templates/`, `static/js/` |

---

## 10. Existing inconsistencies to resolve as part of this stage

1. **Status naming:** `discover.py` emits `DATA_MISSING`, while the handoff and this spec use `DATA_INCOMPLETE`. Pick one engineering status name. `DATA_INCOMPLETE` is also already used as a *data_status*, so consider calling the engineering status `DATA_INCOMPLETE` and keeping the data provenance status separate.
2. **Source A filters out failures:** `recommend.py` drops non-matching pairs instead of returning `DOES_NOT_MEET`. That's fine for ranking, but Source A and Source B currently follow different status semantics.
3. **Power pre-filter** in `recommend.py` compares motor power to output power with no gearbox efficiency. Use `P_req / η_gb`.
4. **Peak torque** is never checked today, and `max_torque_nm` is unused.
5. `PROJECT_STATUS.md` is stale: it still lists Stage 7 as CAD/3D.

---

## 11. Decisions needed from the engineering owner

1. Confirm the v1 application set (§3.1–3.6), or trim/add.
2. Confirm or replace the SF table values (§4.2) and the starts/hour threshold.
3. Confirm the fit-% weights and breakpoints (§6).
4. Confirm that hardness is recorded but not used in v1 (§2.2).
5. Confirm the default speed tolerance (§5.3).
6. Name the person or process that approves material-library rows (§2.5).
