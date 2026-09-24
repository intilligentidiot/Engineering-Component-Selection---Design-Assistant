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

            valid_pairings.append({
                "motor": {
                    "id": motor.id,
                    "part_number": motor.part_number,
                    "manufacturer": motor.manufacturer.name,
                    "voltage_v": motor.voltage_v,
                    "power_w": motor.continuous_power_w
                },
                "gearbox": {
                    "id": gearbox.id,
                    "part_number": gearbox.part_number,
                    "manufacturer": gearbox.manufacturer.name,
                    "ratio": gearbox.gear_ratio,
                    "max_torque_nm": gearbox.max_output_torque_nm
                },
                "performance": {
                    "output_speed_rpm": round(output_speed_rpm, 2),
                    "output_torque_nm": round(calc_output_torque, 4),
                    "torque_margin_factor": round(torque_margin, 2)
                },
                "score": efficiency_score
            })

    # 4. Rank by closest match to the exact requirement
    valid_pairings.sort(key=lambda x: x["score"])

    return valid_pairings[:top_n]
