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

## 6. Not yet supported

Bulk-material conveyors (CEMA), screw conveyors, mixers, pumps and fans, crushers, extruders, presses/punching, and vehicles. Each needs its own approved equations before it is added.
