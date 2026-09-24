from app.engine.trace import CalculationTrace, create_trace, ValidationError

def calculate_design_torque(required_torque_nm: float, service_factor: float) -> CalculationTrace:
    if required_torque_nm is None or service_factor is None:
        raise ValidationError("Required torque and service factor must be provided.")
    if required_torque_nm < 0:
        raise ValidationError("Required torque cannot be negative.")
    if service_factor <= 0:
        raise ValidationError("Service factor must be strictly greater than 0.")
        
    design_torque = required_torque_nm * service_factor
    
    return create_trace(
        formula="T_design = T_required * Service Factor",
        inputs={"required_torque_nm": required_torque_nm, "service_factor": service_factor},
        normalized_inputs={"required_torque_nm": required_torque_nm, "service_factor": service_factor},
        substitution=f"T_design = {required_torque_nm} * {service_factor}",
        result=design_torque,
        unit="Nm",
        assumptions=[f"User provided Service Factor: {service_factor}"],
        formula_version="1.0"
    )

def calculate_gearbox_output_torque(motor_torque_nm: float, gear_ratio: float, efficiency: float) -> CalculationTrace:
    if motor_torque_nm is None or gear_ratio is None or efficiency is None:
        raise ValidationError("Motor torque, gear ratio, and efficiency must be provided.")
    if motor_torque_nm < 0 or gear_ratio <= 0:
        raise ValidationError("Motor torque and gear ratio must be non-negative/positive.")
    if efficiency <= 0 or efficiency > 1:
        raise ValidationError("Efficiency must be a decimal between >0 and 1.")
        
    output_torque = motor_torque_nm * gear_ratio * efficiency
    
    return create_trace(
        formula="T_output = T_motor * Gear Ratio * Efficiency",
        inputs={"motor_torque_nm": motor_torque_nm, "gear_ratio": gear_ratio, "efficiency": efficiency},
        normalized_inputs={"motor_torque_nm": motor_torque_nm, "gear_ratio": gear_ratio, "efficiency": efficiency},
        substitution=f"T_output = {motor_torque_nm} * {gear_ratio} * {efficiency}",
        result=output_torque,
        unit="Nm",
        assumptions=[f"Efficiency = {efficiency * 100}%"],
        formula_version="1.0"
    )
