"""
One selected standard per calculation (engineer's rule):

  * every result must come from the selected standard only;
  * basic physics (statics, kinematics, power = torque × speed, catalogue matching) is not
    defined by any design standard, so it is allowed under every selection;
  * a design method runs only when it is the selected standard (or a true equivalent,
    e.g. ANSI/ABMA Std 9/11 = ISO 281). Otherwise the step is "Not defined in <standard>";
  * "General engineering mechanics" is an explicit choice for work with no design standard:
    textbook design methods run, methods from any named standard do not.

A calculation's `standard` text decides its kind:
    empty                                   → basic physics
    starts with "General engineering mechanics" → general method
    anything else                           → that standard's method
"""
import re
from typing import List, Optional

GENERAL = "General engineering mechanics"

# Standards that use the same method and numbers (one family = one standard for this rule)
_FAMILIES = [
    {"iso281", "abmastd9", "abmastd11", "ansiabmastd9", "ansiabmastd11"},
]

# A standard code written inside a note or label, e.g. "DIN 743-1", "AS 1403", "ASME B106.1M", "AWS D1.1"
CODE_RE = re.compile(
    r"\b(?:ANSI/)?(?:ISO|DIN|EN|BS|AS/NZS|AS|NZS|IS|VDI|AGMA|IEC|NEMA)\s?\d{3,}(?:[-.:]\d+)*"
    r"|\bASME\s?[A-Z]+\d+(?:\.\d+)*[A-Z]?"
    r"|\b(?:ANSI/)?ABMA\s?(?:Std\.?\s?)?\d+"
    r"|\bAWS\s?D\d+(?:\.\d+)?"
    r"|\bAISC\s?\d{3}"
    r"|\bCSA\s?[A-Z]\d+(?:\.\d+)?"
    r"|\bNFPA\s?\d+"
    r"|\bCEMA\b")


def _key(s: str) -> str:
    k = re.sub(r"[^a-z0-9]", "", (s or "").lower())
    # "BS ISO 281", "BS EN 13001", "ANSI/AGMA 2001" name the same document as "ISO 281", "EN 13001", "AGMA 2001"
    k = re.sub(r"^(?:bs|ansi|asnzs|as|din|nzs)(?=(?:iso|en|iec)\d)", "", k)
    k = re.sub(r"^ansi(?=[a-z]+\d)", "", k)
    return k


def _main_code(s: str) -> str:
    """'DIN 743-1:2000-05' → 'din743', 'ANSI/ABMA Std 11' → 'abmastd11'."""
    m = CODE_RE.search(s or "")
    code = m.group(0) if m else (s or "")
    code = re.split(r"[-:]", code)[0] if re.match(r".*\d[-:]", code) else code
    return _key(code)


def same_standard(a: str, b: str) -> bool:
    ka, kb = _main_code(a), _main_code(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    return any(ka in f and kb in f for f in _FAMILIES)


def is_general(selected: str) -> bool:
    return (selected or "").strip().lower().startswith(GENERAL.lower())


def kind(method_standard: Optional[str]) -> str:
    s = (method_standard or "").strip()
    if not s:
        return "physics"
    return "general" if is_general(s) else "standard"


def allowed(method_standard: Optional[str], selected: str) -> bool:
    """May a calculation labelled `method_standard` run when the engineer selected `selected`?"""
    k = kind(method_standard)
    if k == "physics":
        return True
    if k == "general":
        return is_general(selected)
    if is_general(selected):
        return False
    codes = CODE_RE.findall(method_standard or "") or [method_standard]
    return any(same_standard(c, selected) for c in codes)


def foreign_codes(text: str, selected: str) -> List[str]:
    """Standard codes cited in `text` that are not the selected standard."""
    out = []
    for c in CODE_RE.findall(text or ""):
        if is_general(selected) or not same_standard(c, selected):
            out.append(c.strip())
    return sorted(set(out))
