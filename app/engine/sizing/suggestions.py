"""
Suggested values for inputs the user did not give (engineering-owner sign-off pending).

These are typical published ranges for common hardware, not facts about the
user's machine. Where a range exists, the end that gives the LARGER (safer)
motor requirement is suggested. A suggestion is only ever used after it has
been shown to the user, who can change it; every suggestion used is listed in
the result. Bump SUGGESTIONS_VERSION when a value changes.

Geometry, speeds, loads, densities and tension are never suggested — they are
properties of the user's own machine and must come from the user.
"""
from typing import Dict, Optional, Any
from app.engine.sizing.defaults import DEFAULTS_VERSION

SUGGESTIONS_VERSION = DEFAULTS_VERSION


def _s(label: str, value: Any, note: str) -> Dict[str, Any]:
    return {"label": label, "value": value, "note": note}


_ACCEL = _s("Time to reach full speed", 1.0,
            "Typical gentle start-up. It only affects the start-up (peak) torque — enter the real time if the "
            "machine must start faster.")
_GENERAL = {
    "params.accel_time_s": _ACCEL,
    "duty.load_class": _s("How smooth is the work", "moderate",
                          "Middle option, used when not stated. Choose 'Heavy shocks' if parts jam or impact."),
    "duty.hours_per_day": _s("Running hours per day", 8,
                             "One shift. If it runs longer, increase this — it raises the safety margin."),
    "limits.max_voltage_v": _s("Supply voltage", 24, "Common industrial DC supply. Change it to match your power supply."),
}


def suggestions_for(application: str, machine_text: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Suggestions available for this application, keyed by form path."""
    out = dict(_GENERAL)
    text = (machine_text or "").lower()
    if application == "conveyor":
        out["params.friction_coefficient"] = _s(
            "Friction coefficient", 0.5,
            "A belt sliding on a steel bed is typically 0.3–0.5; the higher value is used to be safe. "
            "Roller conveyors are much lower (about 0.03–0.05) — enter that if yours runs on rollers.")
    if application in ("screw_axis", "rack_pinion_axis"):
        out["params.guide_friction"] = _s(
            "Guide friction coefficient", 0.01,
            "Rolling linear guides are typically 0.002–0.01; the higher value is used to be safe. "
            "Plain sliding guides are much higher (about 0.1–0.2).")
    if application == "screw_axis":
        if "ball" in text:
            out["params.screw_efficiency"] = _s(
                "Screw efficiency", 0.9, "Ball screws are typically 0.9–0.95; the lower value is used to be safe.")
        else:
            out["params.screw_efficiency"] = _s(
                "Screw efficiency", 0.2,
                "Lead (trapezoidal) screws are typically 0.2–0.5; the lower value is used to be safe. "
                "If it is a ball screw, use about 0.9.")
    return out
