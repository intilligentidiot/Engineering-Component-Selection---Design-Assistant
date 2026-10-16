from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from app.database.database import get_db
from app.database.models import Motor, Gearbox, Manufacturer
from app.engine.recommend import get_recommendations
from app.engine.trace import ValidationError
from app.engine.sizing import size_application, SizingRequest
from app.engine.bearing import bearing_life, BearingRequest
from app.engine.method_eval import MethodPlan, evaluate_method
from app.engine.project import ProjectPlan, evaluate_project

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# Pydantic response schemas
# ─────────────────────────────────────────────────────────────

class ManufacturerOut(BaseModel):
    id: int
    name: str
    website: Optional[str]
    model_config = {"from_attributes": True}

class MotorOut(BaseModel):
    id: int
    part_number: str
    manufacturer: ManufacturerOut
    voltage_v: float
    continuous_power_w: float
    nominal_speed_rpm: float
    nominal_torque_nm: float
    max_torque_nm: Optional[float]
    source: str
    source_url: Optional[str]
    data_status: str
    verification_date: str
    model_config = {"from_attributes": True}

class GearboxOut(BaseModel):
    id: int
    part_number: str
    manufacturer: ManufacturerOut
    gear_ratio: float
    efficiency: float
    max_input_speed_rpm: Optional[float]
    max_output_torque_nm: float
    source: str
    source_url: Optional[str]
    data_status: str
    verification_date: str
    model_config = {"from_attributes": True}

class RecommendRequest(BaseModel):
    required_speed_rpm: float = Field(..., gt=0, description="Required output speed in RPM")
    required_torque_nm: float = Field(..., gt=0, description="Required output torque in Nm")
    service_factor: float     = Field(1.0,  gt=0, description="Service factor (default 1.0)")
    max_voltage_v: float      = Field(..., gt=0, description="Maximum motor voltage in Volts")
    top_n: int                = Field(5, ge=1, le=20)
    include_internet_results: bool = Field(False, description="Enable Source B Internet Discovery search")
    # Stage 8 (optional): peak torque before service factor, and allowed over-speed in %
    peak_torque_nm: Optional[float] = Field(None, gt=0, description="Peak (acceleration) torque in Nm, before service factor")
    speed_tolerance_pct: Optional[float] = Field(None, ge=0, le=200, description="Allowed over-speed vs required speed (%)")

# ─────────────────────────────────────────────────────────────
# Existing endpoints
# ─────────────────────────────────────────────────────────────

class ParseRequirementsRequest(BaseModel):
    text: str

@router.post("/parse-requirements")
def parse_requirements(request: ParseRequirementsRequest):
    from app.ai.provider import get_parser
    parser = get_parser()
    result = parser.parse(request.text)
    return result.model_dump()

@router.post("/parse-sizing")
def parse_sizing(request: ParseRequirementsRequest):
    """
    Stage 8.x: read a plain-text description and return values for the sizing form.
    Every value carries the user's own words as evidence; the user confirms them
    in the form before anything is calculated.
    """
    from app.ai.sizing_parser import get_sizing_parser
    return get_sizing_parser().parse(request.text).model_dump()

@router.post("/ask")
def ask_question(request: ParseRequirementsRequest):
    """
    One entry point for any engineering question: decides the kind of calculation
    (motor sizing, bearing life, or an AI-chosen method for other topics) and reads
    the values the user wrote. Never returns calculated results.
    """
    from app.ai.assistant import ask
    return ask(request.text).model_dump()


class EvaluateMethodRequest(BaseModel):
    plan: MethodPlan
    values: dict = {}


@router.post("/evaluate-method")
def evaluate_method_route(request: EvaluateMethodRequest):
    """Deterministically evaluates an AI-chosen method from the engineer's values."""
    return evaluate_method(request.plan, request.values).model_dump()

class EvaluateProjectRequest(BaseModel):
    plan: ProjectPlan
    values: dict = {}
    include_internet: bool = False


@router.post("/project-evaluate")
def evaluate_project_route(request: EvaluateProjectRequest, db: Session = Depends(get_db)):
    """Runs every calculation of a project plan in order; missing information is reported per step."""
    return evaluate_project(request.plan, request.values, db, request.include_internet).model_dump()

@router.post("/bearing-life")
def bearing_life_check(request: BearingRequest):
    """ISO 281 basic rating life: life from the catalogue rating, or the minimum rating for a required life."""
    return bearing_life(request).model_dump()

@router.post("/size")
def size(request: SizingRequest):
    """
    Stage 8: application-based sizing. Turns material + part + application + motion
    inputs into the output-shaft requirement, with the full calculation proof.
    Does not select components — feed `requirement` into /api/recommend.
    """
    return size_application(request).model_dump()

@router.get("/status")
def api_status():
    return {"api": "operational"}

@router.post("/recommend")
def recommend(request: RecommendRequest, db: Session = Depends(get_db)):
    try:
        # Source A: Verified Local Database
        local_results = get_recommendations(
            db=db,
            required_speed_rpm=request.required_speed_rpm,
            required_torque_nm=request.required_torque_nm,
            service_factor=request.service_factor,
            max_voltage_v=request.max_voltage_v,
            top_n=request.top_n,
            peak_torque_nm=request.peak_torque_nm,
            speed_tolerance_pct=request.speed_tolerance_pct,
        )

        for res in local_results:
            res["source_type"] = "LOCAL"

        internet_results = []
        discovery_status = "NOT_REQUESTED"

        # Source B: Internet Discovery (only if explicitly enabled)
        if request.include_internet_results:
            import os
            try:
                from app.engine.discover import discover_and_evaluate_components
                internet_results = discover_and_evaluate_components(
                    db=db,
                    required_speed_rpm=request.required_speed_rpm,
                    required_torque_nm=request.required_torque_nm,
                    service_factor=request.service_factor,
                    max_voltage_v=request.max_voltage_v,
                    top_n=request.top_n,
                    peak_torque_nm=request.peak_torque_nm,
                    speed_tolerance_pct=request.speed_tolerance_pct,
                )

                # ── Stage 6.1: Determine cache vs live status ────────────────────────────────
                any_cache_hit = any(r.get("cache_hit") for r in internet_results)
                if any_cache_hit:
                    discovery_status = "COMPLETED_FROM_CACHE"
                elif os.environ.get("SERPAPI_KEY"):
                    discovery_status = "COMPLETED_LIVE"
                else:
                    discovery_status = "COMPLETED_MOCK_FALLBACK"

            except ValueError as ve:
                discovery_status = "INTERNET_SEARCH_NOT_CONFIGURED"
            except Exception as ex:
                # Graceful failure: local search remains intact
                discovery_status = "INTERNET_SEARCH_UNAVAILABLE"
                print(f"Internet discovery search failure: {ex}")


        # Only count fully verified candidates that MEET requirements
        valid_internet_count = sum(1 for r in internet_results if r.get("engineering_status") == "MEETS")

        return {
            "status": "ok",
            "count": len(local_results),
            "internet_count": valid_internet_count,
            "discovery_status": discovery_status,
            "inputs": request.model_dump(),
            "results": local_results,
            "internet_results": internet_results
        }
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ─────────────────────────────────────────────────────────────
# Component Detail Endpoints (Stage 5 — Source A)
# ─────────────────────────────────────────────────────────────

@router.get("/manufacturers", response_model=List[ManufacturerOut])
def list_manufacturers(db: Session = Depends(get_db)):
    return db.query(Manufacturer).order_by(Manufacturer.name).all()

@router.get("/motors", response_model=List[MotorOut])
def list_motors(
    manufacturer_id: Optional[int] = None,
    max_voltage_v: Optional[float] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Motor)
    if manufacturer_id:
        q = q.filter(Motor.manufacturer_id == manufacturer_id)
    if max_voltage_v:
        q = q.filter(Motor.voltage_v <= max_voltage_v)
    return q.order_by(Motor.manufacturer_id, Motor.voltage_v).all()

@router.get("/motors/{motor_id}", response_model=MotorOut)
def get_motor(motor_id: int, db: Session = Depends(get_db)):
    motor = db.query(Motor).filter(Motor.id == motor_id).first()
    if not motor:
        raise HTTPException(status_code=404, detail="Motor not found")
    return motor

@router.get("/gearboxes", response_model=List[GearboxOut])
def list_gearboxes(
    manufacturer_id: Optional[int] = None,
    min_ratio: Optional[float] = None,
    max_ratio: Optional[float] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Gearbox)
    if manufacturer_id:
        q = q.filter(Gearbox.manufacturer_id == manufacturer_id)
    if min_ratio:
        q = q.filter(Gearbox.gear_ratio >= min_ratio)
    if max_ratio:
        q = q.filter(Gearbox.gear_ratio <= max_ratio)
    return q.order_by(Gearbox.manufacturer_id, Gearbox.gear_ratio).all()

@router.get("/gearboxes/{gearbox_id}", response_model=GearboxOut)
def get_gearbox(gearbox_id: int, db: Session = Depends(get_db)):
    gb = db.query(Gearbox).filter(Gearbox.id == gearbox_id).first()
    if not gb:
        raise HTTPException(status_code=404, detail="Gearbox not found")
    return gb
