from pydantic import BaseModel

# Placeholders for API schemas
class MotorBase(BaseModel):
    manufacturer: str
    model: str
    voltage: float
    power_w: float
