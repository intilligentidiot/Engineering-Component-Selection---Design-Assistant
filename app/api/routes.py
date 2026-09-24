from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from app.database.database import get_db
from app.database.models import Motor, Gearbox, Manufacturer
from app.engine.recommend import get_recommendations
from app.engine.trace import ValidationError

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

# ─────────────────────────────────────────────────────────────
# Existing endpoints
# ─────────────────────────────────────────────────────────────

@router.get("/status")
def api_status():
    return {"api": "operational"}

@router.post("/recommend")
def recommend(request: RecommendRequest, db: Session = Depends(get_db)):
    # Connection Point B: in a future stage, include_internet_results=False
    # will be a parameter here that triggers the discover.py module.
    try:
        results = get_recommendations(
            db=db,
            required_speed_rpm=request.required_speed_rpm,
            required_torque_nm=request.required_torque_nm,
            service_factor=request.service_factor,
            max_voltage_v=request.max_voltage_v,
            top_n=request.top_n
        )
        return {
            "status": "ok",
            "count": len(results),
            "inputs": request.model_dump(),
            "results": results
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
