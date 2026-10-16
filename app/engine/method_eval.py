"""
Deterministic evaluation of an AI-chosen calculation method.

For topics without a checked calculation module, the AI chooses the method
(standard, formulas, required inputs) as a MethodPlan. The AI never produces
the numbers: this module evaluates each formula itself, step by step, from the
values the engineer entered, and shows every substitution.

Formulas are parsed with Python's `ast` and only plain arithmetic is allowed:
numbers, the plan's own symbols, + - * / ** and a fixed list of maths functions.
Anything else (attribute access, imports, comprehensions, strings…) is rejected.
The method itself is not verified — results are always labelled as such.
"""
import ast
import math
import re
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

FUNCS = {
    "sqrt": math.sqrt, "exp": math.exp, "log": math.log, "log10": math.log10, "ln": math.log,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "atan2": math.atan2, "radians": math.radians, "degrees": math.degrees,
    "abs": abs, "min": min, "max": max, "ceil": math.ceil, "floor": math.floor, "pow": pow,
}
CONSTS = {"pi": math.pi, "g": 9.80665}
_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_ABS = 1e100


# ─────────────────────────────────────────────────────────────
# Plan schema (what the AI returns)
# ─────────────────────────────────────────────────────────────

class PlanInput(BaseModel):
    symbol: str = Field(..., description="Short identifier used in formulas, e.g. Fr, n, C.")
    name: str = Field(..., description="Plain-English name, e.g. 'Radial load'.")
    unit: str = Field(..., description="Unit the value must be entered in, e.g. 'N', 'rpm', 'mm'.")
    value: Optional[float] = Field(None, description="Only if the user stated it, converted to `unit`.")
    quote: Optional[str] = Field(None, description="The user's exact words for `value`, copied verbatim.")
    typical_value: Optional[float] = Field(None, description="Optional typical value when the user did not give one (never for the user's own dimensions, loads or speeds).")
    typical_note: Optional[str] = Field(None, description="Where the typical value comes from and its usual range.")


class PlanStep(BaseModel):
    symbol: str = Field(..., description="Identifier for this step's result, used by later steps.")
    name: str = Field(..., description="Plain-English name of the quantity calculated.")
    unit: str = Field(..., description="Unit of the result.")
    expression: str = Field(..., description="Formula using only earlier symbols, numbers, + - * / ** and functions "
                                             "sqrt exp log log10 sin cos tan asin acos atan atan2 radians degrees abs min max; "
                                             "constants pi and g (9.80665). Include any unit conversion factors explicitly.")
    note: Optional[str] = Field(None, description="Short explanation or the clause of the standard it comes from.")


class MethodPlan(BaseModel):
    title: str = Field(..., description="What is being calculated, e.g. 'Bearing basic rating life'.")
    standard: Optional[str] = Field(None, description="Standard or reference the method follows, e.g. 'ISO 281:2007'.")
    summary: str = Field(..., description="Two or three plain-English sentences describing the method.")
    inputs: List[PlanInput] = Field(default_factory=list)
    steps: List[PlanStep] = Field(default_factory=list)
    result_symbols: List[str] = Field(default_factory=list, description="Symbols of the main results to highlight.")
    limitations: List[str] = Field(default_factory=list, description="What the method does not cover.")


class EvaluatedStep(BaseModel):
    symbol: str
    name: str
    unit: str
    formula: str
    substitution: str
    result: float
    note: Optional[str] = None


class MethodResult(BaseModel):
    status: str  # CALCULATED | REQUIREMENTS_INCOMPLETE | INVALID_PLAN | CALCULATION_ERROR
    missing_inputs: List[Dict[str, str]] = []
    errors: List[str] = []
    steps: List[EvaluatedStep] = []
    results: List[EvaluatedStep] = []


class PlanError(Exception):
    pass


# ─────────────────────────────────────────────────────────────
# Safe expression handling
# ─────────────────────────────────────────────────────────────

_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.Pow: lambda a, b: a ** b}
_UNOPS = {ast.USub: lambda a: -a, ast.UAdd: lambda a: a}


def _parse(expr: str) -> ast.Expression:
    expr = expr.replace("^", "**").replace("×", "*").replace("·", "*").replace("−", "-")
    if len(expr) > 500:
        raise PlanError("Formula is too long.")
    try:
        return ast.parse(expr, mode="eval")
    except SyntaxError:
        raise PlanError(f"Formula could not be read: {expr}")


def _names(node: ast.AST) -> List[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and not (n.id in FUNCS or n.id in CONSTS):
            out.append(n.id)
    return out


def _check(node: ast.AST) -> None:
    """Reject anything that is not plain arithmetic."""
    for n in ast.walk(node):
        if isinstance(n, (ast.Expression, ast.Load, ast.operator, ast.unaryop)):
            continue
        if isinstance(n, ast.BinOp):
            if type(n.op) not in _BINOPS:
                raise PlanError("Only + - * / and powers are allowed in formulas.")
        elif isinstance(n, ast.UnaryOp):
            if type(n.op) not in _UNOPS:
                raise PlanError("Unsupported operator in formula.")
        elif isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float)) or isinstance(n.value, bool):
                raise PlanError("Only numbers are allowed as constants.")
        elif isinstance(n, ast.Name):
            if not _SYMBOL.match(n.id):
                raise PlanError(f"Invalid symbol '{n.id}'.")
        elif isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in FUNCS or n.keywords:
                raise PlanError("Only the standard maths functions are allowed in formulas.")
        else:
            raise PlanError(f"'{type(n).__name__}' is not allowed in formulas.")


def _eval(node: ast.AST, env: Dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id in CONSTS:
            return CONSTS[node.id]
        raise PlanError(f"Unknown symbol '{node.id}'.")
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, env), _eval(node.right, env)
        if isinstance(node.op, ast.Pow) and abs(b) > 1000:
            raise PlanError("Exponent too large.")
        return _BINOPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp):
        return _UNOPS[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.Call):
        return float(FUNCS[node.func.id](*[_eval(a, env) for a in node.args]))
    raise PlanError("Unsupported formula.")


def _fmt(x: float) -> str:
    if x == 0:
        return "0"
    if 1e4 <= abs(x) < 1e12:
        return f"{x:.0f}"           # 15670, not 1.567e+04
    if abs(x) >= 1e12 or abs(x) < 1e-3:
        return f"{x:.4g}"
    return f"{float(f'{x:.4g}'):g}"


class _Sub(ast.NodeTransformer):
    def __init__(self, env):
        self.env = env

    def visit_Name(self, node):
        if node.id in self.env:
            return ast.Name(id=_fmt(self.env[node.id]), ctx=ast.Load())
        return node


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def validate_plan(plan: MethodPlan) -> List[str]:
    """Structural checks before showing a plan to the user. Returns a list of problems."""
    problems: List[str] = []
    seen = set(CONSTS)
    if not plan.steps:
        problems.append("The method has no calculation steps.")
    for i in plan.inputs:
        if not _SYMBOL.match(i.symbol) or i.symbol in FUNCS:
            problems.append(f"Invalid input symbol '{i.symbol}'.")
        if i.symbol in seen:
            problems.append(f"Symbol '{i.symbol}' is defined twice.")
        seen.add(i.symbol)
    for s in plan.steps:
        if not _SYMBOL.match(s.symbol) or s.symbol in FUNCS:
            problems.append(f"Invalid step symbol '{s.symbol}'.")
        try:
            tree = _parse(s.expression)
            _check(tree)
            unknown = [n for n in _names(tree) if n not in seen]
            if unknown:
                problems.append(f"Step '{s.name}' uses undefined symbol(s): {', '.join(sorted(set(unknown)))}.")
        except PlanError as e:
            problems.append(f"Step '{s.name}': {e}")
        if s.symbol in seen:
            problems.append(f"Symbol '{s.symbol}' is defined twice.")
        seen.add(s.symbol)
    for r in plan.result_symbols:
        if r not in {s.symbol for s in plan.steps}:
            problems.append(f"Result '{r}' is not calculated by any step.")
    return problems


def evaluate_method(plan: MethodPlan, values: Dict[str, Any]) -> MethodResult:
    problems = validate_plan(plan)
    if problems:
        return MethodResult(status="INVALID_PLAN", errors=problems)

    env: Dict[str, float] = {}
    missing = []
    for i in plan.inputs:
        v = values.get(i.symbol)
        if v is None or v == "":
            missing.append({"symbol": i.symbol, "label": f"{i.name} ({i.unit})"})
            continue
        try:
            env[i.symbol] = float(v)
        except (TypeError, ValueError):
            return MethodResult(status="CALCULATION_ERROR", errors=[f"{i.name} must be a number."])
    if missing:
        return MethodResult(status="REQUIREMENTS_INCOMPLETE", missing_inputs=missing)

    steps: List[EvaluatedStep] = []
    for s in plan.steps:
        tree = _parse(s.expression)
        try:
            result = _eval(tree, env)
        except ZeroDivisionError:
            return MethodResult(status="CALCULATION_ERROR", steps=steps,
                                errors=[f"Step '{s.name}' divides by zero — check the inputs."])
        except (ValueError, OverflowError, PlanError) as e:
            return MethodResult(status="CALCULATION_ERROR", steps=steps,
                                errors=[f"Step '{s.name}' could not be calculated ({e}) — check the inputs."])
        if isinstance(result, complex) or math.isnan(result) or abs(result) > _MAX_ABS:
            return MethodResult(status="CALCULATION_ERROR", steps=steps,
                                errors=[f"Step '{s.name}' gave an invalid number — check the inputs."])
        subst = ast.unparse(_Sub(env).visit(_parse(s.expression)))
        steps.append(EvaluatedStep(symbol=s.symbol, name=s.name, unit=s.unit, formula=f"{s.symbol} = {s.expression}",
                                   substitution=f"{s.symbol} = {subst} = {_fmt(result)} {s.unit}".strip(),
                                   result=result, note=s.note))
        env[s.symbol] = result

    wanted = plan.result_symbols or [plan.steps[-1].symbol]
    return MethodResult(status="CALCULATED", steps=steps, results=[st for st in steps if st.symbol in wanted])
