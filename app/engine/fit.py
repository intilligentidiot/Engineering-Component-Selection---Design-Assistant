"""
Fit / compatibility indicator (spec §6).

A secondary comparison aid for candidates whose engineering status is MEETS.
It measures how closely a candidate matches the requirement (penalising
oversizing and speed mismatch). It is NOT a safety, confidence or probability
figure and never replaces the MEETS / DOES_NOT_MEET / DATA_INCOMPLETE status.
"""
from typing import Optional, Dict, Any
from app.engine.sizing.defaults import (
    FIT_WEIGHTS, FIT_IDEAL_MARGIN_MAX, FIT_OVERSIZE_LIMIT, FIT_OVERSIZE_FLOOR,
)


def _margin_score(margin: float) -> float:
    """1.0 for margins 1.0–1.5×, falling to 0.5 at 3×, floor beyond that."""
    if margin <= FIT_IDEAL_MARGIN_MAX:
        return 1.0
    if margin <= FIT_OVERSIZE_LIMIT:
        span = FIT_OVERSIZE_LIMIT - FIT_IDEAL_MARGIN_MAX
        return 1.0 - 0.5 * (margin - FIT_IDEAL_MARGIN_MAX) / span
    return FIT_OVERSIZE_FLOOR


def compute_fit(
    available_torque_nm: float,
    design_torque_nm: float,
    output_speed_rpm: float,
    required_speed_rpm: float,
    speed_tolerance_pct: float,
    available_power_w: Optional[float] = None,
    required_power_w: Optional[float] = None,
) -> Dict[str, Any]:
    tol = max(speed_tolerance_pct / 100.0, 0.01)
    scores = {
        "torque": _margin_score(available_torque_nm / design_torque_nm),
        "speed": max(0.0, 1.0 - abs(output_speed_rpm - required_speed_rpm) / (tol * required_speed_rpm)),
    }
    if available_power_w and required_power_w:
        scores["power"] = _margin_score(available_power_w / required_power_w)

    # Renormalise weights if power data is not available
    total_w = sum(FIT_WEIGHTS[k] for k in scores)
    percent = round(100 * sum(FIT_WEIGHTS[k] * s for k, s in scores.items()) / total_w)
    return {
        "percent": percent,
        "breakdown": {k: round(v * 100) for k, v in scores.items()},
        "label": "Comparison only — how closely this candidate matches the requirement. "
                 "Not a safety or confidence figure.",
    }
