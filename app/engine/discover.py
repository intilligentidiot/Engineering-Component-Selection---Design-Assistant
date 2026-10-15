import html
import json
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database.models import (
    DiscoveredComponent,
    DiscoverySearchCache,
    DATA_STATUS_DISCOVERED,
    DATA_STATUS_DATA_INCOMPLETE,
    DATA_STATUS_STALE,
)
from app.engine.search_provider import SearchProvider
from app.engine.torque import calculate_design_torque, calculate_gearbox_output_torque
from app.engine.power import calculate_mechanical_power
from app.engine.fit import compute_fit
from app.engine.sizing.defaults import DEFAULT_SPEED_TOLERANCE_PCT

# ── Freshness thresholds ─────────────────────────────────────────────────────
# Engineering spec data stays valid for 90 days.
# Price / availability data is only valid for 1 day.
SPECS_TTL_DAYS  = 90
PRICES_TTL_DAYS = 1


class MockIndustrialSearchProvider(SearchProvider):
    """
    Default approved search provider implementation using realistic external component data feeds.
    Can be replaced or extended with live API providers.
    """
    
    def __init__(self):
        # Simulated external manufacturer and distributor product index
        self.mock_index = [
            {
                "manufacturer": "Oriental Motor",
                "product_name": "BLH Series Brushless Motor & Gearhead",
                "model": "BLH230K-30",
                "part_number": "BLH230K-30",
                "product_url": "https://www.orientalmotor.com/products/brushless-dc-motors/blh230k-30.html",
                "datasheet_url": "https://www.orientalmotor.com/pdf/datasheets/BLH230K-30_ds.pdf",
                "image_url": "https://www.orientalmotor.com/images/products/blh_series.jpg",
                "voltage_v": 24.0,
                "power_w": 30.0,
                "nominal_speed_rpm": 3000.0,
                "nominal_torque_nm": 0.1,
                "gear_ratio": 30.0,
                "efficiency": 0.81,
                "max_output_torque_nm": 2.2,
                "availability_status": "IN_STOCK",
                "price": 245.0,
                "price_currency": "USD",
                "cad_available": "True",
                "cad_url": "https://www.orientalmotor.com/cad/BLH230K-30.step",
                "source": "Oriental Motor Official Portal"
            },
            {
                "manufacturer": "Nanotec",
                "product_name": "DB42 Brushless Motor + Planetary Gearbox",
                "model": "DB42C048024-GP42-25",
                "part_number": "DB42C048024-GP42-25",
                "product_url": "https://www.nanotec.com/us/en/products/db42c048024-gp42-25",
                "datasheet_url": "https://www.nanotec.com/datasheets/DB42C048024.pdf",
                "image_url": "https://www.nanotec.com/media/products/DB42_GP42.png",
                "voltage_v": 24.0,
                "power_w": 65.0,
                "nominal_speed_rpm": 3500.0,
                "nominal_torque_nm": 0.18,
                "gear_ratio": 25.0,
                "efficiency": 0.85,
                "max_output_torque_nm": 3.8,
                "availability_status": "IN_STOCK",
                "price": 189.50,
                "price_currency": "USD",
                "cad_available": "True",
                "cad_url": "https://www.nanotec.com/cad/DB42C048024-GP42-25.step",
                "source": "Nanotec Direct Catalog"
            },
            {
                "manufacturer": "ElectroCraft",
                "product_name": "Complete Drive Motor Assembly",
                "model": "RP34-24V-TR15",
                "part_number": "RP34-24V-TR15",
                "product_url": "https://www.electrocraft.com/products/dpm/RP34/",
                "datasheet_url": None,  # Intentionally missing datasheet to test incomplete data handling
                "image_url": "https://www.electrocraft.com/images/RP34.jpg",
                "voltage_v": 24.0,
                "power_w": 120.0,
                "nominal_speed_rpm": 2400.0,
                "nominal_torque_nm": 0.45,
                "gear_ratio": 15.0,
                "efficiency": None,  # Missing efficiency to test DATA_INCOMPLETE status
                "max_output_torque_nm": 5.5,
                "availability_status": "AVAILABILITY_NOT_CONFIRMED",
                "price": None,
                "price_currency": "USD",
                "cad_available": "False",
                "cad_url": None,
                "source": "Industrial Motor Supplier Inc."
            },
            {
                "manufacturer": "Nidec Servo",
                "product_name": "Brushless DC Gearmotor 48V",
                "model": "DME44B-48V-G50",
                "part_number": "DME44B-48V-G50",
                "product_url": "https://www.nidec-servo.com/en/digital/pdf/DME44.pdf",
                "datasheet_url": "https://www.nidec-servo.com/en/digital/pdf/DME44.pdf",
                "image_url": "https://www.nidec-servo.com/img/dme44.jpg",
                "voltage_v": 48.0,
                "power_w": 150.0,
                "nominal_speed_rpm": 3000.0,
                "nominal_torque_nm": 0.48,
                "gear_ratio": 50.0,
                "efficiency": 0.78,
                "max_output_torque_nm": 18.0,
                "availability_status": "IN_STOCK",
                "price": 310.00,
                "price_currency": "USD",
                "cad_available": "True",
                "cad_url": "https://www.nidec-servo.com/cad/DME44B-48V-G50.step",
                "source": "Nidec Industrial Catalog"
            }
        ]

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        # Simple keyword matching against catalog items
        q_lower = query.lower()
        results = []
        for item in self.mock_index:
            results.append(item)
            if len(results) >= limit:
                break
        return results


# ── Text / URL sanitization ──────────────────────────────────────────────────

def sanitize_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    # Strip <script>...</script> and <style>...</style> entirely
    clean = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Strip HTML tags and escape dangerous characters
    clean = re.sub(r'<[^>]*>', '', clean)
    return html.escape(clean.strip())


def sanitize_url(url: Optional[str]) -> Optional[str]:
    """
    URL normalization & validation (Task 4):
    - Accepts only http:// or https:// URLs
    - Strips whitespace
    - Rejects empty, relative, or javascript: URLs
    - Preserves query parameters and legitimate path structures
    """
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    # Unescape HTML entities first in case url was pre-escaped
    cleaned = html.unescape(cleaned)
    if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(cleaned)
        if not parsed.scheme or not parsed.netloc:
            return None
        # Return clean, unescaped valid URL
        return cleaned
    except Exception:
        return None


# ── Query construction ───────────────────────────────────────────────────────

def construct_engineering_query(required_torque_nm: float, required_speed_rpm: float, max_voltage_v: float) -> str:
    """
    Construct precise engineering query from calculated requirements.
    Never generates vague queries like 'best motor'.
    """
    return f"{max_voltage_v:.0f}V industrial DC motor gearbox {required_torque_nm:.1f} Nm {required_speed_rpm:.0f} RPM"


# ── Stage 6.2 — Relevance filter ─────────────────────────────────────────────
#
# A result must contain at least one STRONG product indicator
# (motor / gearbox type term) OR at least two SUPPORTING indicators
# (engineering quantity / product-document terms) to be accepted.
#
# This is fully deterministic (no ML/AI).
# The filter operates on: title + snippet + URL combined.

# Words that directly indicate this is an electric motor or gearbox product.
_PRODUCT_KEYWORDS: List[str] = [
    "motor", "gearmotor", "gear motor", "geared motor", "gearbox",
    "gearhead", "dc motor", "dc gear motor", "planetary gearbox",
    "planetary gearmotor", "planetary gear", "servo motor", "stepper motor",
    "brushless motor", "brushless dc", "bldc", "electric motor",
    "motor gearbox", "geared drive", "gear drive", "reducer",
]

# Supporting engineering / product-document terms.
# A result with ≥2 of these (and zero product keywords) may still be relevant
# if it is clearly about a product (datasheet, part number, etc.).
_SUPPORT_KEYWORDS: List[str] = [
    "torque", "output torque", "rpm", "rated speed", "rated torque",
    "voltage", "gear ratio", "reduction ratio", "efficiency",
    "datasheet", "part number", "model number", "product page",
    "specifications", "technical data", "catalog", "series", "watt",
]

# Phrases that almost certainly mean the result is NOT an engineering product.
# Any result matching one of these is rejected outright regardless of other signals.
_REJECTION_PHRASES: List[str] = [
    "annual report", "municipal plan", "government plan", "city plan",
    "community plan", "ace plan", "planning document", "press release",
    "news article", "wikipedia", "wikipedia.org",
    "research paper", "academic paper", "journal article",
    "thesis", "dissertation",
    "terms of service", "privacy policy", "cookie policy",
    "job posting", "career", "employment opportunity",
    "stock price", "share price", "investor",
]


def is_relevant_product_result(raw: Dict[str, Any]) -> bool:
    """
    Stage 6.2 — Deterministic relevance filter.

    Returns True  → result is a plausible motor/gearbox product candidate.
    Returns False → result is irrelevant and must be rejected.

    Decision logic:
    1. If the combined text matches a REJECTION_PHRASE → reject immediately.
    2. If the combined text contains ≥1 PRODUCT_KEYWORD → accept.
    3. If the combined text contains ≥2 SUPPORT_KEYWORDS → accept.
    4. Otherwise → reject.

    Never modifies or fabricates any field.  Only inspects what is present.
    """
    title   = (raw.get("product_name") or raw.get("title") or "").lower()
    snippet = (raw.get("snippet") or raw.get("description") or "").lower()
    url     = (raw.get("product_url") or raw.get("datasheet_url") or
               raw.get("link") or "").lower()
    mfg     = (raw.get("manufacturer") or "").lower()

    combined = f"{title} {snippet} {url} {mfg}"

    # Step 1: hard rejection phrases
    for phrase in _REJECTION_PHRASES:
        if phrase in combined:
            return False

    # Step 1.5: Structured data fallback
    # If the provider returns a normalized dictionary without text snippet/title
    # but WITH genuine engineering fields, accept it.
    engineering_fields = [
        "voltage_v", "power_w", "nominal_speed_rpm", "nominal_torque_nm",
        "gear_ratio", "efficiency", "max_output_torque_nm"
    ]
    structured_count = sum(1 for field in engineering_fields if raw.get(field) is not None)
    has_ident = bool(raw.get("manufacturer") or raw.get("part_number") or raw.get("product_name"))
    
    if structured_count >= 2 or (structured_count >= 1 and has_ident):
        return True

    # Step 2: strong product keyword match
    for kw in _PRODUCT_KEYWORDS:
        if kw in combined:
            return True

    # Step 3: ≥2 supporting keyword matches
    support_hits = sum(1 for kw in _SUPPORT_KEYWORDS if kw in combined)
    if support_hits >= 2:
        return True

    return False




# ── Stage 6.1 — Query fingerprint & cache helpers ────────────────────────────

def _build_canonical_key(
    required_torque_nm: float,
    required_speed_rpm: float,
    max_voltage_v: float,
    service_factor: float,
) -> str:
    """
    Build a stable, human-readable canonical key from rounded engineering
    parameters.  Minor float differences (e.g. 1.0 vs 1.00000001) must NOT
    produce different cache entries.

    Rounding strategy:
      - torque     : 2 decimal places  (0.01 Nm resolution)
      - speed      : 0 decimal places  (1 RPM resolution)
      - voltage    : 0 decimal places  (1 V resolution)
      - SF         : 2 decimal places
    """
    torque_r  = round(required_torque_nm,  2)
    speed_r   = round(required_speed_rpm,  0)
    voltage_r = round(max_voltage_v,       0)
    sf_r      = round(service_factor,      2)
    return f"t={torque_r}|s={speed_r}|v={voltage_r}|sf={sf_r}"


def build_query_fingerprint(
    required_torque_nm: float,
    required_speed_rpm: float,
    max_voltage_v: float,
    service_factor: float,
) -> str:
    """
    SHA-256 of the canonical key — used as the primary cache index.
    Returns a 64-char hex string.
    """
    key = _build_canonical_key(required_torque_nm, required_speed_rpm, max_voltage_v, service_factor)
    return hashlib.sha256(key.encode()).hexdigest()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(ts_str: str) -> Optional[datetime]:
    """Parse an ISO-8601 UTC string back to a timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        # Handle both "YYYY-MM-DD HH:MM:SS UTC" and ISO 8601
        clean = ts_str.replace(" UTC", "+00:00")
        return datetime.fromisoformat(clean)
    except Exception:
        return None


def _is_specs_fresh(cache_row: "DiscoverySearchCache") -> bool:
    """True if the spec data in this cache row is within SPECS_TTL_DAYS."""
    cached_at = _parse_utc(cache_row.specs_cached_at)
    if cached_at is None:
        return False
    return (_now_utc() - cached_at) < timedelta(days=SPECS_TTL_DAYS)


def _is_prices_fresh(cache_row: "DiscoverySearchCache") -> bool:
    """True if the price/availability data in this cache row is within PRICES_TTL_DAYS."""
    cached_at = _parse_utc(cache_row.prices_cached_at)
    if cached_at is None:
        return False
    return (_now_utc() - cached_at) < timedelta(days=PRICES_TTL_DAYS)


def lookup_cache(
    db: Session,
    required_torque_nm: float,
    required_speed_rpm: float,
    max_voltage_v: float,
    service_factor: float,
) -> Optional[Dict[str, Any]]:
    """
    Stage 6.1 cache lookup.

    Returns a dict with:
        - raw_results  : list of raw product dicts (to be re-evaluated by the engine)
        - specs_fresh  : bool
        - prices_fresh : bool
        - provider     : str
        - cached_at    : str (ISO timestamp of when specs were last cached)
        - hit_count    : int

    Returns None if no cache entry exists.
    """
    fingerprint = build_query_fingerprint(required_torque_nm, required_speed_rpm, max_voltage_v, service_factor)
    row = db.query(DiscoverySearchCache).filter(
        DiscoverySearchCache.query_fingerprint == fingerprint
    ).first()

    if row is None:
        return None

    # Increment hit counter
    row.hit_count = (row.hit_count or 0) + 1
    db.commit()

    try:
        raw_results = json.loads(row.results_json)
    except Exception:
        # Corrupted cache row — treat as miss
        db.delete(row)
        db.commit()
        return None

    return {
        "raw_results":   raw_results,
        "specs_fresh":   _is_specs_fresh(row),
        "prices_fresh":  _is_prices_fresh(row),
        "provider":      row.provider or "Unknown",
        "cached_at":     row.specs_cached_at,
        "hit_count":     row.hit_count,
    }


def write_cache(
    db: Session,
    required_torque_nm: float,
    required_speed_rpm: float,
    max_voltage_v: float,
    service_factor: float,
    raw_results: List[Dict[str, Any]],
    provider_name: str,
) -> None:
    """
    Stage 6.1 — Write (or update) a cache row for the given query parameters.

    - Always updates specs_cached_at and results_json.
    - Always updates prices_cached_at (price data is piggy-backed on the same
      search result, so they are refreshed at the same time).
    """
    fingerprint  = build_query_fingerprint(required_torque_nm, required_speed_rpm, max_voltage_v, service_factor)
    query_text   = construct_engineering_query(required_torque_nm, required_speed_rpm, max_voltage_v)
    now_str      = _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    results_json = json.dumps(raw_results, default=str)

    existing = db.query(DiscoverySearchCache).filter(
        DiscoverySearchCache.query_fingerprint == fingerprint
    ).first()

    if existing:
        existing.results_json    = results_json
        existing.provider        = provider_name
        existing.specs_cached_at = now_str
        existing.prices_cached_at = now_str
    else:
        row = DiscoverySearchCache(
            query_fingerprint  = fingerprint,
            query_text         = query_text,
            results_json       = results_json,
            provider           = provider_name,
            specs_cached_at    = now_str,
            prices_cached_at   = now_str,
            hit_count          = 0,
        )
        db.add(row)

    db.commit()


# ── Main discovery workflow ───────────────────────────────────────────────────

def discover_and_evaluate_components(
    db: Session,
    required_speed_rpm: float,
    required_torque_nm: float,
    service_factor: float,
    max_voltage_v: float,
    provider: Optional[SearchProvider] = None,
    top_n: int = 5,
    peak_torque_nm: Optional[float] = None,
    speed_tolerance_pct: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Source B Internet Discovery Workflow (Stage 6.1 — with cache):

    1. Build query fingerprint from engineering parameters
    2. Check DiscoverySearchCache for a fresh result set
       a. If CACHE HIT (specs fresh):    re-evaluate cached raw results through
                                          deterministic engine — NO SerpApi call
       b. If CACHE MISS / SPECS STALE:   call provider, store results in cache,
                                          then evaluate
    3. Normalise & sanitise all external product data
    4. Store/update DiscoveredComponent rows (deduplication by part_number)
    5. Run EXISTING deterministic calculation engine on each candidate
    6. Return evaluated candidates tagged with cache_hit / cache_source
    """

    # ── Resolve provider ────────────────────────────────────────────────────
    provider_name = "MockIndustrialSearchProvider"
    if provider is None:
        import os
        from app.engine.search_provider import SerpApiSearchProvider
        if os.environ.get("SERPAPI_KEY"):
            try:
                provider = SerpApiSearchProvider()
                provider_name = "SerpApiSearchProvider"
            except Exception as e:
                print(f"Could not initialise SerpApiSearchProvider: {e}")
                provider = MockIndustrialSearchProvider()
        else:
            provider = MockIndustrialSearchProvider()
    else:
        # Caller supplied a custom provider — derive a name from the class
        provider_name = type(provider).__name__

    query   = construct_engineering_query(required_torque_nm, required_speed_rpm, max_voltage_v)
    now_str = _now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── Stage 6.1: Check cache first ────────────────────────────────────────
    cache_result = lookup_cache(db, required_torque_nm, required_speed_rpm, max_voltage_v, service_factor)

    cache_hit    = False
    cache_source = None   # Will be set to ISO timestamp string when hit

    if cache_result and cache_result["specs_fresh"]:
        # CACHE HIT — use stored raw results, skip SerpApi
        raw_results  = cache_result["raw_results"]
        cache_hit    = True
        cache_source = cache_result["cached_at"]
        print(
            f"[Cache HIT] query='{query}' "
            f"provider={cache_result['provider']} "
            f"hits={cache_result['hit_count']} "
            f"cached_at={cache_source}"
        )
    else:
        # CACHE MISS (or stale) — call provider
        reason = "stale" if (cache_result and not cache_result["specs_fresh"]) else "miss"
        print(f"[Cache {reason.upper()}] query='{query}' — calling provider {provider_name}")
        try:
            raw_results = provider.search(query, limit=10)
        except Exception as e:
            # Graceful failure: return empty list, do not crash system
            print(f"Internet discovery provider warning/failure: {e}")
            return []

        # Stage 6.2: Relevance filter BEFORE enrichment and cache
        relevant_raw = []
        for raw in raw_results:
            if not is_relevant_product_result(raw):
                title_preview = (raw.get("product_name") or raw.get("title") or "")[:80]
                print(f"[Relevance REJECT] '{title_preview}' - not a motor/gearbox product")
                continue
            relevant_raw.append(raw)
            
        # Stage 6.3: External Product Specification Enrichment
        from app.engine.product_enrichment import ProductEnricher
        enricher = ProductEnricher()
        enriched_results = enricher.enrich(relevant_raw)

        # Write results back to cache
        write_cache(
            db, required_torque_nm, required_speed_rpm,
            max_voltage_v, service_factor, enriched_results, provider_name
        )
        
        raw_results = enriched_results

    # ── Calculate engineering targets using existing engine logic ────────────
    design_torque = calculate_design_torque(required_torque_nm, service_factor).result
    req_power_w   = calculate_mechanical_power(design_torque, required_speed_rpm).result
    design_peak   = peak_torque_nm * service_factor if peak_torque_nm is not None else None

    discovered_evaluations = []

    for raw in raw_results:
        # ── Stage 6.2: Relevance filter ──────────────────────────────────────
        # Reject clearly irrelevant results (e.g. government reports, news
        # articles, PDFs unrelated to motor/gearbox products) BEFORE they
        # become component candidates or count toward the results limit.
        if not is_relevant_product_result(raw):
            title_preview = (raw.get("product_name") or raw.get("title") or "")[:80]
            print(f"[Relevance REJECT] '{title_preview}' — not a motor/gearbox product")
            continue
        # ─────────────────────────────────────────────────────────────────────

        # Deduplication check by manufacturer AND part_number

        pn  = sanitize_text(raw.get("part_number") or raw.get("model"))
        raw_mfg = sanitize_text(raw.get("manufacturer"))
        
        existing = None
        if pn and raw_mfg:
            existing = db.query(DiscoveredComponent).filter(
                DiscoveredComponent.part_number == pn,
                DiscoveredComponent.manufacturer == raw_mfg
            ).first()

        mfg = raw_mfg or "Unknown External Manufacturer"

        # Check completeness of engineering specifications
        v_v   = raw.get("voltage_v")
        p_w   = raw.get("power_w")
        n_rpm = raw.get("nominal_speed_rpm")
        n_t   = raw.get("nominal_torque_nm")
        ratio = raw.get("gear_ratio")
        eff   = raw.get("efficiency")
        max_t = raw.get("max_output_torque_nm")

        is_complete = all(x is not None for x in [v_v, p_w, n_rpm, n_t, ratio, eff])
        status = DATA_STATUS_DISCOVERED if is_complete else DATA_STATUS_DATA_INCOMPLETE

        if not existing:
            comp = DiscoveredComponent(
                search_query          = query,
                source                = sanitize_text(raw.get("source", "External Search Provider")),
                source_type           = "INTERNET",
                manufacturer          = mfg,
                product_name          = sanitize_text(raw.get("product_name", f"{mfg} Motor/Gearbox")),
                model                 = sanitize_text(raw.get("model")),
                part_number           = pn,
                product_url           = sanitize_url(raw.get("product_url")),
                datasheet_url         = sanitize_url(raw.get("datasheet_url")),
                image_url             = sanitize_url(raw.get("image_url")),
                voltage_v             = v_v,
                power_w               = p_w,
                nominal_speed_rpm     = n_rpm,
                nominal_torque_nm     = n_t,
                gear_ratio            = ratio,
                efficiency            = eff,
                max_output_torque_nm  = max_t,
                availability_status   = sanitize_text(raw.get("availability_status", "AVAILABILITY_NOT_CONFIRMED")),
                availability_source   = sanitize_text(raw.get("source")),
                availability_checked_at = now_str,
                price                 = raw.get("price"),
                price_currency        = sanitize_text(raw.get("price_currency", "USD")),
                price_source          = sanitize_text(raw.get("source")),
                price_checked_at      = now_str,
                cad_available         = str(raw.get("cad_available", "False")),
                cad_url               = sanitize_url(raw.get("cad_url")),
                data_status           = status,
                discovered_at         = now_str,
                last_checked_at       = now_str,
            )
            db.add(comp)
            db.commit()
            db.refresh(comp)
        else:
            comp = existing

        # ── Run EXISTING deterministic calculation engine ─────────────────
        calc_trace   = {}
        perf         = {}
        overall_status = "MEETS"
        fit            = None

        if not is_complete:
            overall_status = "DATA_INCOMPLETE"
            calc_trace = {
                "error":       "Missing essential engineering specifications in external product record.",
                "data_status": DATA_STATUS_DATA_INCOMPLETE
            }
        else:
            # Check voltage filter
            if comp.voltage_v and comp.voltage_v > max_voltage_v:
                continue  # Voltage exceeds user constraint

            output_speed_rpm    = comp.nominal_speed_rpm / comp.gear_ratio
            calc_output_torque  = calculate_gearbox_output_torque(
                comp.nominal_torque_nm, comp.gear_ratio, comp.efficiency
            ).result

            torque_meets = calc_output_torque >= design_torque
            speed_meets  = output_speed_rpm  >= required_speed_rpm
            if speed_tolerance_pct is not None:
                speed_meets = speed_meets and output_speed_rpm <= required_speed_rpm * (1 + speed_tolerance_pct / 100)

            if not (torque_meets and speed_meets):
                overall_status = "DOES_NOT_MEET"
                continue

            # Stage 8: peak torque check against the product's rated output torque
            peak_trace = None
            if design_peak is not None:
                if comp.max_output_torque_nm is not None:
                    if comp.max_output_torque_nm < design_peak:
                        overall_status = "DOES_NOT_MEET"
                        continue
                    peak_status = "MEETS"
                    peak_cmp = f"{comp.max_output_torque_nm} Nm (rated max output) >= {round(design_peak, 4)} Nm"
                elif calc_output_torque >= design_peak:
                    peak_status = "MEETS"
                    peak_cmp = (f"{round(calc_output_torque, 4)} Nm (continuous output) >= {round(design_peak, 4)} Nm "
                                f"— rated max output not stated")
                else:
                    peak_status = "DATA_INCOMPLETE"
                    overall_status = "DATA_INCOMPLETE"
                    peak_cmp = f"Rated max output torque not stated — cannot verify {round(design_peak, 4)} Nm peak"
                peak_trace = {
                    "formula":    "Rated max output torque ≥ T_peak × Service Factor",
                    "comparison": peak_cmp,
                    "status":     peak_status,
                }

            calc_trace = {
                "design_torque": {
                    "formula":      "T_design = Required Torque × Service Factor",
                    "substitution": f"{required_torque_nm} Nm × {service_factor}",
                    "result":       design_torque,
                    "unit":         "Nm"
                },
                "gearbox_output_torque": {
                    "formula":      "T_output = Motor Torque × Gear Ratio × Efficiency",
                    "substitution": f"{comp.nominal_torque_nm} Nm × {comp.gear_ratio} × {comp.efficiency}",
                    "result":       round(calc_output_torque, 4),
                    "unit":         "Nm",
                    "comparison":   f"{round(calc_output_torque, 4)} Nm >= {design_torque} Nm",
                    "status":       "MEETS" if torque_meets else "DOES_NOT_MEET"
                },
                "output_speed": {
                    "formula":      "Output Speed = Motor RPM / Ratio",
                    "substitution": f"{comp.nominal_speed_rpm} RPM / {comp.gear_ratio}",
                    "result":       round(output_speed_rpm, 2),
                    "unit":         "RPM",
                    "comparison":   f"{round(output_speed_rpm, 2)} RPM >= {required_speed_rpm} RPM",
                    "status":       "MEETS" if speed_meets else "DOES_NOT_MEET"
                }
            }

            if peak_trace:
                calc_trace["peak_torque"] = peak_trace

            if overall_status == "MEETS":
                fit = compute_fit(
                    calc_output_torque, design_torque, output_speed_rpm, required_speed_rpm,
                    speed_tolerance_pct if speed_tolerance_pct is not None else DEFAULT_SPEED_TOLERANCE_PCT,
                    comp.power_w * comp.efficiency if comp.power_w else None, req_power_w,
                )

            perf = {
                "output_speed_rpm":    round(output_speed_rpm, 2),
                "output_torque_nm":    round(calc_output_torque, 4),
                "torque_margin_factor": round(calc_output_torque / design_torque, 2)
            }

        discovered_evaluations.append({
            "source_type":      "INTERNET",
            "source":           comp.source,
            "manufacturer":     comp.manufacturer,
            "product_name":     comp.product_name,
            "model":            comp.model,
            "part_number":      comp.part_number,
            "product_url":      comp.product_url,
            "datasheet_url":    comp.datasheet_url,
            "image_url":        comp.image_url,
            "specs": {
                "voltage_v":           comp.voltage_v,
                "power_w":             comp.power_w,
                "nominal_speed_rpm":   comp.nominal_speed_rpm,
                "nominal_torque_nm":   comp.nominal_torque_nm,
                "gear_ratio":          comp.gear_ratio,
                "efficiency":          comp.efficiency,
                "max_output_torque_nm": comp.max_output_torque_nm,
            },
            "availability": {
                "status":     comp.availability_status,
                "source":     comp.availability_source,
                "checked_at": comp.availability_checked_at,
            },
            "price": {
                "amount":     comp.price,
                "currency":   comp.price_currency,
                "source":     comp.price_source,
                "checked_at": comp.price_checked_at,
            },
            "cad": {
                "available": comp.cad_available == "True",
                "url":       comp.cad_url,
            },
            "verification": {
                "data_status":   comp.data_status,
                "discovered_at": comp.discovered_at,
                "last_checked_at": comp.last_checked_at,
            },
            # ── Stage 6.1 cache provenance fields ──────────────────────────
            "cache_hit":    cache_hit,
            "cache_source": cache_source,
            # Stage 6.3 provenance fields
            "specification_source": raw.get("specification_source"),
            "specification_source_url": raw.get("specification_source_url"),
            "extracted_at": raw.get("extracted_at"),
            # ───────────────────────────────────────────────────────────────
            "performance":        perf,
            "calculation_trace":  calc_trace,
            "engineering_status": overall_status,
            "fit":                fit,
        })

    return discovered_evaluations[:top_n]
