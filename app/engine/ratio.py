from app.engine.trace import CalculationTrace, create_trace, ValidationError

def calculate_gear_ratio(motor_rpm: float, output_rpm: float) -> CalculationTrace:
    if motor_rpm is None or output_rpm is None:
        raise ValidationError("Motor RPM and output RPM must be provided.")
    if motor_rpm < 0 or output_rpm < 0:
        raise ValidationError("RPM values cannot be negative.")
    if output_rpm == 0:
        raise ValidationError("Output RPM cannot be zero (division by zero).")
        
    ratio = motor_rpm / output_rpm
    
    return create_trace(
        formula="Gear Ratio = Motor RPM / Output RPM",
        inputs={"motor_rpm": motor_rpm, "output_rpm": output_rpm},
        normalized_inputs={"motor_rpm": motor_rpm, "output_rpm": output_rpm},
        substitution=f"Ratio = {motor_rpm} / {output_rpm}",
        result=ratio,
        unit="dimensionless",
        assumptions=[],
        formula_version="1.0"
    )
