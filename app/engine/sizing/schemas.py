"""
Stage 8 — Application-based sizing: request / response schemas.

All user-facing inputs use practical units (mm, m/s, deg, kg, N); the sizing
models convert to SI internally and show every conversion in the trace.
See docs/STAGE_8_APPLICATION_SIZING_SPEC.md.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

ApplicationType = Literal[
    "conveyor",
    "hoist",
    "rotary_table",
    "screw_axis",
    "rack_pinion_axis",
    "winding",
]

PartShape = Literal["block", "cylinder", "tube", "sphere", "volume", "mass"]

LoadClass = Literal["uniform", "moderate", "heavy"]


class MaterialInput(BaseModel):
    name: Optional[str] = None
    density_kg_m3: Optional[float] = None
    # Recorded and shown, never used in an equation (spec §2.2)
    hardness_scale: Optional[str] = None
    hardness_value: Optional[float] = None


class PartInput(BaseModel):
    shape: Optional[PartShape] = None
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    diameter_mm: Optional[float] = None
    outer_diameter_mm: Optional[float] = None
    inner_diameter_mm: Optional[float] = None
    volume_cm3: Optional[float] = None
    mass_kg: Optional[float] = None
    quantity: int = Field(1, ge=1)
    carrier_mass_kg: Optional[float] = None


class ApplicationParams(BaseModel):
    # Shared motion inputs
    speed_m_s: Optional[float] = None
    accel_time_s: Optional[float] = None
    drive_efficiency: Optional[float] = None

    # Conveyor
    incline_deg: Optional[float] = None
    friction_coefficient: Optional[float] = None
    drive_diameter_mm: Optional[float] = None
    belt_mass_kg: Optional[float] = None
    extra_force_n: Optional[float] = None

    # Hoist
    drum_diameter_mm: Optional[float] = None
    rope_falls: Optional[int] = None
    rope_efficiency: Optional[float] = None
    hook_mass_kg: Optional[float] = None
    counterweight_kg: Optional[float] = None

    # Rotary table
    load_arrangement: Optional[Literal["solid_disc", "parts_at_radius", "custom_inertia"]] = None
    load_radius_mm: Optional[float] = None
    load_inertia_kg_m2: Optional[float] = None
    table_inertia_kg_m2: Optional[float] = None
    motion_mode: Optional[Literal["continuous", "index"]] = None
    target_speed_rpm: Optional[float] = None
    index_angle_deg: Optional[float] = None
    index_time_s: Optional[float] = None
    friction_torque_nm: Optional[float] = None

    # Linear axes (screw, rack & pinion / belt)
    axis_angle_deg: Optional[float] = None
    guide_friction: Optional[float] = None
    process_force_n: Optional[float] = None
    screw_lead_mm: Optional[float] = None
    screw_efficiency: Optional[float] = None
    screw_inertia_kg_m2: Optional[float] = None
    pinion_diameter_mm: Optional[float] = None

    # Winding
    web_tension_n: Optional[float] = None
    core_diameter_mm: Optional[float] = None
    full_roll_diameter_mm: Optional[float] = None
    roll_width_mm: Optional[float] = None
    core_inertia_kg_m2: Optional[float] = None


class DutyInput(BaseModel):
    load_class: Optional[LoadClass] = None
    hours_per_day: Optional[float] = None
    service_factor_override: Optional[float] = None
    # Optional repeating cycle — enables RMS torque (spec §4.1)
    run_time_s: Optional[float] = None
    dwell_time_s: Optional[float] = None


class SizingRequest(BaseModel):
    application: ApplicationType
    material: MaterialInput = MaterialInput()
    part: PartInput = PartInput()
    params: ApplicationParams = ApplicationParams()
    duty: DutyInput = DutyInput()


class StepInput(BaseModel):
    value: Any
    unit: str
    origin: str  # USER | DEFAULT | CONSTANT | DERIVED


class SizingStep(BaseModel):
    key: str
    label: str
    formula: str
    substitution: str
    result: float
    unit: str
    inputs: Dict[str, StepInput] = {}
    note: Optional[str] = None


class MissingInput(BaseModel):
    field: str
    label: str


class OperatingPoint(BaseModel):
    label: str
    speed_rpm: float
    run_torque_nm: float
    peak_torque_nm: float


class SizedRequirement(BaseModel):
    required_speed_rpm: float
    required_torque_nm: float      # continuous (RMS or run), before service factor
    peak_torque_nm: float          # acceleration peak, before service factor
    service_factor: float
    design_torque_nm: float        # continuous × SF
    design_peak_torque_nm: float   # peak × SF
    required_power_w: float        # design torque × ω


class SizingResult(BaseModel):
    status: Literal["SIZED", "REQUIREMENTS_INCOMPLETE", "INVALID_INPUT"]
    application: str
    missing_inputs: List[MissingInput] = []
    errors: List[str] = []
    steps: List[SizingStep] = []
    operating_points: List[OperatingPoint] = []
    requirement: Optional[SizedRequirement] = None
    assumptions: List[str] = []
    warnings: List[str] = []
    material_notes: List[str] = []
    defaults_version: str = ""
