from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database.models import Motor, Gearbox
from app.engine.torque import calculate_design_torque, calculate_gearbox_output_torque
from app.engine.power import calculate_mechanical_power
from app.engine.fit import compute_fit
from app.engine.sizing.defaults import DEFAULT_SPEED_TOLERANCE_PCT

def get_recommendations(
    db: Session,
    required_speed_rpm: float,
    required_torque_nm: float,
    service_factor: float,
    max_voltage_v: float,
    top_n: int = 5,
    peak_torque_nm: Optional[float] = None,
    speed_tolerance_pct: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic engineering recommendation algorithm.
    Pairs motors and gearboxes based on pure engineering math.
    CalculationTrace is a Pydantic model, so we access fields with .result not ["result"].

    peak_torque_nm (optional, before service factor) adds the Stage 8 peak checks:
      * gearbox rated output torque >= design peak torque
      * motor peak torque × ratio × efficiency >= design peak torque. When the motor's
        peak torque is not recorded, the pair still MEETS if its continuous output
        already covers the peak; otherwise it is DATA_INCOMPLETE (never assumed).
    """
    tol_pct = DEFAULT_SPEED_TOLERANCE_PCT if speed_tolerance_pct is None else speed_tolerance_pct

    # 1. Fetch valid components from database
    motors = db.query(Motor).filter(Motor.voltage_v <= max_voltage_v).all()
    gearboxes = db.query(Gearbox).all()

    # 2. Compute minimum design requirements using .result (Pydantic attribute access)
    design_torque = calculate_design_torque(required_torque_nm, service_factor).result
    req_power_w = calculate_mechanical_power(design_torque, required_speed_rpm).result
    design_peak = peak_torque_nm * service_factor if peak_torque_nm is not None else None

    valid_pairings = []

    # 3. Evaluate all pairings
    for motor in motors:
        # Pre-filter: Motor must have enough raw continuous power to meet mechanical requirement
        if motor.continuous_power_w < req_power_w:
            continue

        for gearbox in gearboxes:
            # Check maximum input speed rating on the gearbox
            if gearbox.max_input_speed_rpm and motor.nominal_speed_rpm > gearbox.max_input_speed_rpm:
                continue

            # Power delivered through the gearbox must cover the requirement (gearbox losses included)
            if motor.continuous_power_w * gearbox.efficiency < req_power_w:
                continue

            # Calculate final physical output speed
            output_speed_rpm = motor.nominal_speed_rpm / gearbox.gear_ratio

            # Speed match criteria: must meet the requirement, within the allowed over-speed tolerance
            if output_speed_rpm < required_speed_rpm or output_speed_rpm > required_speed_rpm * (1 + tol_pct / 100):
                continue

            # Calculate final physical output torque using .result (Pydantic attribute access)
            calc_output_torque = calculate_gearbox_output_torque(
                motor.nominal_torque_nm,
                gearbox.gear_ratio,
                gearbox.efficiency
            ).result

            # Torque match criteria: Must meet design torque
            if calc_output_torque < design_torque:
                continue

            # Check gearbox structural limit
            if calc_output_torque > gearbox.max_output_torque_nm:
                continue

            # Stage 8: peak torque checks (only when a peak requirement is supplied)
            engineering_status = "MEETS"
            peak_trace = None
            if design_peak is not None:
                if gearbox.max_output_torque_nm < design_peak:
                    continue  # verified gearbox rating is below the peak -> DOES_NOT_MEET
                if motor.max_torque_nm is not None:
                    avail_peak = motor.max_torque_nm * gearbox.gear_ratio * gearbox.efficiency
                    if avail_peak < design_peak:
                        continue  # verified motor peak is below the peak -> DOES_NOT_MEET
                    peak_status, basis = "MEETS", f"{motor.max_torque_nm} Nm (motor peak) × {gearbox.gear_ratio} × {gearbox.efficiency}"
                elif calc_output_torque >= design_peak:
                    avail_peak = calc_output_torque
                    peak_status, basis = "MEETS", "continuous output torque already covers the peak (motor peak not recorded)"
                else:
                    avail_peak = None
                    peak_status, basis = "DATA_INCOMPLETE", "motor peak torque not recorded — cannot verify"
                    engineering_status = "DATA_INCOMPLETE"
                peak_trace = {
                    "formula": "T_peak_available = T_motor_peak × Ratio × Efficiency ≥ T_peak × SF",
                    "substitution": basis,
                    "result": round(avail_peak, 4) if avail_peak is not None else None,
                    "unit": "Nm",
                    "comparison": (f"{round(avail_peak, 4)} Nm >= {round(design_peak, 4)} Nm (Design Peak Torque); "
                                   f"gearbox rating {gearbox.max_output_torque_nm} Nm >= {round(design_peak, 4)} Nm")
                                  if avail_peak is not None else
                                  f"Design Peak Torque {round(design_peak, 4)} Nm — not verifiable from recorded data",
                    "status": peak_status,
                }

            # Score by how close to the exact requirement (less over-engineering = better)
            torque_margin = calc_output_torque / design_torque
            speed_margin = output_speed_rpm / required_speed_rpm
            efficiency_score = torque_margin * speed_margin

            # Generate candidate-specific calculation trace
            dt_trace = calculate_design_torque(required_torque_nm, service_factor)
            mp_trace = calculate_mechanical_power(dt_trace.result, required_speed_rpm)
            ot_trace = calculate_gearbox_output_torque(motor.nominal_torque_nm, gearbox.gear_ratio, gearbox.efficiency)

            calculation_trace = {
                "design_torque": {
                    "formula": dt_trace.formula,
                    "substitution": dt_trace.substitution,
                    "result": dt_trace.result,
                    "unit": dt_trace.unit,
                    "comparison": f"Required Torque ({round(required_torque_nm, 4)} Nm) × Service Factor ({service_factor}) = {round(dt_trace.result, 4)} Nm"
                },
                "required_power": {
                    "formula": mp_trace.formula,
                    "substitution": f"P = {round(dt_trace.result, 4)} * {round(required_speed_rpm, 2)} / 9.5493",
                    "result": mp_trace.result,
                    "unit": mp_trace.unit,
                    "comparison": f"Required Power = {mp_trace.result:.2f} W"
                },
                "gearbox_output_torque": {
                    "formula": ot_trace.formula,
                    "substitution": f"{motor.nominal_torque_nm} Nm × {gearbox.gear_ratio} × {gearbox.efficiency}",
                    "result": round(ot_trace.result, 4),
                    "unit": ot_trace.unit,
                    "comparison": f"{round(ot_trace.result, 4)} Nm >= {round(dt_trace.result, 4)} Nm (Design Torque)",
                    "status": "MEETS" if ot_trace.result >= dt_trace.result else "DOES_NOT_MEET"
                },
                "output_speed": {
                    "formula": "Output Speed = Motor Speed / Gear Ratio",
                    "substitution": f"{motor.nominal_speed_rpm} RPM / {gearbox.gear_ratio}",
                    "result": round(output_speed_rpm, 2),
                    "unit": "RPM",
                    "comparison": f"{round(output_speed_rpm, 2)} RPM >= {round(required_speed_rpm, 2)} RPM (Required Speed)",
                    "status": "MEETS" if output_speed_rpm >= required_speed_rpm else "DOES_NOT_MEET"
                }
            }
            if peak_trace:
                calculation_trace["peak_torque"] = peak_trace

            fit = None
            if engineering_status == "MEETS":
                fit = compute_fit(
                    calc_output_torque, design_torque, output_speed_rpm, required_speed_rpm, tol_pct,
                    motor.continuous_power_w * gearbox.efficiency, req_power_w,
                )

            valid_pairings.append({
                "motor": {
                    "id": motor.id,
                    "part_number": motor.part_number,
                    "manufacturer": motor.manufacturer.name,
                    "voltage_v": motor.voltage_v,
                    "power_w": motor.continuous_power_w,
                    "nominal_speed_rpm": motor.nominal_speed_rpm,
                    "nominal_torque_nm": motor.nominal_torque_nm,
                    "max_torque_nm": motor.max_torque_nm,
                    "source": motor.source,
                    "source_url": motor.source_url,
                    "data_status": motor.data_status,
                    "verification_date": motor.verification_date
                },
                "gearbox": {
                    "id": gearbox.id,
                    "part_number": gearbox.part_number,
                    "manufacturer": gearbox.manufacturer.name,
                    "ratio": gearbox.gear_ratio,
                    "efficiency": gearbox.efficiency,
                    "max_input_speed_rpm": gearbox.max_input_speed_rpm,
                    "max_torque_nm": gearbox.max_output_torque_nm,
                    "source": gearbox.source,
                    "source_url": gearbox.source_url,
                    "data_status": gearbox.data_status,
                    "verification_date": gearbox.verification_date
                },
                "performance": {
                    "output_speed_rpm": round(output_speed_rpm, 2),
                    "output_torque_nm": round(calc_output_torque, 4),
                    "torque_margin_factor": round(torque_margin, 2),
                    "torque_status": "MEETS",
                    "speed_status": "MEETS"
                },
                "calculation_trace": calculation_trace,
                "engineering_status": engineering_status,
                "fit": fit,
                "score": efficiency_score
            })

    # 4. Rank: MEETS before DATA_INCOMPLETE, then highest fit %, then closest match to the exact requirement
    valid_pairings.sort(key=lambda x: (
        x["engineering_status"] != "MEETS",
        -(x["fit"]["percent"] if x["fit"] else 0),
        x["score"],
    ))

    return valid_pairings[:top_n]

