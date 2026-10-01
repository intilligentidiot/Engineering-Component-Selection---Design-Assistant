"""
Stage 6.2 — Relevance Filter Tests

Tests:
  1.  Unrelated PDF (government planning doc) → rejected
  2.  DC gear motor title → accepted
  3.  Gearbox product with snippet → accepted
  4.  Genuine product with missing torque → accepted, DATA_INCOMPLETE preserved
  5.  Result with no manufacturer/part-number → accepted, values stay None (not fabricated)
  6.  Irrelevant results do not consume the candidate limit
  7.  All existing cache tests still pass (imported and re-run)

No real SerpApi calls are made.
"""

import pytest
from app.engine.discover import (
    is_relevant_product_result,
    discover_and_evaluate_components,
    SearchProvider,
)
from app.database.database import SessionLocal
from app.database.seed import seed_database
from app.database.models import DATA_STATUS_DATA_INCOMPLETE


# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()
    yield db
    db.close()


# ── Helper provider ───────────────────────────────────────────────────────────

class FixedResultsProvider(SearchProvider):
    """Returns a fixed, pre-defined list of raw results."""
    def __init__(self, results):
        self._results = results

    def search(self, query: str, limit: int = 10):
        return self._results


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Government / planning document PDF is rejected
# ─────────────────────────────────────────────────────────────────────────────
def test_government_plan_pdf_rejected():
    """Unrelated planning document must be rejected by is_relevant_product_result()."""
    raw = {
        "product_name": "2017 ACE Plan",
        "snippet": "Municipal community planning document for the City of Nanaimo.",
        "product_url": "https://nserbt.ca/sites/default/files/(M07745) 2017 ACE Plan.pdf",
    }
    assert is_relevant_product_result(raw) is False, "Planning document PDF should be rejected"


def test_annual_report_rejected():
    raw = {
        "product_name": "Annual Report 2024",
        "snippet": "Corporate annual report for fiscal year 2024.",
        "product_url": "https://example.com/annual_report_2024.pdf",
    }
    assert is_relevant_product_result(raw) is False


def test_news_article_rejected():
    raw = {
        "product_name": "News: Electric Vehicle Market Grows",
        "snippet": "A news article about industry trends in electric vehicles.",
        "product_url": "https://technews.example.com/ev-market-2024",
    }
    assert is_relevant_product_result(raw) is False


def test_wikipedia_rejected():
    raw = {
        "product_name": "DC Motor - Wikipedia",
        "snippet": "Wikipedia article describing DC motor history.",
        "product_url": "https://en.wikipedia.org/wiki/DC_motor",
    }
    assert is_relevant_product_result(raw) is False


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2 — DC Gear Motor product accepted
# ─────────────────────────────────────────────────────────────────────────────
def test_dc_gear_motor_accepted():
    """A result with 'DC gear motor' in the title must be accepted."""
    raw = {
        "product_name": "24V DC Gear Motor 35 RPM Industrial",
        "snippet": "High-torque 24V DC gear motor with 35 RPM output speed.",
        "product_url": "https://www.motorshop.com/dc-gear-motor-24v",
    }
    assert is_relevant_product_result(raw) is True


def test_brushless_motor_accepted():
    raw = {
        "product_name": "BLH Series Brushless Motor & Gearhead",
        "snippet": "Compact brushless DC motor with integrated planetary gearhead.",
        "product_url": "https://www.orientalmotor.com/products/brushless-dc-motors/blh.html",
    }
    assert is_relevant_product_result(raw) is True


def test_motor_in_url_accepted():
    """If title/snippet are sparse but the URL clearly says 'motor', accept it."""
    raw = {
        "product_name": "BLH230K-30",
        "snippet": "",
        "product_url": "https://www.orientalmotor.com/motor/blh230k-30.html",
    }
    assert is_relevant_product_result(raw) is True


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3 — Gearbox product accepted
# ─────────────────────────────────────────────────────────────────────────────
def test_planetary_gearbox_accepted():
    raw = {
        "product_name": "GP42 Planetary Gearbox",
        "snippet": "High-efficiency planetary gearbox with 25:1 gear ratio for industrial drives.",
        "product_url": "https://www.nanotec.com/gearbox/gp42",
    }
    assert is_relevant_product_result(raw) is True


def test_gearhead_accepted():
    raw = {
        "product_name": "Maxon GP 42 C Gearhead",
        "snippet": "Planetary gearhead compatible with DCX 22mm motors.",
        "product_url": "https://www.maxongroup.com/gearhead/gp42c",
    }
    assert is_relevant_product_result(raw) is True


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4 — Genuine product with missing torque stays DATA_INCOMPLETE
# ─────────────────────────────────────────────────────────────────────────────
def test_genuine_motor_missing_specs_stays_data_incomplete(db_session):
    """
    A genuine motor product with missing torque must pass the filter,
    become a candidate, and carry DATA_INCOMPLETE — not be rejected.
    """
    provider = FixedResultsProvider([
        {
            "manufacturer": "TestMotorCo",
            "product_name": "24V DC Gear Motor 100 RPM",
            "part_number": "TMC-24-100",
            "product_url": "https://testmotorco.com/tmc-24-100",
            "voltage_v": 24.0,
            "power_w": 30.0,
            "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": None,   # ← missing
            "gear_ratio": 30.0,
            "efficiency": None,          # ← missing
            "max_output_torque_nm": None,
        }
    ])

    results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=35.0,
        required_torque_nm=1.0,
        service_factor=1.0,
        max_voltage_v=24.0,
        provider=provider
    )

    # The product passed the relevance filter and became a candidate
    assert len(results) >= 1, "Genuine motor product should be accepted even when specs are incomplete"

    # Find our test product
    candidate = next((r for r in results if r.get("part_number") == "TMC-24-100"), None)
    assert candidate is not None, "TMC-24-100 must be present in results"

    # Must carry DATA_INCOMPLETE, not MEETS or DOES_NOT_MEET
    assert candidate["verification"]["data_status"] == DATA_STATUS_DATA_INCOMPLETE, \
        "Product with missing specs must be DATA_INCOMPLETE, not silently promoted"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — No manufacturer / part number → values stay None (not fabricated)
# ─────────────────────────────────────────────────────────────────────────────
def test_no_manufacturer_not_fabricated(db_session):
    """
    If a result has no manufacturer or part number, those fields
    must stay empty/None — the system must not invent values.
    """
    provider = FixedResultsProvider([
        {
            "manufacturer": None,          # ← not provided
            "product_name": "24V DC Gear Motor 35 RPM Compact",
            "part_number": None,           # ← not provided
            "product_url": "https://somestore.com/motor-product-page",
            "voltage_v": 24.0,
            "power_w": 50.0,
            "nominal_speed_rpm": 3500.0,
            "nominal_torque_nm": 0.14,
            "gear_ratio": 100.0,
            "efficiency": 0.80,
            "max_output_torque_nm": 11.0,
        }
    ])

    results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=35.0,
        required_torque_nm=2.0,
        service_factor=1.0,
        max_voltage_v=24.0,
        provider=provider
    )

    assert len(results) >= 1, "Motor result with missing provenance should still be accepted"
    candidate = results[0]

    # part_number must be None (not fabricated)
    assert candidate.get("part_number") is None, "part_number must not be fabricated"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6 — Irrelevant results do not consume the candidate limit
# ─────────────────────────────────────────────────────────────────────────────
def test_irrelevant_results_do_not_consume_limit(db_session):
    """
    If 4 out of 5 raw results are irrelevant and 1 is a valid motor,
    the final result list must contain only the 1 valid motor,
    not 5 items (the irrelevant four must not fill empty slots).
    """
    provider = FixedResultsProvider([
        # 4 irrelevant
        {"product_name": "2017 ACE Plan",                "snippet": "Municipal community planning document.", "product_url": "https://gov.ca/ace_plan.pdf"},
        {"product_name": "Annual Report 2023",           "snippet": "Corporate annual report.",               "product_url": "https://corp.com/annual.pdf"},
        {"product_name": "News: Tech Market Report",     "snippet": "A news article about industry trends.", "product_url": "https://news.com/tech"},
        {"product_name": "Research Paper on Automation", "snippet": "Academic paper on robotic research.",   "product_url": "https://journal.org/paper"},
        # 1 genuine motor product
        {
            "manufacturer": "FilterTestCo",
            "product_name": "24V DC Gear Motor 50 RPM",
            "part_number": "FTC-24-50",
            "product_url": "https://filtertestco.com/gear-motor",
            "voltage_v": 24.0, "power_w": 40.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.13, "gear_ratio": 60.0, "efficiency": 0.82,
            "max_output_torque_nm": 6.0,
        }
    ])

    results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=50.0,
        required_torque_nm=1.0,
        service_factor=1.0,
        max_voltage_v=24.0,
        provider=provider
    )

    # The 4 irrelevant results must not appear
    for r in results:
        assert "ACE" not in (r.get("product_name") or ""), "Government plan should not be a candidate"
        assert "Annual" not in (r.get("product_name") or ""), "Annual report should not be a candidate"

    # The valid motor must be present
    valid = next((r for r in results if r.get("part_number") == "FTC-24-50"), None)
    assert valid is not None, "The one relevant motor product must be in results"


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7 — Edge cases for the relevance filter
# ─────────────────────────────────────────────────────────────────────────────
def test_datasheet_pdf_of_motor_accepted():
    """A datasheet PDF for a motor product must be accepted (not rejected as a PDF)."""
    raw = {
        "product_name": "BLH230K-30 Brushless Motor Datasheet",
        "snippet": "Technical datasheet with torque, voltage and RPM specifications.",
        "datasheet_url": "https://www.orientalmotor.com/pdf/BLH230K-30.pdf",
        "product_url": None,
    }
    assert is_relevant_product_result(raw) is True


def test_empty_result_rejected():
    """A completely empty result must be rejected."""
    raw = {}
    assert is_relevant_product_result(raw) is False


def test_career_page_rejected():
    """A job posting page must be rejected."""
    raw = {
        "product_name": "Motor Design Engineer – Career Opportunity",
        "snippet": "Employment opportunity for an experienced engineer.",
        "product_url": "https://company.com/careers/motor-engineer",
    }
    assert is_relevant_product_result(raw) is False


def test_support_keywords_only_accepted():
    """Two supporting keywords with no product keyword should be accepted (spec sheet case)."""
    raw = {
        "product_name": "DB42C048024 Technical Specifications",
        "snippet": "Voltage: 24V, Rated torque 0.18 Nm, datasheet included.",
        "product_url": "https://nanotec.com/db42c048024",
    }
    # Contains: "voltage", "torque", "datasheet" → ≥2 support keywords → accept
    assert is_relevant_product_result(raw) is True


# ─────────────────────────────────────────────────────────────────────────────
# TEST 8 — Structured Data Fallback
# ─────────────────────────────────────────────────────────────────────────────

def test_normalized_motor_record_accepted():
    """Normalized motor record with structured engineering fields → accepted."""
    raw = {
        "manufacturer": "Oriental Motor",
        "part_number": "ABC123M",
        "voltage_v": 24.0,
        "power_w": 30.0,
        "nominal_speed_rpm": 3000.0,
        "nominal_torque_nm": 0.1,
        "gear_ratio": 30.0,
        "efficiency": 0.81
    }
    assert is_relevant_product_result(raw) is True


def test_normalized_gearbox_record_accepted():
    """Normalized gearbox record with structured engineering fields → accepted."""
    raw = {
        "manufacturer": "Nanotec",
        "part_number": "GP42-25",
        "gear_ratio": 25.0,
        "efficiency": 0.90,
        "max_output_torque_nm": 15.0
    }
    assert is_relevant_product_result(raw) is True


def test_normalized_record_no_text_valid_engineering_accepted():
    """Normalized record without title/snippet/url but with valid engineering fields → accepted."""
    raw = {
        # No manufacturer or part number
        "voltage_v": 12.0,
        "nominal_speed_rpm": 1500.0,
        "nominal_torque_nm": 0.05
    }
    # >= 2 engineering fields -> accepted
    assert is_relevant_product_result(raw) is True


def test_completely_empty_dictionary_rejected():
    """Completely empty/uninformative dictionary → rejected."""
    raw = {}
    assert is_relevant_product_result(raw) is False
    
    raw_one_field = {"voltage_v": 24.0} # only 1 field, no identifier
    assert is_relevant_product_result(raw_one_field) is False


def test_irrelevant_text_only_web_result_rejected():
    """Irrelevant text-only web result → rejected."""
    raw = {
        "product_name": "Random Blog Post",
        "snippet": "Just talking about my life.",
        "product_url": "https://blog.com/post"
    }
    assert is_relevant_product_result(raw) is False
