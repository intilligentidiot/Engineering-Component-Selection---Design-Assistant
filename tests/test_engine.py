import pytest
from app.engine.trace import ValidationError
from app.engine.power import calculate_mechanical_power, calculate_motor_power_requirement
from app.engine.ratio import calculate_gear_ratio
from app.engine.torque import calculate_design_torque, calculate_gearbox_output_torque

def test_power_calculation():
    trace = calculate_mechanical_power(12, 60, unit="kW")
    assert trace.result == pytest.approx(0.075392, rel=1e-3)
    assert trace.unit == "kW"
    assert "12 * 60 / 9550" in trace.substitution

def test_power_calculation_w():
    trace = calculate_mechanical_power(12, 60, unit="W")
    assert trace.result == pytest.approx(75.398, rel=1e-3)
    assert trace.unit == "W"

def test_power_invalid_inputs():
    with pytest.raises(ValidationError):
        calculate_mechanical_power(-5, 60)
    with pytest.raises(ValidationError):
        calculate_mechanical_power(10, -60)

def test_motor_power_requirement():
    trace = calculate_motor_power_requirement(150, 0.9)
    assert trace.result == pytest.approx(166.666, rel=1e-3)

def test_motor_power_invalid_efficiency():
    with pytest.raises(ValidationError):
        calculate_motor_power_requirement(150, 1.2)
    with pytest.raises(ValidationError):
        calculate_motor_power_requirement(150, 0)

def test_gear_ratio():
    trace = calculate_gear_ratio(1200, 60)
    assert trace.result == 20.0
    assert trace.unit == "dimensionless"

def test_gear_ratio_zero_output():
    with pytest.raises(ValidationError):
        calculate_gear_ratio(1200, 0)

def test_design_torque():
    trace = calculate_design_torque(15, 1.5)
    assert trace.result == 22.5
    assert trace.unit == "Nm"

def test_design_torque_invalid():
    with pytest.raises(ValidationError):
        calculate_design_torque(15, -1)

def test_output_torque():
    trace = calculate_gearbox_output_torque(2, 20, 0.90)
    assert trace.result == 36.0
    assert trace.unit == "Nm"

def test_output_torque_invalid():
    with pytest.raises(ValidationError):
        calculate_gearbox_output_torque(2, 20, 1.1)

def test_trace_structure():
    trace = calculate_gear_ratio(100, 10)
    assert hasattr(trace, "calculation_id")
    assert trace.formula == "Gear Ratio = Motor RPM / Output RPM"
    assert trace.inputs == {"motor_rpm": 100, "output_rpm": 10}
    assert trace.formula_version == "1.0"
