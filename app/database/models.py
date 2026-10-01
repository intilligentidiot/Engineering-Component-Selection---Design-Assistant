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
DATA_STATUS_STALE                = "STALE"              # Cached but past freshness threshold


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


class DiscoveredComponent(Base):
    __tablename__ = "discovered_components"

    id                   = Column(Integer, primary_key=True, index=True)
    component_type       = Column(String)   # "motor", "gearbox", or "combination"
    search_query         = Column(String, index=True)
    source               = Column(String)   # provider / source name
    source_type          = Column(String, default="INTERNET")
    manufacturer         = Column(String)
    product_name         = Column(String)
    model                = Column(String, nullable=True)
    part_number          = Column(String, index=True, nullable=True)
    product_url          = Column(String, nullable=True)
    datasheet_url        = Column(String, nullable=True)
    image_url            = Column(String, nullable=True)

    # Key structured specs for deterministic engine evaluation
    voltage_v            = Column(Float, nullable=True)
    power_w              = Column(Float, nullable=True)
    nominal_speed_rpm    = Column(Float, nullable=True)
    nominal_torque_nm    = Column(Float, nullable=True)
    gear_ratio           = Column(Float, nullable=True)
    efficiency           = Column(Float, nullable=True)
    max_input_speed_rpm  = Column(Float, nullable=True)
    max_output_torque_nm = Column(Float, nullable=True)

    # Additional specs as JSON string if needed
    specifications_json  = Column(String, nullable=True)

    # Availability fields
    availability_status  = Column(String, default="AVAILABILITY_NOT_CONFIRMED") # IN_STOCK, OUT_OF_STOCK, AVAILABILITY_NOT_CONFIRMED, DISCONTINUED
    availability_source  = Column(String, nullable=True)
    availability_checked_at = Column(String, nullable=True)

    # Commercial fields
    price                = Column(Float, nullable=True)
    price_currency       = Column(String, nullable=True)
    price_source         = Column(String, nullable=True)
    price_checked_at     = Column(String, nullable=True)

    # CAD fields
    cad_available        = Column(String, default="False") # "True" or "False"
    cad_url              = Column(String, nullable=True)

    # Verification / Status
    data_status          = Column(String, default=DATA_STATUS_DISCOVERED)
    discovered_at        = Column(String)
    last_checked_at      = Column(String)


class DiscoverySearchCache(Base):
    """
    Stage 6.1 — Search Query Cache.

    Stores one row per unique engineering query fingerprint.  When the same
    (or sufficiently similar) requirement is searched again within the
    freshness window, the cached result set is re-used instead of calling
    SerpApi again.

    Fingerprint strategy:
        SHA-256( canonical_query_string )  where the canonical string is
        built from rounded engineering parameters so that minor float
        differences collapse to the same cache key.

    Freshness policy (per ARCHITECTURE.md):
        - specs / engineering data  : 90 days
        - price / availability data : 1 day
    The cache row tracks both timestamps separately so the caller can decide
    whether a partial refresh (price only) is required without discarding
    the full spec set.
    """
    __tablename__ = "discovery_search_cache"

    id                     = Column(Integer, primary_key=True, index=True)

    # The SHA-256 fingerprint of the canonical query parameters.
    # Indexed for fast exact-match lookups.
    query_fingerprint      = Column(String, unique=True, index=True, nullable=False)

    # Human-readable version of the query (for debugging / admin views).
    query_text             = Column(String, nullable=False)

    # Serialised JSON list of the raw product records returned by the provider.
    # We re-run the deterministic engine on retrieval, so we store *raw* data
    # (pre-evaluation), not computed results.
    results_json           = Column(String, nullable=False)  # JSON array string

    # Which provider produced this result set ("SerpApi", "Mock", …).
    provider               = Column(String, nullable=True)

    # Timestamps stored as ISO-8601 UTC strings to match the rest of the schema.
    # specs_cached_at  — last time engineering specs were refreshed.
    # prices_cached_at — last time price/availability was refreshed.
    specs_cached_at        = Column(String, nullable=False)
    prices_cached_at       = Column(String, nullable=True)

    # Hit counter — useful for future analytics / eviction policies.
    hit_count              = Column(Integer, default=0)

