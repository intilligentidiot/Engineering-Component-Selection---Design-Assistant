import uuid
from typing import Dict, Any, List
from pydantic import BaseModel

class CalculationError(Exception):
    pass

class ValidationError(CalculationError):
    pass

class CalculationTrace(BaseModel):
    calculation_id: str
    formula: str
    inputs: Dict[str, Any]
    normalized_inputs: Dict[str, Any]
    substitution: str
    result: float
    unit: str
    assumptions: List[str]
    formula_version: str

def create_trace(
    formula: str,
    inputs: Dict[str, Any],
    normalized_inputs: Dict[str, Any],
    substitution: str,
    result: float,
    unit: str,
    assumptions: List[str],
    formula_version: str
) -> CalculationTrace:
    return CalculationTrace(
        calculation_id=str(uuid.uuid4()),
        formula=formula,
        inputs=inputs,
        normalized_inputs=normalized_inputs,
        substitution=substitution,
        result=result,
        unit=unit,
        assumptions=assumptions,
        formula_version=formula_version
    )
