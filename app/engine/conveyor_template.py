"""
Built-in project template: bulk-material belt conveyor drive pulley.

Method: ISO 5048 (DIN 22101) peripheral force with length coefficient C,
Euler–Eytelwein belt tensions, combined bending + torsion shaft check,
then the checked motor + gearbox selection and ISO 281 bearing modules.
Not yet approved by an engineer — see docs/ENGINEERING_DEFAULTS_TO_REVIEW.md.
"""
from app.engine.method_eval import PlanStep
from app.engine.project import ProjectPlan, ProjectCalc, Link, _i


def _s(sym, name, unit, expr, note=None):
    return PlanStep(symbol=sym, name=name, unit=unit, expression=expr, note=note)


def bulk_conveyor_template(machine: str = "Belt conveyor (bulk material)") -> ProjectPlan:
    return ProjectPlan(
        title="Bulk belt conveyor drive pulley — calculation plan",
        machine=machine,
        origin="TEMPLATE",
        summary=("Belt conveyor for bulk material, calculated with the ISO 5048 (DIN 22101) peripheral-force method: "
                 "load per metre → peripheral force → drive power and pulley torque → belt tensions → total belt "
                 "tension on the pulley → shaft bending, allowable stress and shaft size → motor + gearbox and bearings."),
        inputs=[
            _i("Q", "Conveying capacity", "t/h", "Your production requirement"),
            _i("v", "Belt speed", "m/s", "Your design"),
            _i("L", "Conveyor length (centre-to-centre)", "m", "Your layout"),
            _i("H", "Lift height (0 if horizontal, positive if conveying upward)", "m", "Your layout"),
            _i("D", "Drive pulley diameter", "mm", "Your design / pulley catalogue"),
            _i("B", "Belt width (for belt selection; not used in the power formula)", "mm", "Your design", optional=True),
            _i("m_B", "Belt mass per metre", "kg/m", "Belt manufacturer's datasheet"),
            _i("m_R", "Rotating idler mass per metre of conveyor (carry + return)", "kg/m",
               "Idler catalogue: rotating mass of each idler set divided by idler spacing, carrying + return side"),
            _i("f", "Artificial friction coefficient", "", "ISO 5048 / DIN 22101", typical=0.02,
               note="ISO 5048: 0.02 for normal conditions; 0.023–0.03 for poor alignment, low temperature or heavy loading."),
            _i("C", "Length coefficient (secondary resistances)", "", "ISO 5048 table of C against conveyor length", typical=1.6,
               note="ISO 5048 table: about 1.78 at 100 m, about 1.6 at 150 m, about 1.45 at 200 m — confirm from the standard."),
            _i("F_S2", "Special resistances (skirt boards, belt cleaners, ploughs) — enter 0 if none", "N",
               "Your design / component suppliers"),
            _i("mu", "Friction between belt and drive pulley", "", "Pulley lagging / DIN 22101 guidance", typical=0.25,
               note="About 0.35 for dry rubber lagging, 0.25 wet or bare steel; the lower value is used to be safe."),
            _i("theta", "Belt wrap angle on the drive pulley", "deg",
               "Your layout (180° for a plain head drive, more with a snub pulley)"),
            _i("eta", "Drive efficiency (gearbox + couplings)", "", "Gearbox catalogue", typical=0.9,
               note="A helical-bevel gearbox with couplings is typically 0.90–0.95; the lower value is used to be safe."),
            _i("a", "Distance from bearing centre to pulley hub (each side)", "mm", "Your pulley / shaft drawing"),
            _i("Sy", "Shaft material yield strength", "MPa", "Shaft material standard or mill certificate"),
            _i("n_s", "Safety factor on yield for the shaft", "", "Your company design standard", typical=2.5,
               note="Static design factor, commonly 2–3 for conveyor pulley shafts — check your design standard."),
            _i("SF", "Service factor for the drive", "", "Service-factor table", typical=1.25,
               note="Belt conveyors with even feed are usually 'uniform' to 'moderate': 1.0–1.5 depending on running hours."),
            _i("life_req", "Required bearing life", "h", "Your target service life (running hours)", optional=True),
            _i("C_b", "Bearing dynamic load rating (if a bearing is already chosen)", "kN", "Bearing catalogue", optional=True),
            _i("V", "Supply voltage (maximum)", "V", "Your power supply"),
        ],
        calculations=[
            ProjectCalc(id="load", title="Material load per metre of belt", purpose="Mass of material on each metre of belt.",
                        steps=[_s("m_G", "Material load per metre", "kg/m", "Q / (3.6 * v)",
                                  "Capacity in t/h ÷ 3.6 = kg/s, then ÷ belt speed.")]),
            ProjectCalc(id="force", title="Peripheral force at the drive pulley", standard="ISO 5048 / DIN 22101",
                        purpose="Total force the drive pulley must apply to the belt.",
                        steps=[_s("F_H", "Main + secondary resistances", "N",
                                  "C * f * L * g * (m_R + (2 * m_B + m_G) * sqrt(1 - (H / L) ** 2))",
                                  "F_H = C·f·L·g·[m_R + (2·m_B + m_G)·cos δ]"),
                               _s("F_St", "Lift resistance", "N", "H * g * m_G"),
                               _s("F_U", "Peripheral force (total)", "N", "F_H + F_St + F_S2")]),
            ProjectCalc(id="power", title="Required drive power", purpose="Power at the pulley and at the motor.",
                        steps=[_s("P_A", "Power at the drive pulley", "kW", "F_U * v / 1000"),
                               _s("P_M", "Required motor power", "kW", "P_A / eta")]),
            ProjectCalc(id="torque", title="Pulley shaft torque and speed", purpose="Torque and speed the gearbox must deliver.",
                        steps=[_s("T", "Pulley shaft torque", "N·m", "F_U * D / 2 / 1000"),
                               _s("n", "Pulley speed", "rpm", "60 * v / (pi * D / 1000)")]),
            ProjectCalc(id="tension", title="Belt tensions", standard="Euler–Eytelwein (capstan) equation",
                        purpose="Tight- and slack-side belt tension and the total belt tension acting on the pulley.",
                        steps=[_s("e_mt", "Capstan factor e^(μθ)", "", "exp(mu * radians(theta))"),
                               _s("T2", "Slack-side tension (minimum for no slip)", "N", "F_U / (e_mt - 1)"),
                               _s("T1", "Tight-side tension", "N", "F_U + T2"),
                               _s("R", "Total equivalent belt tension on the pulley (resultant)", "N",
                                  "sqrt(T1 ** 2 + T2 ** 2 - 2 * T1 * T2 * cos(radians(theta)))",
                                  "Vector sum of T1 and T2 for the wrap angle (= T1 + T2 at 180°). Pulley self-weight not included.")]),
            ProjectCalc(id="motor", title="Motor + gearbox selection", kind="motor_selection",
                        purpose="Find motor + gearbox combinations that deliver the pulley torque at the pulley speed.",
                        links=[Link(param="required_speed_rpm", symbol="n"), Link(param="required_torque_nm", symbol="T"),
                               Link(param="service_factor", symbol="SF"), Link(param="max_voltage_v", symbol="V")]),
            ProjectCalc(id="allowable", title="Allowable bending stress of the shaft material",
                        purpose="Highest bending stress the shaft material may carry with the chosen safety factor.",
                        steps=[_s("sigma_allow", "Allowable bending stress of the shaft material", "MPa", "Sy / n_s",
                                  "Yield strength ÷ safety factor.")]),
            ProjectCalc(id="shaft", title="Shaft bending moment and shaft size",
                        standard="Combined bending + torsion, von Mises (static)",
                        purpose="Bending moment from the belt tensions and the shaft size that keeps stress below the allowable value.",
                        steps=[_s("M", "Shaft bending moment", "N·m", "R / 2 * a / 1000",
                                  "Belt load shared equally by the two hubs; each hub load acts at distance a from its bearing."),
                               _s("d_min", "Minimum shaft diameter at the hub", "mm",
                                  "(32 * 1000 / (pi * sigma_allow) * sqrt(M ** 2 + 0.75 * T ** 2)) ** (1 / 3)",
                                  "σ_eq = 32/(πd³)·√(M² + ¾T²) ≤ σ_allow")]),
            ProjectCalc(id="bearing_load", title="Bearing load", purpose="Radial load on each pulley bearing.",
                        steps=[_s("Fr_b", "Radial load per bearing", "N", "R / 2")]),
            ProjectCalc(id="bearing_life", title="Bearing life (ISO 281)", kind="bearing_life", bearing_type="roller",
                        standard="ISO 281", purpose="Check the bearing life, or find the minimum bearing rating needed.",
                        note="Spherical roller bearings are usual for conveyor pulleys, so roller-bearing life is used.",
                        links=[Link(param="radial_load_n", symbol="Fr_b"), Link(param="speed_rpm", symbol="n"),
                               Link(param="required_life_h", symbol="life_req"), Link(param="dynamic_rating_kn", symbol="C_b")]),
        ],
        limitations=[
            "ISO 5048 simplified method with coefficient C — for long, inclined or multi-drive conveyors use the full "
            "DIN 22101 / CEMA calculation.",
            "Minimum belt tension for sag limits, start-up / braking tensions and take-up design are not included.",
            "Belt width and bulk density are not used: the belt capacity / cross-section check is not included.",
            "Shaft check is static only — fatigue, stress concentration at hub/shoulder and deflection are not included.",
            "Built-in template, not yet approved by an engineer.",
        ],
    )
