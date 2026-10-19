# ARCHITECTURE.md — Dual-Source Component Data Contract

This document defines the architectural contract between the two data sources
used by the motor + gearbox selection step of the Tesla Mechanical Designs
Engineering Calculation Assistant.

It must be read before implementing the internet discovery module (Source B).

---

## Overview

The tool has two component data sources that coexist in the same dashboard:

| Source | Name | Status |
|--------|------|--------|
| **Source A** | Verified Local Database | ✅ Built (Stages 1–5) |
| **Source B** | Internet Discovery | 🔜 Future stage |

---

## Data Status Schema

Every component from either source carries one of these statuses:

| Constant | Value | Meaning |
|----------|-------|---------|
| `DATA_STATUS_ENGINEERING_VERIFIED` | `ENGINEERING_VERIFIED` | Specs confirmed from official datasheet and validated internally |
| `DATA_STATUS_SOURCE_VERIFIED` | `SOURCE_VERIFIED` | Specs sourced directly from manufacturer page, not yet cross-checked |
| `DATA_STATUS_DISCOVERED` | `DISCOVERED` | Found via internet search — specs must not be trusted for engineering decisions |
| `DATA_STATUS_DATA_INCOMPLETE` | `DATA_INCOMPLETE` | Some required fields are missing or unconfirmed |

**Enforcement rules (both sources):**
- Never fabricate missing specifications.
- Never infer availability when the source does not confirm it.
- Never claim suitability solely from search-result similarity.
- Engineering calculations always remain the basis for comparisons.

---

## Connection Points for Source B (Internet Discovery)

### Connection Point A — `app/engine/discover.py` (NEW FILE, not yet created)

```python
# Future module: app/engine/discover.py
#
# Responsibilities:
#   - Accept required power, torque, speed as inputs
#   - Construct structured search queries (e.g. "24V DC motor 120W gearbox")
#   - Call search APIs or scrape manufacturer/distributor sites
#   - Return a list of DiscoveredComponent dicts with:
#       - manufacturer, part_number, product_url, datasheet_url
#       - image_url, specs (dict), availability, price
#       - cad_available, cad_url
#       - data_status = "DISCOVERED"
#   - NEVER assign ENGINEERING_VERIFIED status — only human review can do that
#
def discover_components(required_power_w, required_torque_nm, required_speed_rpm):
    raise NotImplementedError("Internet Discovery module not yet implemented")
```

---

### Connection Point B — `app/api/routes.py` `/api/recommend` endpoint

The existing endpoint will gain an optional parameter when Source B is ready:

```python
class RecommendRequest(BaseModel):
    ...
    include_internet_results: bool = False  # ← ADD THIS when Source B is ready
```

When `include_internet_results=True`:
1. Run existing local DB search (Source A) → labelled `source_type: "LOCAL"`
2. Call `discover.py` (Source B) → labelled `source_type: "INTERNET"`
3. Run engineering math on all candidates
4. Return merged list, each item containing `source_type` and `data_status`

---

### Connection Point C — `app/database/models.py`

A new `DiscoveredComponent` table will be added to cache internet results:

```python
class DiscoveredComponent(Base):
    __tablename__ = "discovered_components"

    id                  = Column(Integer, primary_key=True)
    component_type      = Column(String)   # "motor" or "gearbox"
    search_query        = Column(String)
    manufacturer        = Column(String)
    part_number         = Column(String)
    product_url         = Column(String)
    datasheet_url       = Column(String, nullable=True)
    image_url           = Column(String, nullable=True)
    specs               = Column(String)   # JSON blob
    availability        = Column(String, nullable=True)
    price               = Column(String, nullable=True)
    cad_available       = Column(Boolean, default=False)
    cad_url             = Column(String, nullable=True)
    data_status         = Column(String, default="DISCOVERED")
    discovered_at       = Column(String)
    last_checked_at     = Column(String)
```

---

### Connection Point D — `static/js/main.js`

The results renderer already uses a `source_type` field structure.
When Source B is enabled, a new section will appear below local results:

```
── Source A: Verified Local Database ── (already built, green badge)
── Source B: Internet Discovery ──      (future, blue badge, DISCOVERED status)
```

Each Source B card will visually show:
- Product image (if available)
- `DISCOVERED` status badge in amber
- Manufacturer, part number, product URL, datasheet link
- Calculated performance comparison against engineering requirements
- CAD availability flag
- **NO recommendation rank** — internet results are informational only
  until a human promotes them to `SOURCE_VERIFIED` or higher

---

## Data Flow Diagram

```
User Requirements
      │
      ▼
Engineering Calculations (app/engine/)
      │
      ├──► Source A: Local DB Query (app/database/)
      │         └── Status: ENGINEERING_VERIFIED
      │
      └──► Source B: discover.py (future)
                └── Status: DISCOVERED
                      │
                      ▼
              Normalize & Compare
                      │
                      ▼
           Unified Dashboard Response
           (same UI, clearly labelled)
```

---

## Rules for Source B Implementation (future developer checklist)

- [ ] `data_status` must default to `DISCOVERED` for all internet-sourced components
- [ ] Promotion to `SOURCE_VERIFIED` requires a human to click "Verify Source" in the UI
- [ ] Promotion to `ENGINEERING_VERIFIED` requires a human + the calculation engine to confirm all specs
- [ ] Never auto-promote based on search confidence or AI inference
- [ ] Price and availability fields must only be populated when the source explicitly states them
- [ ] Image URLs must be direct links — never hotlink without permission verification
- [ ] CAD availability must only be marked `True` when a downloadable file URL exists
