from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from app.database.database import Base

# ── Data Status Constants ───────────────────────────────────────────────────
# These statuses apply to BOTH Source A (local) and future Source B (internet).
# See ARCHITECTURE.md for the full dual-source contract.
DATA_STATUS_ENGINEERING_VERIFIED = "ENGINEERING_VERIFIED"
DATA_STATUS_SOURCE_VERIFIED      = "SOURCE_VERIFIED"
DATA_STATUS_DISCOVERED           = "DISCOVERED"         # Internet-discovered, not yet checked
DATA_STATUS_DATA_INCOMPLETE      = "DATA_INCOMPLETE"    # Missing required fields


class Manufacturer(Base):
    __tablename__ = "manufacturers"

    id      = Column(Integer, primary_key=True, index=True)
    name    = Column(String, unique=True, index=True)
    website = Column(String, nullable=True)

    motors    = relationship("Motor",   back_populates="manufacturer")
    gearboxes = relationship("Gearbox", back_populates="manufacturer")


class Motor(Base):
    __tablename__ = "motors"

    id                  = Column(Integer, primary_key=True, index=True)
    manufacturer_id     = Column(Integer, ForeignKey("manufacturers.id"))
    part_number         = Column(String, unique=True, index=True)
    voltage_v           = Column(Float)
    continuous_power_w  = Column(Float)
    nominal_speed_rpm   = Column(Float)
    nominal_torque_nm   = Column(Float)
    max_torque_nm       = Column(Float,  nullable=True)

    # Data Provenance (Source A)
    source              = Column(String)
    source_url          = Column(String, nullable=True)
    verification_status = Column(String)   # kept for legacy compat
    verification_date   = Column(String)

    # ── Dual-source status field (Connection Point C) ──
    # Future Source B (internet-discovered) components will also use this field.
    data_status         = Column(String, default=DATA_STATUS_ENGINEERING_VERIFIED)

    manufacturer = relationship("Manufacturer", back_populates="motors")


class Gearbox(Base):
    __tablename__ = "gearboxes"

    id                   = Column(Integer, primary_key=True, index=True)
    manufacturer_id      = Column(Integer, ForeignKey("manufacturers.id"))
    part_number          = Column(String, unique=True, index=True)
    gear_ratio           = Column(Float)
    efficiency           = Column(Float)
    max_input_speed_rpm  = Column(Float, nullable=True)
    max_output_torque_nm = Column(Float)

    # Data Provenance (Source A)
    source               = Column(String)
    source_url           = Column(String, nullable=True)
    verification_status  = Column(String)   # kept for legacy compat
    verification_date    = Column(String)

    # ── Dual-source status field (Connection Point C) ──
    data_status          = Column(String, default=DATA_STATUS_ENGINEERING_VERIFIED)

    manufacturer = relationship("Manufacturer", back_populates="gearboxes")
