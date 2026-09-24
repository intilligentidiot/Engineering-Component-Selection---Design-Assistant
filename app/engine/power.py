from app.engine.trace import CalculationTrace, create_trace, ValidationError

def calculate_mechanical_power(torque_nm: float, speed_rpm: float, unit: str = "W") -> CalculationTrace:
    if torque_nm is None or speed_rpm is None:
        raise ValidationError("Torque and speed must be provided.")
    if speed_rpm < 0:
        raise ValidationError("Speed (RPM) cannot be negative.")
    if torque_nm < 0:
        raise ValidationError("Torque cannot be negative for this basic calculation.")
    
    power_kw = (torque_nm * speed_rpm) / 9550.0
    power_w = (torque_nm * speed_rpm) / 9.5493
    
    if unit == "kW":
        result = power_kw
        formula = "P(kW) = T(Nm) * RPM / 9550"
        substitution = f"P = {torque_nm} * {speed_rpm} / 9550"
    else:
        unit = "W"
        result = power_w
        formula = "P(W) = T(Nm) * RPM / 9.5493"
        substitution = f"P = {torque_nm} * {speed_rpm} / 9.5493"
        
    return create_trace(
        formula=formula,
        inputs={"torque_nm": torque_nm, "speed_rpm": speed_rpm},
        normalized_inputs={"torque_nm": torque_nm, "speed_rpm": speed_rpm},
        substitution=substitution,
        result=result,
        unit=unit,
        assumptions=[],
        formula_version="1.0"
    )

def calculate_motor_power_requirement(power_output: float, efficiency: float, unit: str = "W") -> CalculationTrace:
    if power_output is None or efficiency is None:
        raise ValidationError("Power output and efficiency must be provided.")
    if efficiency <= 0 or efficiency > 1:
        raise ValidationError("Efficiency must be a decimal between >0 and 1.")
    if power_output < 0:
        raise ValidationError("Power output cannot be negative.")
        
    result = power_output / efficiency
    
    return create_trace(
        formula="P_motor = P_output / Efficiency",
        inputs={"power_output": power_output, "efficiency": efficiency},
        normalized_inputs={"power_output": power_output, "efficiency": efficiency},
        substitution=f"P_motor = {power_output} / {efficiency}",
        result=result,
        unit=unit,
        assumptions=[f"Efficiency = {efficiency * 100}%"],
        formula_version="1.0"
    )
