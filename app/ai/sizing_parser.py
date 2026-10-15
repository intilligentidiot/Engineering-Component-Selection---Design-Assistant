"""
Stage 8.x — Natural-language extraction for the application-sizing form.

The AI (or the deterministic mock) only *reads* the user's text and returns
the values that were actually written, each with the exact words it came from.
It never calculates, never selects products, and never supplies values from
its own knowledge (density, friction, efficiency, tension, …).

Guards applied to every provider's output (in SizingRequirementParser.parse):
  * every value must carry a quote that appears verbatim in the user's text,
    otherwise it is rejected;
  * numeric values must come from a quote that contains a number;
  * values are range-checked and categorical values checked against allowed sets.
Extracted values are AI_EXTRACTED: the UI asks the user to confirm them before
they are used (spec §8).

Provider selection follows app/ai/provider.py (AI_PROVIDER=mock|openai|gemini).
"""
import os
import re
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Extraction schema (what a provider returns)
# ─────────────────────────────────────────────────────────────

class FieldQuote(BaseModel):
    field: str = Field(..., description="Name of the extracted field, exactly as in this schema.")
    quote: str = Field(..., description="The exact words from the user's text that state this value, copied verbatim.")


class SizingExtraction(BaseModel):
    application: Optional[str] = Field(None, description="One of: conveyor, hoist, rotary_table, screw_axis, rack_pinion_axis, winding — only when the user's machine really is that kind of motion (e.g. 'belt feeder' → conveyor, 'winch' → hoist, 'dial table' → rotary_table). Null if it is not one of these.")
    machine_as_written: Optional[str] = Field(None, description="The machine name exactly as the user wrote it, e.g. 'belt feeder'.")
    machine_explanation: Optional[str] = Field(None, description="One plain-English sentence explaining which kind of motion the machine is and why, e.g. 'A palletizer lift raises loads vertically, so it is calculated as a lift.'")
    unsupported_machine: Optional[str] = Field(None, description="If the user describes something that is NOT one of the six supported motions (e.g. a pump, fan, mixer, press, or a bearing), its name exactly as written. Never force it into a supported type.")
    material_name: Optional[str] = Field(None, description="Material name as written by the user.")
    density_kg_m3: Optional[float] = Field(None, description="Density in kg/m³ ONLY if the user states it (convert g/cm³ × 1000). Never from your own knowledge.")
    hardness_scale: Optional[str] = Field(None, description="'Shore A' or 'Shore D' if stated.")
    hardness_value: Optional[float] = Field(None, description="Hardness number if stated.")
    part_shape: Optional[str] = Field(None, description="One of: block, cylinder, tube, sphere, volume, mass.")
    length_mm: Optional[float] = Field(None, description="Part length in mm.")
    width_mm: Optional[float] = Field(None, description="Part width in mm.")
    height_mm: Optional[float] = Field(None, description="Part height in mm.")
    diameter_mm: Optional[float] = Field(None, description="Part diameter in mm (the part, not a pulley/drum).")
    outer_diameter_mm: Optional[float] = Field(None, description="Tube outer diameter in mm.")
    inner_diameter_mm: Optional[float] = Field(None, description="Tube inner diameter in mm.")
    volume_cm3: Optional[float] = Field(None, description="Part volume in cm³.")
    part_mass_kg: Optional[float] = Field(None, description="Mass of ONE part (or the single load) in kg.")
    quantity: Optional[int] = Field(None, description="Number of parts moved at the same time.")
    carrier_mass_kg: Optional[float] = Field(None, description="Pallet / fixture / carriage mass in kg.")
    speed_m_s: Optional[float] = Field(None, description="Linear speed (belt, lift, travel or line speed) in m/s.")
    accel_time_s: Optional[float] = Field(None, description="Time to reach full speed in seconds.")
    incline_deg: Optional[float] = Field(None, description="Conveyor incline in degrees (0 if the user says flat/horizontal).")
    friction_coefficient: Optional[float] = Field(None, description="Conveyor friction coefficient if stated.")
    drive_diameter_mm: Optional[float] = Field(None, description="Conveyor drive pulley/roller/sprocket diameter in mm.")
    belt_mass_kg: Optional[float] = Field(None, description="Belt/chain moving mass in kg.")
    extra_force_n: Optional[float] = Field(None, description="Extra resisting force on a conveyor in N.")
    drive_efficiency: Optional[float] = Field(None, description="Efficiency of an extra chain/belt stage as a fraction 0–1.")
    drum_diameter_mm: Optional[float] = Field(None, description="Hoist drum diameter in mm.")
    rope_falls: Optional[int] = Field(None, description="Number of rope falls.")
    rope_efficiency: Optional[float] = Field(None, description="Rope/sheave efficiency as a fraction 0–1.")
    hook_mass_kg: Optional[float] = Field(None, description="Hook/carriage mass in kg.")
    counterweight_kg: Optional[float] = Field(None, description="Counterweight mass in kg.")
    load_arrangement: Optional[str] = Field(None, description="Turntable: parts_at_radius, solid_disc or custom_inertia.")
    load_radius_mm: Optional[float] = Field(None, description="Turntable load radius in mm.")
    load_inertia_kg_m2: Optional[float] = Field(None, description="Load inertia in kg·m².")
    table_inertia_kg_m2: Optional[float] = Field(None, description="Turntable own inertia in kg·m².")
    motion_mode: Optional[str] = Field(None, description="Turntable: continuous or index.")
    target_speed_rpm: Optional[float] = Field(None, description="Turntable speed in rpm.")
    index_angle_deg: Optional[float] = Field(None, description="Index angle per step in degrees.")
    index_time_s: Optional[float] = Field(None, description="Time for one index step in seconds.")
    friction_torque_nm: Optional[float] = Field(None, description="Bearing friction torque in N·m.")
    axis_angle_deg: Optional[float] = Field(None, description="Linear axis angle: 0 horizontal, 90 vertical.")
    guide_friction: Optional[float] = Field(None, description="Linear guide friction coefficient.")
    process_force_n: Optional[float] = Field(None, description="Process (pressing/cutting) force in N.")
    screw_lead_mm: Optional[float] = Field(None, description="Screw lead in mm per turn.")
    screw_efficiency: Optional[float] = Field(None, description="Screw efficiency as a fraction 0–1, only if stated.")
    pinion_diameter_mm: Optional[float] = Field(None, description="Pinion / belt pulley pitch diameter in mm.")
    web_tension_n: Optional[float] = Field(None, description="Web tension in N.")
    core_diameter_mm: Optional[float] = Field(None, description="Winding core diameter in mm.")
    full_roll_diameter_mm: Optional[float] = Field(None, description="Full roll diameter in mm.")
    roll_width_mm: Optional[float] = Field(None, description="Roll width in mm.")
    load_class: Optional[str] = Field(None, description="uniform (smooth), moderate (some shocks), heavy (heavy shocks / jams).")
    hours_per_day: Optional[float] = Field(None, description="Running hours per day.")
    service_factor_override: Optional[float] = Field(None, description="Service factor only if the user explicitly states one.")
    run_time_s: Optional[float] = Field(None, description="Run time per stop/start cycle in seconds.")
    dwell_time_s: Optional[float] = Field(None, description="Stopped time per cycle in seconds.")
    max_voltage_v: Optional[float] = Field(None, description="Maximum supply voltage in V.")
    quotes: List[FieldQuote] = Field(default_factory=list, description="One entry per non-null field above, with the verbatim words from the user's text.")
    clarifications: List[str] = Field(default_factory=list, description="Questions for the user about missing or ambiguous information.")


# Flat extraction field → sizing-form path
FIELD_PATHS: Dict[str, str] = {
    "application": "application",
    "material_name": "material.name", "density_kg_m3": "material.density_kg_m3",
    "hardness_scale": "material.hardness_scale", "hardness_value": "material.hardness_value",
    "part_shape": "part.shape", "length_mm": "part.length_mm", "width_mm": "part.width_mm",
    "height_mm": "part.height_mm", "diameter_mm": "part.diameter_mm",
    "outer_diameter_mm": "part.outer_diameter_mm", "inner_diameter_mm": "part.inner_diameter_mm",
    "volume_cm3": "part.volume_cm3", "part_mass_kg": "part.mass_kg", "quantity": "part.quantity",
    "carrier_mass_kg": "part.carrier_mass_kg",
    "load_class": "duty.load_class", "hours_per_day": "duty.hours_per_day",
    "service_factor_override": "duty.service_factor_override",
    "run_time_s": "duty.run_time_s", "dwell_time_s": "duty.dwell_time_s",
    "max_voltage_v": "limits.max_voltage_v",
}
_PARAM_FIELDS = [
    "speed_m_s", "accel_time_s", "incline_deg", "friction_coefficient", "drive_diameter_mm",
    "belt_mass_kg", "extra_force_n", "drive_efficiency", "drum_diameter_mm", "rope_falls",
    "rope_efficiency", "hook_mass_kg", "counterweight_kg", "load_arrangement", "load_radius_mm",
    "load_inertia_kg_m2", "table_inertia_kg_m2", "motion_mode", "target_speed_rpm",
    "index_angle_deg", "index_time_s", "friction_torque_nm", "axis_angle_deg", "guide_friction",
    "process_force_n", "screw_lead_mm", "screw_efficiency", "pinion_diameter_mm", "web_tension_n",
    "core_diameter_mm", "full_roll_diameter_mm", "roll_width_mm",
]
FIELD_PATHS.update({f: f"params.{f}" for f in _PARAM_FIELDS})

_CATEGORICAL = {
    "application": {"conveyor", "hoist", "rotary_table", "screw_axis", "rack_pinion_axis", "winding"},
    "part_shape": {"block", "cylinder", "tube", "sphere", "volume", "mass"},
    "load_arrangement": {"parts_at_radius", "solid_disc", "custom_inertia"},
    "motion_mode": {"continuous", "index"},
    "load_class": {"uniform", "moderate", "heavy"},
    "hardness_scale": {"Shore A", "Shore D"},
}
_TEXT_FIELDS = {"material_name"}
_FRACTIONS = {"friction_coefficient", "drive_efficiency", "rope_efficiency", "guide_friction", "screw_efficiency"}
_ZERO_OK = {"incline_deg", "axis_angle_deg"}
# Angles may be stated in words instead of numbers
_WORD_ANGLES = {"vertical": 90.0, "vertically": 90.0, "horizontal": 0.0, "horizontally": 0.0, "flat": 0.0, "level": 0.0}


# ─────────────────────────────────────────────────────────────
# Result returned to the API / UI
# ─────────────────────────────────────────────────────────────

class ExtractedValue(BaseModel):
    path: str
    value: Any
    quote: str


class RejectedValue(BaseModel):
    field: str
    reason: str


class SizingParseResult(BaseModel):
    parser_status: str  # PARSED | NEEDS_CLARIFICATION | NOTHING_FOUND | UNSUPPORTED_MACHINE | ERROR_*
    provider: str
    machine_as_written: Optional[str] = None     # e.g. "belt feeder" (mapped to `application`)
    unsupported_machine: Optional[str] = None    # e.g. "bearing" — not a supported motion
    unsupported_message: Optional[str] = None
    machine_explanation: Optional[str] = None    # why the machine was treated as that motion
    values: List[ExtractedValue] = []
    rejected: List[RejectedValue] = []
    clarifications: List[str] = []


SYSTEM_INSTRUCTION = (
    "You extract engineering inputs for a motor-sizing form from the user's text. "
    "Return only values the user actually wrote. Convert units to the units named in each field "
    "description, but copy the user's original words into `quotes` verbatim — one quote per non-null field. "
    "Never supply values from your own knowledge: if a material is named without a density, leave density null "
    "and ask for it in `clarifications`. The same applies to friction coefficients, efficiencies, web tension, "
    "service factor and inertia. "
    "Do not calculate torque, speed, power or any other result. Do not select products. "
    "If something is ambiguous, leave it null and add a short clarification question. "
    "MACHINE TYPE — classify by the physics of what the motor must move, not by the machine's name. Any machine, "
    "whatever it is called, is supported when its driven motion is one of these: "
    "conveyor = a load moved horizontally or up a slope on a belt, chain, rollers or a sliding surface "
    "(feeders, transfer lines, roller tables, pallet conveyors, sorting belts...); "
    "hoist = a load raised or lowered vertically by a rope, cable or chain on a drum/sprocket "
    "(winches, cranes, lifts, elevators, palletizer lifts...); "
    "rotary_table = a table or mass rotated about an axis, continuously or in steps "
    "(turntables, indexers, dial tables, carousels, rotary fixtures...); "
    "screw_axis = linear motion driven by a lead or ball screw (actuators, screw jacks, electric cylinders...); "
    "rack_pinion_axis = linear motion driven by a rack and pinion or a toothed belt (gantries, belt-driven slides...); "
    "winding = material wound onto or off a roll under tension (winders, unwinders, reels, spoolers, coilers...). "
    "Copy the user's own words for the machine into machine_as_written and write machine_explanation. "
    "If the driven motion is something else — fluid handling (pumps, fans, compressors), mixing, crushing, "
    "pressing/punching, vehicles, or a component such as a bearing — put its name in unsupported_machine, "
    "leave application null and never force it into one of the six types."
)


# ─────────────────────────────────────────────────────────────
# Base parser with shared verification
# ─────────────────────────────────────────────────────────────

class ProviderError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


class SizingRequirementParser(ABC):
    name = "base"

    @abstractmethod
    def extract(self, text: str) -> SizingExtraction:
        """Provider-specific extraction. May raise ProviderError."""

    def parse(self, text: str) -> SizingParseResult:
        if not text or not text.strip():
            return SizingParseResult(parser_status="NOTHING_FOUND", provider=self.name,
                                     clarifications=["Please describe your application first."])
        try:
            ex = self.extract(text)
        except ProviderError as e:
            logger.error("[Sizing parser] %s — %s", self.name, e.status)
            return SizingParseResult(parser_status=e.status, provider=self.name, clarifications=[e.message])
        except Exception as e:  # never let a provider crash the request
            logger.error("[Sizing parser] %s — unexpected %s", self.name, type(e).__name__)
            return SizingParseResult(parser_status="ERROR_UNEXPECTED", provider=self.name,
                                     clarifications=[f"Text reader error: {type(e).__name__}. Please fill the form by hand."])
        return self._verify(text, ex)

    def _verify(self, text: str, ex: SizingExtraction) -> SizingParseResult:
        norm_text = _norm(text)
        quotes: Dict[str, str] = {}
        for q in ex.quotes:
            quotes.setdefault(q.field, q.quote)

        values: List[ExtractedValue] = []
        rejected: List[RejectedValue] = []
        for field, path in FIELD_PATHS.items():
            val = getattr(ex, field)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            quote = quotes.get(field)
            if not quote or _norm(quote) not in norm_text:
                rejected.append(RejectedValue(field=path, reason="not found word-for-word in your text"))
                continue
            if field in _CATEGORICAL:
                if val not in _CATEGORICAL[field]:
                    rejected.append(RejectedValue(field=path, reason=f"'{val}' is not a recognised option"))
                    continue
            elif field not in _TEXT_FIELDS:
                if not re.search(r"\d", quote) and not (field in _ZERO_OK and _WORD_ANGLES.get(_norm(quote)) == val):
                    rejected.append(RejectedValue(field=path, reason="no number in the quoted words"))
                    continue
                if not isinstance(val, (int, float)) or val < 0 or (val == 0 and field not in _ZERO_OK):
                    rejected.append(RejectedValue(field=path, reason=f"value {val} is not valid"))
                    continue
                if field in _FRACTIONS and val > 1.5:
                    rejected.append(RejectedValue(field=path, reason=f"value {val} is out of range"))
                    continue
            values.append(ExtractedValue(path=path, value=val, quote=quote))

        clar = list(ex.clarifications or [])
        as_written = ex.machine_as_written if ex.machine_as_written and _norm(ex.machine_as_written) in norm_text else None
        unsupported = ex.unsupported_machine if ex.unsupported_machine and _norm(ex.unsupported_machine) in norm_text else None
        unsupported_msg = _unsupported_message(unsupported) if unsupported else None
        if rejected:
            clar.append("Some values could not be confirmed from your text and were not filled in.")
        if not values and not clar and not unsupported:
            clar.append("No values were recognised. Try including the machine type, part size or weight, "
                        "speed with units (e.g. 0.5 m/s), and hours per day.")
        status = "NOTHING_FOUND" if not values else ("NEEDS_CLARIFICATION" if clar else "PARSED")
        if unsupported and not any(v.path == "application" for v in values):
            status = "UNSUPPORTED_MACHINE"
        return SizingParseResult(parser_status=status, provider=self.name, values=values,
                                 rejected=rejected, clarifications=clar, machine_as_written=as_written,
                                 unsupported_machine=unsupported, unsupported_message=unsupported_msg,
                                 machine_explanation=(ex.machine_explanation or None) if as_written or values else None)


# ─────────────────────────────────────────────────────────────
# Mock (deterministic, rule-based) provider — default, no key needed
# ─────────────────────────────────────────────────────────────

_N = r"(\d+(?:\.\d+)?)"
_LEN = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


# Names people use for the six supported motions (order = priority when several match)
_MACHINE_NAMES = [
    ("screw_axis", r"\b(?:ball ?screw|lead ?screw|screw ?jack|screw[- ](?:drive|axis|actuator)|linear actuator|electric cylinder|linear (?:axis|slide|module|stage))\b"),
    ("rack_pinion_axis", r"\b(?:rack(?: and| ?&) ?pinion|gantry|(?:belt[- ]driven|toothed[- ]belt|timing[- ]belt) (?:axis|actuator|slide|module)|linear belt)\b"),
    ("rotary_table", r"\b(?:turn ?table|rotary (?:table|indexer|platform)|index(?:ing)? table|indexer|rotating (?:table|platform)|dial table|carousel)\b"),
    ("winding", r"\b(?:(?:un|re)?wind(?:ing|er)|reel(?:er)?|spool(?:er|ing)?|coiler|take[- ]up roll)\b"),
    ("hoist", r"\b(?:hoist|winch|crane|lift(?:ing|er)?|elevator|vertical lift)\b"),
    ("conveyor", r"\b(?:conveyor|belt feeder|feeder belt|roller (?:table|line|bed)|transfer belt|belt line|(?:in|out)feed belt|accumulation table)\b"),
]

_MOTION_EXPLANATION = {
    "conveyor": "moves a load along a belt, rollers or a surface, so it is calculated as a conveyor.",
    "hoist": "raises a load vertically, so it is calculated as a lift / hoist.",
    "rotary_table": "rotates a table or mass about an axis, so it is calculated as a turntable / indexer.",
    "screw_axis": "moves a load in a straight line with a screw, so it is calculated as a screw-driven axis.",
    "rack_pinion_axis": "moves a load in a straight line with a rack & pinion or toothed belt, so it is calculated as that kind of axis.",
    "winding": "winds material onto or off a roll under tension, so it is calculated as a winder.",
}

# Things that are not one of the supported motions (checked first)
_UNSUPPORTED = (r"\b(?:bucket elevators?|screw conveyors?|augers?|bearings?|pumps?|fans?|blowers?|compressors?|mixers?|"
                r"agitators?|crushers?|grinders?|extruders?|presses|press|punch(?:es)?|shredders?|vehicles?|carts?|trolleys?)\b")


def _unsupported_message(name: str) -> str:
    if re.search(r"bearing", name, re.IGNORECASE):
        return ("A bearing is a part, not a machine the motor drives. Use the 'Bearing Life' tab to check a bearing's "
                "life (ISO 281). To size the motor, describe the machine the bearing sits in.")
    return (f"A '{name}' can't be sized here yet — it needs its own engineering formulas, which haven't been added. "
            f"Supported: conveyor, lift/hoist, turntable/indexer, screw axis, rack & pinion / belt axis, winding. "
            f"If you already know the torque and speed, use the 'Advanced: Torque & RPM' tab.")


class MockSizingParser(SizingRequirementParser):
    """Rule-based extraction of explicitly written values. Covers common phrasings only."""
    name = "mock"

    def extract(self, text: str) -> SizingExtraction:
        self._text = text
        self._work = text          # spans already used are blanked out here
        self._out: Dict[str, Any] = {}
        self._quotes: List[FieldQuote] = []
        self._clar: List[str] = []
        self._application()
        self._material()
        self._machine_dimensions()
        self._part()
        self._motion()
        self._duty()
        needs_density = self._out.get("application") == "winding" or "part_mass_kg" not in self._out
        if "material_name" in self._out and "density_kg_m3" not in self._out and needs_density:
            self._clar.append(f"What is the density of {self._out['material_name']}? It is not guessed — "
                              f"please take it from the material datasheet.")
        return SizingExtraction(**self._out, quotes=self._quotes, clarifications=self._clar)

    # helpers
    def _find(self, pattern: str):
        return re.search(pattern, self._work, re.IGNORECASE)

    def _set(self, field: str, value, m: re.Match, consume: bool = True):
        if field in self._out:
            return
        self._out[field] = value
        self._quotes.append(FieldQuote(field=field, quote=self._text[m.start():m.end()]))
        if consume:
            self._work = self._work[:m.start()] + " " * (m.end() - m.start()) + self._work[m.end():]

    def _try(self, field: str, patterns: List[str], conv=float, consume: bool = True) -> bool:
        for p in patterns:
            m = self._find(p)
            if m:
                self._set(field, conv(m), m, consume)
                return True
        return False

    @staticmethod
    def _mm(m: re.Match, i: int = 1, u: int = 2) -> float:
        return float(m.group(i)) * _LEN[m.group(u).lower()]

    # sections
    def _application(self):
        # Unsupported machines first, so e.g. "bucket elevator" or "screw conveyor" is not
        # mistaken for a hoist or conveyor.
        m = re.search(_UNSUPPORTED, self._text, re.IGNORECASE)
        masked = self._text
        if m:
            self._out["unsupported_machine"] = m.group(0)
            masked = self._text[:m.start()] + " " * (m.end() - m.start()) + self._text[m.end():]
        found: List[Tuple[int, str, re.Match]] = []
        for app, pat in _MACHINE_NAMES:
            mm = re.search(pat, masked, re.IGNORECASE)
            if mm:
                found.append((mm.start(), app, mm))
        if not found:
            return
        found.sort(key=lambda x: x[0])
        _, app, mm = found[0]
        self._out["application"] = app
        self._out["machine_as_written"] = mm.group(0)
        self._out["machine_explanation"] = f"'{mm.group(0)}' {_MOTION_EXPLANATION[app]}"
        self._quotes.append(FieldQuote(field="application", quote=mm.group(0)))
        if re.fullmatch(r"linear (?:axis|slide|module|stage)", mm.group(0), re.IGNORECASE):
            self._clar.append(f"'{mm.group(0)}' was treated as a screw-driven axis. "
                              f"If it is driven by a rack & pinion or a toothed belt, change the machine type.")
        if len({a for _, a, _ in found}) > 1:
            others = sorted({a for _, a, _ in found} - {app})
            self._clar.append(f"Your text mentions more than one machine type; '{app}' was chosen "
                              f"(also mentioned: {', '.join(others)}). Please check.")

    def _material(self):
        self._try("density_kg_m3", [_N + r"\s*(?:kg/m3|kg/m³|kg per cubic met(?:er|re))"], lambda m: float(m.group(1)))
        self._try("density_kg_m3", [_N + r"\s*(?:g/cm3|g/cm³|g/cc)"], lambda m: float(m.group(1)) * 1000)
        m = self._find(r"shore\s*([ad])\s*" + _N) or self._find(_N + r"\s*shore\s*([ad])\b")
        if m:
            scale_grp, val_grp = (1, 2) if m.group(1).isalpha() else (2, 1)
            self._set("hardness_value", float(m.group(val_grp)), m, consume=False)
            self._set("hardness_scale", f"Shore {m.group(scale_grp).upper()}", m)
        stop = r"(?!(?:around|at|on|with|and|in|for|of|to|density|blocks?|parts?|each|weighing)\b)"
        self._try("material_name", [r"(?:made of|made from|material(?: is|:)?)\s+(" + stop + r"[a-z][a-z\-]*(?:\s+" + stop + r"[a-z][a-z\-]*)?)"],
                  lambda m: m.group(1).strip(), consume=False)
        if "material_name" in self._out:
            # quote must be just the material words
            self._quotes[-1] = FieldQuote(field="material_name", quote=self._out["material_name"])

    def _machine_dimensions(self):
        L = r"\s*(mm|cm|m)\b"
        self._try("core_diameter_mm", [r"core\s*(?:diameter|dia\.?|of|is|:|ø)*\s*" + _N + L, _N + L + r"\s*core"], self._mm)
        self._try("full_roll_diameter_mm", [r"(?:full[- ]roll|roll|max(?:imum)?)\s*(?:diameter|dia\.?)\s*(?:of|is|:)?\s*" + _N + L,
                                            r"full[- ]roll\s*(?:of|is|:)?\s*" + _N + L, _N + L + r"\s*(?:full\s+)?roll"], self._mm)
        self._try("roll_width_mm", [r"(?:roll\s+)?width\s*(?:of|is|:)?\s*" + _N + L, _N + L + r"\s*wide"], self._mm)
        self._try("drum_diameter_mm", [r"drum\s*(?:diameter|dia\.?|of|is|:|ø)*\s*" + _N + L, _N + L + r"\s*(?:diameter\s+)?drum"], self._mm)
        if self._out.get("application") == "rack_pinion_axis":
            self._try("pinion_diameter_mm", [r"(?:pinion|pulley)\s*(?:pitch\s*)?(?:diameter|dia\.?|of|is|:|ø)*\s*" + _N + L,
                                             _N + L + r"\s*(?:pitch\s+)?(?:pinion|pulley)"], self._mm)
        self._try("drive_diameter_mm", [r"(?:pulley|roller|sprocket)\s*(?:diameter|dia\.?|of|is|:|ø)*\s*" + _N + L,
                                        _N + L + r"\s*(?:diameter\s+)?(?:drive\s+)?(?:pulley|roller|sprocket)"], self._mm)
        self._try("load_radius_mm", [r"(?:radius|pitch circle radius)\s*(?:of|is|:)?\s*" + _N + L, _N + L + r"\s*radius"], self._mm)
        self._try("screw_lead_mm", [r"lead\s*(?:of|is|:)?\s*" + _N + r"\s*mm", _N + r"\s*mm\s*lead"], lambda m: float(m.group(1)))

    def _part(self):
        L = r"\s*(mm|cm|m)\b"
        m = self._find(_N + r"\s*(?:mm|cm|m)?\s*[x×*]\s*" + _N + r"\s*(?:mm|cm|m)?\s*[x×*]\s*" + _N + L)
        if m:
            f = _LEN[m.group(4).lower()]
            self._set("part_shape", "block", m, consume=False)
            self._set("length_mm", float(m.group(1)) * f, m, consume=False)
            self._set("width_mm", float(m.group(2)) * f, m, consume=False)
            self._set("height_mm", float(m.group(3)) * f, m)
        if re.search(r"\b(?:tube|pipe)s?\b", self._work, re.IGNORECASE):
            if self._try("outer_diameter_mm", [r"(?:od|outer diameter|outside diameter)\s*(?:of|is|:)?\s*" + _N + L], self._mm):
                self._out.setdefault("part_shape", "tube")
                self._quotes.append(FieldQuote(field="part_shape", quote=self._quotes[-1].quote))
            self._try("inner_diameter_mm", [r"(?:id|inner diameter|inside diameter)\s*(?:of|is|:)?\s*" + _N + L], self._mm)
        shape_word = re.search(r"\b(rod|bar|cylinder|shaft|ball|sphere)s?\b", self._work, re.IGNORECASE)
        if shape_word and "part_shape" not in self._out:
            if self._try("diameter_mm", [r"(?:ø|dia(?:meter)?\.?)\s*(?:of|is|:)?\s*" + _N + L, _N + L + r"\s*(?:dia(?:meter)?\b|ø)"], self._mm):
                shape = "sphere" if shape_word.group(1).lower() in ("ball", "sphere") else "cylinder"
                self._out["part_shape"] = shape
                self._quotes.append(FieldQuote(field="part_shape", quote=shape_word.group(0)))
        if self._out.get("part_shape") in ("cylinder", "tube"):
            self._try("length_mm", [r"(?:length|long)\s*(?:of|is|:)?\s*" + _N + L, _N + L + r"\s*long"], self._mm)
        if self._try("volume_cm3", [r"(?:volume\s*(?:of|is|:)?\s*)?" + _N + r"\s*(?:cm3|cm³|cc)\b"], lambda m: float(m.group(1))):
            self._out.setdefault("part_shape", "volume")
            if self._out["part_shape"] == "volume":
                self._quotes.append(FieldQuote(field="part_shape", quote=self._quotes[-1].quote))

        kg = r"\s*(kg|g|t|tonnes?)\b"
        def conv(m):
            unit = m.group(2).lower()
            return float(m.group(1)) * (1000.0 if unit.startswith("t") else 0.001 if unit == "g" else 1.0)
        self._try("counterweight_kg", [r"counter ?weight\s*(?:of|is|:)?\s*" + _N + kg, _N + kg + r"\s*counter ?weight"], conv)
        self._try("belt_mass_kg", [r"belt\s*(?:mass|weight|weighs)\s*(?:of|is|:)?\s*" + _N + kg, _N + kg + r"\s*belt"], conv)
        self._try("carrier_mass_kg", [r"(?:pallet|fixture|carriage|tray|nest)s?\s*(?:mass|weight|weighs|weighing|of)\s*(?:of|is|:)?\s*" + _N + kg,
                                      _N + kg + r"\s*(?:pallet|fixture|carriage|tray|nest)"], conv)
        if self._try("part_mass_kg", [_N + kg + r"\s*(?:each|per part|per piece|apiece)",
                                      r"(?:each|part|block|box|piece|item)\w*\s+(?:weighs|weighing|of|is)\s+" + _N + kg,
                                      r"(?:load|payload|weight|mass)\s*(?:of|is|:)?\s*" + _N + kg,
                                      _N + kg + r"\s*(?:load|payload|weight|mass)"], conv):
            if "part_shape" not in self._out:
                self._out["part_shape"] = "mass"
                self._quotes.append(FieldQuote(field="part_shape", quote=self._quotes[-1].quote))
        self._try("quantity", [r"\b(\d+)\s*(?:x\s+)?(?:[a-z\-]+\s+){0,2}?(?:parts|pieces|pcs|blocks|boxes|items|bottles|products|units|cartons|bars|rods|tubes|balls)\b"],
                  lambda m: int(m.group(1)))

    def _motion(self):
        app = self._out.get("application")
        spd = {"m/s": 1, "mm/s": 0.001, "m/min": 1 / 60}
        def sconv(m):
            u = m.group(2).lower().replace(" ", "")
            u = {"meterspersecond": "m/s", "metrespersecond": "m/s", "mpermin": "m/min", "mperminute": "m/min",
                 "meterperminute": "m/min", "metersperminute": "m/min", "metresperminute": "m/min"}.get(u, u)
            return round(float(m.group(1)) * spd[u], 6)
        self._try("speed_m_s", [_N + r"\s*(m/s|mm/s|m/min|m per min(?:ute)?|met(?:er|re)s? per second|met(?:er|re)s? per minute)"], sconv)
        sec = r"\s*(?:s|sec|secs|seconds?)\b"
        self._try("accel_time_s", [r"(?:accelerat\w*|ramp\w*(?: up)?|reach\w*\s+(?:full\s+|top\s+)?speed|start\w*(?: up)?|get\w* up to speed)[^.;]{0,30}?\b(?:in|within|over)\s+" + _N + sec,
                                   _N + sec + r"\s+(?:to\s+)?(?:accelerat\w*|ramp|reach|get up to)"], lambda m: float(m.group(1)))
        if app == "rotary_table":
            if self._find(r"\bindex\w*|\bsteps?\b"):
                m = self._find(r"\bindex\w*|\bsteps?\b")
                self._set("motion_mode", "index", m, consume=False)
                self._try("index_angle_deg", [_N + r"\s*(?:°|deg\w*)", r"(?:index|step)\w*\s*(?:of|by)?\s*" + _N + r"\s*(?:°|deg)"], lambda m: float(m.group(1)))
                self._try("index_time_s", [r"\b(?:in|within|takes?)\s+" + _N + sec], lambda m: float(m.group(1)))
            else:
                if self._try("target_speed_rpm", [_N + r"\s*(?:rpm|rev/min|r/min)\b"], lambda m: float(m.group(1))):
                    self._out.setdefault("motion_mode", "continuous")
                    self._quotes.append(FieldQuote(field="motion_mode", quote=self._quotes[-1].quote))
            m = self._find(r"(?:around|on) a (?:circle|ring)|\bat (?:a )?radius")
            if m:
                self._set("load_arrangement", "parts_at_radius", m, consume=False)
        deg = r"\s*(?:°|deg\w*)"
        if app == "conveyor":
            if not self._try("incline_deg", [r"(?:incline[d]?|slope[d]?|uphill|angle)\s*(?:of|at|is|:)?\s*" + _N + deg, _N + deg + r"\s*(?:incline|slope|uphill|angle)"], lambda m: float(m.group(1))):
                self._try("incline_deg", [r"\b(?:flat|horizontal|level)\b"], lambda m: 0.0, consume=False)
        if app in ("screw_axis", "rack_pinion_axis"):
            if not self._try("axis_angle_deg", [r"(?:angle|inclined|tilted)\s*(?:of|at|is|:)?\s*" + _N + deg, _N + deg + r"\s*(?:angle|incline)"], lambda m: float(m.group(1))):
                if not self._try("axis_angle_deg", [r"\bvertical(?:ly)?\b"], lambda m: 90.0, consume=False):
                    self._try("axis_angle_deg", [r"\bhorizontal(?:ly)?\b"], lambda m: 0.0, consume=False)
        fric_field = "guide_friction" if app in ("screw_axis", "rack_pinion_axis") else "friction_coefficient"
        self._try(fric_field, [r"(?:coefficient of friction|friction coefficient|friction|μ|mu)\s*(?:of|is|=|:)?\s*" + _N], lambda m: float(m.group(1)))
        def eff(m):
            v = float(m.group(1))
            return v / 100 if (m.group(2) or v > 1.5) else v
        eff_field = {"screw_axis": "screw_efficiency", "hoist": "rope_efficiency"}.get(app, "drive_efficiency")
        self._try(eff_field, [r"efficien\w*\s*(?:of|is|=|:)?\s*" + _N + r"\s*(%)?", _N + r"\s*(%)?\s*efficien"], eff)
        self._try("rope_falls", [r"\b(\d+)\s*(?:rope\s+)?falls?\b"], lambda m: int(m.group(1)))
        self._try("web_tension_n", [_N + r"\s*N\s*(?:of\s+)?(?:web\s+)?tension", r"tension\s*(?:of|is|:)?\s*" + _N + r"\s*N\b"], lambda m: float(m.group(1)))
        self._try("process_force_n", [_N + r"\s*N\s*(?:of\s+)?(?:process|pressing|press|cutting|push(?:ing)?)\s*force",
                                      r"(?:process|pressing|press|cutting|push(?:ing)?)\s*force\s*(?:of|is|:)?\s*" + _N + r"\s*N\b"], lambda m: float(m.group(1)))

    def _duty(self):
        self._try("hours_per_day", [_N + r"\s*(?:h|hrs?|hours?)\s*(?:a|per|/|each)\s*day", r"\b24/7\b"],
                  lambda m: 24.0 if m.group(0) == "24/7" else float(m.group(1)))
        self._try("load_class", [r"heavy (?:shocks?|impacts?)|severe shocks?|\bjam(?:s|ming)?\b"], lambda m: "heavy", consume=False)
        self._try("load_class", [r"(?:moderate|some|light|occasional) (?:shocks?|impacts?|bumps?)|frequent (?:starts?|stops?)"], lambda m: "moderate", consume=False)
        self._try("load_class", [r"\bsmooth(?:ly)?\b|\buniform\b|\bsteady\b|constant load"], lambda m: "uniform", consume=False)
        self._try("service_factor_override", [r"service factor\s*(?:of|is|=|:)?\s*" + _N, r"\bSF\s*(?:=|:)?\s*" + _N], lambda m: float(m.group(1)))
        sec = r"\s*(?:s|sec|secs|seconds?)\b"
        self._try("run_time_s", [r"\bruns?\s*(?:for)?\s*" + _N + sec], lambda m: float(m.group(1)))
        self._try("dwell_time_s", [r"(?:stops?|pauses?|dwells?|waits?|rests?)\s*(?:for)?\s*" + _N + sec], lambda m: float(m.group(1)))
        self._try("max_voltage_v", [_N + r"\s*(?:v|volts?|vdc|vac)\b"], lambda m: float(m.group(1)))


# ─────────────────────────────────────────────────────────────
# Real providers (structured output, same SDKs as Stage 7.2)
# ─────────────────────────────────────────────────────────────

class GeminiSizingParser(SizingRequirementParser):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    def extract(self, text: str) -> SizingExtraction:
        if not self._api_key:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "GEMINI_API_KEY is missing — the text reader is unavailable. Please fill the form by hand.")
        from app.ai import gemini_parser as gp
        if not gp._GENAI_AVAILABLE:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "google-genai SDK is not installed.")
        client = gp.genai.Client(api_key=self._api_key)
        resp = client.models.generate_content(
            model=self._model, contents=text,
            config=gp.genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION, response_mime_type="application/json",
                response_schema=SizingExtraction, temperature=0.0),
        )
        if getattr(resp, "parsed", None) is not None:
            return resp.parsed
        import json
        return SizingExtraction(**json.loads(resp.text or "{}"))


class OpenAISizingParser(SizingRequirementParser):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def extract(self, text: str) -> SizingExtraction:
        if not self._api_key:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "OPENAI_API_KEY is missing — the text reader is unavailable. Please fill the form by hand.")
        from app.ai import openai_parser as op
        if not op._OPENAI_AVAILABLE:
            raise ProviderError("ERROR_CONFIGURATION_MISSING", "openai SDK is not installed.")
        client = op.OpenAI(api_key=self._api_key)
        resp = client.responses.parse(
            model=self._model,
            input=[{"role": "system", "content": SYSTEM_INSTRUCTION}, {"role": "user", "content": text}],
            text_format=SizingExtraction,
        )
        return resp.output_parsed


def get_sizing_parser() -> SizingRequirementParser:
    provider = os.environ.get("AI_PROVIDER", "mock").strip().lower()
    if provider == "gemini":
        return GeminiSizingParser()
    if provider == "openai":
        return OpenAISizingParser()
    if provider == "mock":
        return MockSizingParser()
    raise RuntimeError(f"Unknown AI_PROVIDER '{provider}'. Supported values: mock, openai, gemini")
