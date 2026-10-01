"""
Stage 6.1 — Discovery Search Cache Tests

Tests:
  1. Query fingerprint determinism & collision-resistance
  2. Cache miss → provider called, results written
  3. Cache hit (specs fresh) → provider NOT called, cached results returned
  4. Cache stale (specs TTL expired) → provider called, cache refreshed
  5. Deduplication: same fingerprint from slightly different float params
  6. Cache hit propagation: each result dict carries cache_hit=True & cache_source timestamp
  7. routes.py discovery_status: COMPLETED_FROM_CACHE vs COMPLETED_LIVE vs COMPLETED_MOCK_FALLBACK
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from app.database.database import SessionLocal
from app.database.seed import seed_database
from app.database.models import DiscoverySearchCache
from app.engine.discover import (
    SearchProvider,
    MockIndustrialSearchProvider,
    build_query_fingerprint,
    lookup_cache,
    write_cache,
    discover_and_evaluate_components,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()
    yield db
    db.close()


def _clean_cache(db, torque, speed, voltage, sf):
    """Helper: delete any existing cache row for the given params."""
    from app.engine.discover import build_query_fingerprint
    fp = build_query_fingerprint(torque, speed, voltage, sf)
    row = db.query(DiscoverySearchCache).filter(
        DiscoverySearchCache.query_fingerprint == fp
    ).first()
    if row:
        db.delete(row)
        db.commit()


class CountingProvider(SearchProvider):
    """Test provider that counts how many times .search() is called."""
    def __init__(self, results=None):
        self.call_count = 0
        self._results = results or [
            {
                "manufacturer": "TestCorp",
                "product_name": "Test Gearmotor 24V",
                "model": "TC-CACHE-01",
                "part_number": "TC-CACHE-01",
                "product_url": "https://testcorp.com/product",
                "datasheet_url": "https://testcorp.com/ds.pdf",
                "image_url": None,
                "voltage_v": 24.0,
                "power_w": 100.0,
                "nominal_speed_rpm": 2000.0,
                "nominal_torque_nm": 0.5,
                "gear_ratio": 20.0,
                "efficiency": 0.85,
                "max_output_torque_nm": 8.5,
                "availability_status": "IN_STOCK",
                "price": 150.0,
                "price_currency": "USD",
                "cad_available": "True",
                "cad_url": None,
                "source": "CountingProvider"
            }
        ]

    def search(self, query: str, limit: int = 10):
        self.call_count += 1
        return self._results


# ── 1. Fingerprint determinism ────────────────────────────────────────────────

def test_fingerprint_is_deterministic():
    """Same params → same fingerprint every time."""
    fp1 = build_query_fingerprint(1.0, 35.0, 24.0, 1.0)
    fp2 = build_query_fingerprint(1.0, 35.0, 24.0, 1.0)
    assert fp1 == fp2
    assert len(fp1) == 64  # SHA-256 hex


def test_fingerprint_different_for_different_params():
    """Different engineering requirements → different fingerprints."""
    fp_a = build_query_fingerprint(1.0,  35.0, 24.0, 1.0)
    fp_b = build_query_fingerprint(2.0,  35.0, 24.0, 1.0)
    fp_c = build_query_fingerprint(1.0, 100.0, 24.0, 1.0)
    fp_d = build_query_fingerprint(1.0,  35.0, 48.0, 1.0)
    assert fp_a != fp_b
    assert fp_a != fp_c
    assert fp_a != fp_d


def test_fingerprint_collapses_minor_float_differences():
    """
    Params that round to the same canonical key must produce the same fingerprint.
    e.g. torque=1.000001 rounds to 1.0 at 2 dp → same key as 1.0
    """
    fp_exact   = build_query_fingerprint(1.0,      35.0,     24.0, 1.0)
    fp_epsilon = build_query_fingerprint(1.000001, 35.0001,  24.0, 1.0)
    assert fp_exact == fp_epsilon


# ── 2. Cache miss → provider called ──────────────────────────────────────────

def test_cache_miss_calls_provider(db_session):
    """On a cache miss the provider must be called exactly once."""
    torque, speed, voltage, sf = 1.11, 36.0, 24.0, 1.0
    _clean_cache(db_session, torque, speed, voltage, sf)

    provider = CountingProvider()
    results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=speed,
        required_torque_nm=torque,
        service_factor=sf,
        max_voltage_v=voltage,
        provider=provider
    )

    assert provider.call_count == 1, "Provider should be called once on cache miss"
    # Verify cache row was created
    fp  = build_query_fingerprint(torque, speed, voltage, sf)
    row = db_session.query(DiscoverySearchCache).filter(
        DiscoverySearchCache.query_fingerprint == fp
    ).first()
    assert row is not None, "Cache row should be created after provider call"
    assert row.provider == "CountingProvider"


# ── 3. Cache hit → provider NOT called ───────────────────────────────────────

def test_cache_hit_skips_provider(db_session):
    """On a fresh cache hit the provider must NOT be called."""
    torque, speed, voltage, sf = 1.22, 37.0, 24.0, 1.0
    _clean_cache(db_session, torque, speed, voltage, sf)

    provider = CountingProvider()

    # First call: populates cache
    discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=speed,
        required_torque_nm=torque,
        service_factor=sf,
        max_voltage_v=voltage,
        provider=provider
    )
    assert provider.call_count == 1

    # Second call: should come from cache — provider NOT called again
    discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=speed,
        required_torque_nm=torque,
        service_factor=sf,
        max_voltage_v=voltage,
        provider=provider
    )
    assert provider.call_count == 1, "Provider should NOT be called on cache hit"


# ── 4. Stale cache → provider called & cache refreshed ───────────────────────

def test_stale_cache_refreshes(db_session):
    """A cache row whose specs_cached_at is older than SPECS_TTL_DAYS must trigger a fresh call."""
    from app.engine.discover import SPECS_TTL_DAYS
    torque, speed, voltage, sf = 1.33, 38.0, 24.0, 1.0
    _clean_cache(db_session, torque, speed, voltage, sf)

    provider = CountingProvider()

    # Manually write a stale cache row (older than TTL)
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=SPECS_TTL_DAYS + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_cache(db_session, torque, speed, voltage, sf, provider._results, "OldProvider")

    # Manually back-date it
    from app.engine.discover import build_query_fingerprint
    fp  = build_query_fingerprint(torque, speed, voltage, sf)
    row = db_session.query(DiscoverySearchCache).filter(
        DiscoverySearchCache.query_fingerprint == fp
    ).first()
    row.specs_cached_at  = stale_ts
    row.prices_cached_at = stale_ts
    db_session.commit()

    # Call discover — should detect stale and call provider
    discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=speed,
        required_torque_nm=torque,
        service_factor=sf,
        max_voltage_v=voltage,
        provider=provider
    )
    assert provider.call_count == 1, "Provider should be called when cache is stale"

    # Verify cache was refreshed (specs_cached_at is now recent)
    db_session.refresh(row)
    updated_ts = datetime.fromisoformat(row.specs_cached_at.replace("Z", "+00:00"))
    assert (datetime.now(timezone.utc) - updated_ts).total_seconds() < 60, \
        "Cache should be refreshed with a recent timestamp"


# ── 5. cache_hit field on result dicts ───────────────────────────────────────

def test_results_carry_cache_hit_field(db_session):
    """Each result dict must contain cache_hit and cache_source fields."""
    torque, speed, voltage, sf = 1.44, 39.0, 24.0, 1.0
    _clean_cache(db_session, torque, speed, voltage, sf)

    provider = CountingProvider()

    # First call (live)
    live_results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=speed,
        required_torque_nm=torque,
        service_factor=sf,
        max_voltage_v=voltage,
        provider=provider
    )
    assert len(live_results) > 0
    for r in live_results:
        assert "cache_hit" in r
        assert "cache_source" in r
        assert r["cache_hit"] is False, "First call must be a live hit (cache_hit=False)"

    # Second call (cached)
    cached_results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=speed,
        required_torque_nm=torque,
        service_factor=sf,
        max_voltage_v=voltage,
        provider=provider
    )
    for r in cached_results:
        assert r["cache_hit"] is True, "Second call must be a cache hit (cache_hit=True)"
        assert r["cache_source"] is not None, "cache_source should contain the cache timestamp"


# ── 6. lookup_cache / write_cache unit tests ─────────────────────────────────

def test_lookup_cache_returns_none_on_miss(db_session):
    torque, speed, voltage, sf = 9.99, 999.0, 99.0, 1.5
    _clean_cache(db_session, torque, speed, voltage, sf)
    result = lookup_cache(db_session, torque, speed, voltage, sf)
    assert result is None


def test_write_then_lookup_cache(db_session):
    torque, speed, voltage, sf = 2.5, 50.0, 24.0, 1.2
    _clean_cache(db_session, torque, speed, voltage, sf)

    raw = [{"manufacturer": "CacheCo", "product_name": "Test", "part_number": "CC-01"}]
    write_cache(db_session, torque, speed, voltage, sf, raw, "TestProvider")

    result = lookup_cache(db_session, torque, speed, voltage, sf)
    assert result is not None
    assert result["raw_results"] == raw
    assert result["provider"] == "TestProvider"
    assert result["specs_fresh"] is True


def test_write_cache_updates_existing(db_session):
    torque, speed, voltage, sf = 3.0, 60.0, 24.0, 1.0
    _clean_cache(db_session, torque, speed, voltage, sf)

    raw_v1 = [{"manufacturer": "V1Corp", "product_name": "V1 Motor"}]
    raw_v2 = [{"manufacturer": "V2Corp", "product_name": "V2 Motor"}]

    write_cache(db_session, torque, speed, voltage, sf, raw_v1, "ProviderV1")
    write_cache(db_session, torque, speed, voltage, sf, raw_v2, "ProviderV2")

    result = lookup_cache(db_session, torque, speed, voltage, sf)
    assert result["raw_results"] == raw_v2
    assert result["provider"] == "ProviderV2"
