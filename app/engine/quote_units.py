"""
The tool's own check of values the AI read from the user's text.

The AI copies the user's words (the quote) and gives a number in the unit the tool asks for.
The AI must not calculate, so the tool converts the quote itself:
  * the quote states a number with a unit the tool knows (e.g. "160 bar", "450 lbf", "4 in")
    and the field's unit is known → the tool's conversion is used. It must agree with what
    the AI read (within 5 %), otherwise the value is not used and the engineer enters it;
  * otherwise the AI's value must be one of the numbers in the quote (digits, a percentage,
    or number words such as "two"), or it is not used.
"""
import re
from typing import List, Optional, Tuple

# unit (normalised) -> (dimension, factor to the SI base unit)
UNITS = {
    # length (m)
    "mm": ("L", 1e-3), "cm": ("L", 1e-2), "m": ("L", 1.0), "km": ("L", 1e3),
    "in": ("L", 0.0254), "inch": ("L", 0.0254), "inches": ("L", 0.0254), '"': ("L", 0.0254),
    "ft": ("L", 0.3048), "feet": ("L", 0.3048), "foot": ("L", 0.3048),
    # mass (kg)
    "g": ("M", 1e-3), "kg": ("M", 1.0), "t": ("M", 1e3), "tonne": ("M", 1e3), "tonnes": ("M", 1e3),
    "lb": ("M", 0.45359237), "lbs": ("M", 0.45359237), "pound": ("M", 0.45359237), "pounds": ("M", 0.45359237),
    # force (N)
    "n": ("F", 1.0), "kn": ("F", 1e3), "mn": ("F", 1e6), "lbf": ("F", 4.4482216152605), "kgf": ("F", 9.80665),
    "kip": ("F", 4448.2216152605), "kips": ("F", 4448.2216152605),
    # speed (m/s)
    "m/s": ("V", 1.0), "mm/s": ("V", 1e-3), "m/min": ("V", 1 / 60), "ft/min": ("V", 0.00508), "fpm": ("V", 0.00508),
    "ft/s": ("V", 0.3048), "km/h": ("V", 1 / 3.6),
    # torque / moment (N·m)
    "nm": ("T", 1.0), "knm": ("T", 1e3), "nmm": ("T", 1e-3),
    "lbft": ("T", 1.3558179483314), "ftlb": ("T", 1.3558179483314), "lbfft": ("T", 1.3558179483314),
    "ftlbf": ("T", 1.3558179483314), "inlb": ("T", 0.112984829), "lbin": ("T", 0.112984829),
    "inlbf": ("T", 0.112984829), "lbfin": ("T", 0.112984829), "kgcm": ("T", 0.0980665), "kgfcm": ("T", 0.0980665),
    "ozin": ("T", 0.00706155),
    # pressure / stress (Pa)
    "pa": ("P", 1.0), "kpa": ("P", 1e3), "mpa": ("P", 1e6), "gpa": ("P", 1e9), "bar": ("P", 1e5),
    "psi": ("P", 6894.757293), "ksi": ("P", 6894757.293), "n/mm2": ("P", 1e6),
    # power (W)
    "w": ("W", 1.0), "kw": ("W", 1e3), "hp": ("W", 745.69987158),
    # density (kg/m³)
    "kg/m3": ("D", 1.0), "g/cm3": ("D", 1e3),
}

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "single": 1, "twin": 2, "double": 2,
                "triple": 3, "pair": 2, "dozen": 12}

# a number, then its unit (not the "x100" of "200x100")
_NUM_UNIT = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(%|(?![xX×]\s*\d)[a-zA-Z\"µ][a-zA-Z0-9/·.\-²³]*)?")
_TIMES = re.compile(r"\s*(?:[xX×*]|by)\s*\d")


def norm_unit(u: Optional[str]) -> str:
    u = (u or "").strip().lower().rstrip(".,;:)")
    u = u.replace("³", "3").replace("²", "2").replace("^", "")
    return re.sub(r"[·\s*]", "", u) if "/" in u else re.sub(r"[·.\-\s*]", "", u)


def unit_info(u: Optional[str]) -> Optional[Tuple[str, float]]:
    return UNITS.get(norm_unit(u))


def _numbers(quote: str) -> List[Tuple[float, str]]:
    """Numbers in the quote with their unit; in "200x100x50 mm" every number takes the mm."""
    quote = quote or ""
    found = []
    for m in _NUM_UNIT.finditer(quote):
        try:
            found.append([float(m.group(1).replace(",", "")), m.group(2) or "", m.end()])
        except ValueError:
            pass
    for i in range(len(found) - 2, -1, -1):
        if not found[i][1] and _TIMES.match(quote[found[i][2]:]):
            found[i][1] = found[i + 1][1]
    out = [(n, u) for n, u, _ in found]
    out += [(float(NUMBER_WORDS[w]), "") for w in re.findall(r"[a-z]+", quote.lower()) if w in NUMBER_WORDS]
    return out


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def checked_value(quote: str, ai_value, unit: Optional[str]) -> Optional[float]:
    """The value to use for this field, worked out by the tool from the user's own words, or None."""
    if not isinstance(ai_value, (int, float)) or isinstance(ai_value, bool):
        return None
    nums = _numbers(quote)
    target = unit_info(unit)
    if target:
        converted = [n * info[1] / target[1] for n, u in nums
                     for info in [unit_info(u)] if info and info[0] == target[0]]
        if converted:
            best = min(converted, key=lambda v: abs(v - ai_value))
            return best if _close(best, ai_value, 0.05) else None
    for n, u in nums:
        if _close(n, ai_value):
            return n
        if u == "%" and _close(n / 100, ai_value):
            return n / 100
    return None


def has_number(quote: str) -> bool:
    return bool(_numbers(quote))
