# Engineering Defaults — For Review by an Engineer

**Who this is for:** the mechanical engineer who approves this tool.
**Why it exists:** the project owner isn't technical, so the decisions below were made using standard, conservative choices and **have not yet been approved by an engineer.** Please confirm or change each one. Every value lives in one file, [`app/engine/sizing/defaults.py`](../app/engine/sizing/defaults.py), so changing one is a small edit. After any change, bump `DEFAULTS_VERSION`. Each calculation report prints the version it used.

Current version: `2026-10-14-draft-1`

---

## 1. Service factor table

The user picks how smooth the work is and how many hours a day it runs. The tool then looks up the service factor. This is an AGMA-style table for an electric-motor prime mover.

| Load | < 3 h/day | 3–10 h/day | > 10 h/day |
|---|---|---|---|
| Smooth / uniform | 0.80 | 1.00 | 1.25 |
| Moderate shocks | 1.00 | 1.25 | 1.50 |
| Heavy shocks | 1.50 | 1.75 | 2.00 |

The user can override the value. When they do, the report shows both the table value and the override.
**To confirm:** the values, and whether values below 1.0 should be allowed at all.

## 2. Allowed extra speed: default +50 %

A candidate passes the speed check if its output speed is between 100 % and 150 % of the required speed. This is the same window the tool has always used. The user can change it on the form.
**To confirm:** 50 % is generous. Many applications would want +10–20 %.

## 3. Fit % (comparison only)

This is shown only for candidates whose status is MEETS. It is labelled as a comparison aid, not a safety or confidence figure.
- Torque and power: 100 % if the margin is 1.0–1.5×, falling linearly to 50 % at 3×, and 25 % beyond that.
- Speed: 100 % at an exact match, falling to 0 % at the edge of the allowed tolerance.
- Weights: torque 40 %, speed 40 %, power 20 %. If power data is missing, the weights are re-scaled.

**To confirm:** the breakpoints and weights.

## 4. Optional inputs left blank

The tool never guesses a value that sizing depends on. A few inputs, though, are optional because they are often zero. When the user leaves one blank, the tool uses the value below **and prints it under "Defaults used — please check these"** in the report.

| Input | Default when blank | Note |
|---|---|---|
| Carrier / pallet / fixture mass | 0 kg | |
| Conveyor belt moving mass | 0 kg | |
| Extra resisting force / process force | 0 N | |
| Extra drive stage efficiency (chain or belt after the gearbox) | 1.0 | Assumes direct drive |
| Hoist rope falls | 1 | |
| Hoist rope / sheave efficiency | 1.0 | Not conservative if there are pulleys |
| Hoist hook mass, counterweight | 0 kg | |
| Turntable own inertia | 0 | **Not conservative.** Users are told to enter it from CAD |
| Turntable bearing friction | 0 N·m | |
| Screw inertia, winding core inertia | 0 | |
| Dwell time | 0 s | |

These inputs are **always required** and are never defaulted: density (unless mass is entered), part dimensions, speed, acceleration time, pulley/drum/pinion diameter, friction coefficient, screw lead, **screw efficiency**, web tension, roll diameters, load class, hours per day, and maximum voltage.
**To confirm:** whether any of the defaults above should become required, especially turntable inertia and rope efficiency.

## 5. Modelling choices (conservative)

- **Hardness (Shore A/D)** is recorded and shown, but not used in any equation. No reliable equation links hardness to force or friction. If hardness affects grip, the user enters a friction coefficient instead.
- **Conveyor friction** uses the full moving mass. This overestimates slightly, because the belt's return side carries less.
- **Duty cycle:** deceleration is counted at full peak torque, and during dwell on inclined or vertical axes the motor is assumed to hold the load with no brake.
- **Zero running torque** (for example a frictionless turntable): the continuous requirement is set equal to the peak torque.
- **Winding:** the motor is checked for full-roll torque all the way up to core speed (constant-torque assumption). This overstates the power needed. A constant-power drive could be much smaller. The report warns about this.
- **Peak torque check:**
  - If the motor's peak torque is not recorded but its continuous output already covers the peak, the candidate passes.
  - If neither proves it, the candidate is DATA_INCOMPLETE. It is never assumed to pass.
- **Hoist:** the report says it is a sizing estimate, not a certified hoist design (FEM/ISO classes are out of scope), and that a brake is required.

## 6. Suggested values for missing inputs

The engineer who reviewed the tool asked for this. When the user leaves an input out, the simple view now fills it in from the list below. Each one is shown in purple, marked **"Suggested"** with the reason, and listed again in the result under "Typical values we used". The user can change any of them before calculating.

Where a range exists, the end that gives the **larger** motor requirement is used. The values live in [`app/engine/sizing/suggestions.py`](../app/engine/sizing/suggestions.py).

| Input | Suggested | Basis (typical published range) |
|---|---|---|
| Conveyor friction coefficient | 0.5 | Belt sliding on a steel bed: 0.3–0.5. Roller conveyors: about 0.03–0.05, which the user must enter |
| Linear guide friction | 0.01 | Rolling guides: 0.002–0.01. Plain sliding guides: about 0.1–0.2, which the user must enter |
| Screw efficiency (ball screw named) | 0.9 | Ball screws: 0.9–0.95 |
| Screw efficiency (otherwise) | 0.2 | Lead (trapezoidal) screws: 0.2–0.5 |
| Time to reach full speed | 1.0 s | Design choice. It only affects the peak torque. **Not conservative for machines that must start faster** |
| How smooth is the work | Moderate shocks | Middle class |
| Running hours per day | 8 h | One shift. **Not conservative for multi-shift use** |
| Supply voltage | 24 V | Common industrial DC |

These are **never** suggested, because they belong to the user's own machine: dimensions, mass, density, speeds, pulley/drum/pinion/screw sizes, web tension, incline/axis angle, and inertia.
**To confirm:** each value, especially the two rows marked "not conservative".

## 7. Bearing life (ISO 281)

Bearing questions typed into the main box (for example "ball bearing, radial load 2000 N at 1500 rpm…") run a checked module that calculates ISO 281 *basic* rating life: P = X·Fr + Y·Fa, L10 = (C/P)^p with p = 3 for ball and 10/3 for roller bearings, L10h = L10·10⁶/(60·n). C, X and Y must come from the bearing catalogue and are never assumed. The modified-life factor a_ISO (lubrication and contamination) is **not** included, and the results page says so.

Reliability factor a1 used:

| Reliability | 90 % | 95 % | 96 % | 97 % | 98 % | 99 % |
|---|---|---|---|---|---|---|
| a1 | 1.00 | 0.64 | 0.55 | 0.47 | 0.37 | 0.25 |

**To confirm:** the a1 values against ISO 281:2007.

## 8. How machine types are recognised

The tool classifies a machine by **what the motor has to move**, not by its name. Any machine whose driven motion is one of the six supported types is calculated with that type's equations, and the result explains the choice (for example, "'belt feeder' moves a load along a belt…, so it is calculated as a conveyor").
- With an AI key set (`AI_PROVIDER=gemini` or `openai`), any wording is understood.
- Without a key, a built-in list of common names is used.

Machines whose physics is not covered (pumps, fans, compressors, mixers, crushers, presses, vehicles) are reported as **not supported yet**, and the user is pointed to the Advanced torque/RPM tab. Bearings are pointed to the Bearing Life tab. The tool never forces one of these into a supported type.

## 9. Questions with no checked module ("Method chosen by AI")

The main box accepts any engineering question. It first decides which kind of calculation is being asked for:

| Kind | How it is calculated |
|---|---|
| Motor + gearbox sizing | Checked module (sections 1–6) |
| Bearing life | Checked module (section 7) |
| Anything else (shafts, bolts, belts, springs, pumps…) | **The AI chooses the method and formulas. The tool does every calculation itself** |

For the third kind:
- The AI returns the standard it follows, the inputs needed (with units) and the formulas. **It is not allowed to produce result numbers.**
- The tool evaluates each formula itself, from the engineer's values, and shows every substitution ([`app/engine/method_eval.py`](../app/engine/method_eval.py)). Formulas may only contain plain arithmetic and standard maths functions; anything else is rejected before use.
- A value counts as "given" only if the engineer's own words for it appear in the question. The AI may suggest a typical value for material or catalogue properties. That suggestion is shown in purple with its source, and never for the user's own dimensions, loads or speeds.
- Every result is labelled **"AI METHOD — CHECK"**. The method and units must be checked by an engineer, because the tool cannot verify that the AI picked the right formula.
- **This needs the AI switched on** (`AI_PROVIDER` + key). Without it, the tool says so and points to the Advanced tab.

**Recommendation:** when a topic is used often, turn it into a checked module with its own hand-checked test, as was done for bearing life.

## 10. Not yet supported

Bulk-material conveyors (CEMA), screw conveyors, mixers, pumps and fans, crushers, extruders, presses/punching, and vehicles. Each needs its own approved equations before it is added.
