"""
Stage 8 — engineering defaults that still need sign-off by the engineering owner.

Every value in this file is a *chosen default*, not a verified fact about the
user's machine. Each one is listed in docs/ENGINEERING_DEFAULTS_TO_REVIEW.md.
Bump DEFAULTS_VERSION whenever a value here changes so traces stay auditable.
"""

DEFAULTS_VERSION = "2026-10-14-draft-1"

# Standard gravity (CONSTANT, not a default)
G = 9.80665

# Service factor table: AGMA-style, electric-motor prime mover.
# Keys: load class -> (under 3 h/day, 3–10 h/day, over 10 h/day)
SERVICE_FACTOR_TABLE = {
    "uniform":  (0.80, 1.00, 1.25),
    "moderate": (1.00, 1.25, 1.50),
    "heavy":    (1.50, 1.75, 2.00),
}

LOAD_CLASS_LABELS = {
    "uniform":  "Smooth / uniform load",
    "moderate": "Moderate shocks",
    "heavy":    "Heavy shocks",
}

# Default allowed over-speed of the selected drive vs the required speed (%).
# Matches the window the selection engine has always used (1.5 × required).
DEFAULT_SPEED_TOLERANCE_PCT = 50.0

# Fit indicator (comparison aid only, spec §6)
FIT_WEIGHTS = {"torque": 0.4, "speed": 0.4, "power": 0.2}
FIT_IDEAL_MARGIN_MAX = 1.5    # margin up to 1.5× scores 100 %
FIT_OVERSIZE_LIMIT = 3.0      # beyond 3× scores the floor value
FIT_OVERSIZE_FLOOR = 0.25


def service_factor_for(load_class: str, hours_per_day: float) -> float:
    under_3, mid, over_10 = SERVICE_FACTOR_TABLE[load_class]
    if hours_per_day < 3:
        return under_3
    if hours_per_day <= 10:
        return mid
    return over_10


def hours_band_label(hours_per_day: float) -> str:
    if hours_per_day < 3:
        return "under 3 h/day"
    if hours_per_day <= 10:
        return "3–10 h/day"
    return "over 10 h/day"
