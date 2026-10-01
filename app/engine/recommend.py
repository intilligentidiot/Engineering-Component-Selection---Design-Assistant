from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.database.models import Motor, Gearbox
from app.engine.torque import calculate_design_torque, calculate_gearbox_output_torque
from app.engine.power import calculate_mechanical_power

def get_recommendations(
    db: Session,
    required_speed_rpm: float,
    required_torque_nm: float,
    service_factor: float,
    max_voltage_v: float,
    top_n: int = 5
) -> List[Dict[str, Any]]:
    """
    Deterministic engineering recommendation algorithm.
    Pairs motors and gearboxes based on pure engineering math.
    CalculationTrace is a Pydantic model, so we access fields with .result not ["result"].
    """

    # 1. Fetch valid components from database
    motors = db.query(Motor).filter(Motor.voltage_v <= max_voltage_v).all()
    gearboxes = db.query(Gearbox).all()

    # 2. Compute minimum design requirements using .result (Pydantic attribute access)
    design_torque = calculate_design_torque(required_torque_nm, service_factor).result
    req_power_w = calculate_mechanical_power(design_torque, required_speed_rpm).result

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

            # Calculate final physical output speed
            output_speed_rpm = motor.nominal_speed_rpm / gearbox.gear_ratio

            # Speed match criteria: Must meet the requirement, but not be wildly over-speed (> 1.5x)
            if output_speed_rpm < required_speed_rpm or output_speed_rpm > (required_speed_rpm * 1.5):
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
                    "comparison": f"Required Torque ({required_torque_nm} Nm) × Service Factor ({service_factor}) = {dt_trace.result} Nm"
                },
                "required_power": {
                    "formula": mp_trace.formula,
                    "substitution": mp_trace.substitution,
                    "result": mp_trace.result,
                    "unit": mp_trace.unit,
                    "comparison": f"Required Power = {mp_trace.result:.2f} W"
                },
                "gearbox_output_torque": {
                    "formula": ot_trace.formula,
                    "substitution": f"{motor.nominal_torque_nm} Nm × {gearbox.gear_ratio} × {gearbox.efficiency}",
                    "result": round(ot_trace.result, 4),
                    "unit": ot_trace.unit,
                    "comparison": f"{round(ot_trace.result, 4)} Nm >= {dt_trace.result} Nm (Design Torque)",
                    "status": "MEETS" if ot_trace.result >= dt_trace.result else "DOES_NOT_MEET"
                },
                "output_speed": {
                    "formula": "Output Speed = Motor Speed / Gear Ratio",
                    "substitution": f"{motor.nominal_speed_rpm} RPM / {gearbox.gear_ratio}",
                    "result": round(output_speed_rpm, 2),
                    "unit": "RPM",
                    "comparison": f"{round(output_speed_rpm, 2)} RPM >= {required_speed_rpm} RPM (Required Speed)",
                    "status": "MEETS" if output_speed_rpm >= required_speed_rpm else "DOES_NOT_MEET"
                }
            }

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
                "score": efficiency_score
            })

    # 4. Rank by closest match to the exact requirement
    valid_pairings.sort(key=lambda x: x["score"])

    return valid_pairings[:top_n]

