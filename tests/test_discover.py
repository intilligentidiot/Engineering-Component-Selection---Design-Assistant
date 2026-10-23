import pytest
from app.database.database import SessionLocal
from app.database.seed import seed_database
from app.database.models import DiscoveredComponent
from app.engine.discover import (
    SearchProvider,
    MockIndustrialSearchProvider,
    construct_engineering_query,
    discover_and_evaluate_components,
    sanitize_text,
    sanitize_url
)

@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()
    yield db
    db.close()

# ── 1. Query Construction ────────────────────────────────────

def test_construct_engineering_query():
    q = construct_engineering_query(required_torque_nm=15.0, required_speed_rpm=60.0, max_voltage_v=24.0)
    assert "24V" in q
    assert "15.0 Nm" in q
    assert "60 RPM" in q
    assert "best motor" not in q.lower()
    assert "recommendation" not in q.lower()

# ── 2. Sanitization ──────────────────────────────────────────

def test_sanitization():
    assert sanitize_text("<b>Motor 100</b>") == "Motor 100"
    assert sanitize_text("<script>alert(1)</script>Test") == "Test"
    assert sanitize_url("https://example.com/datasheet.pdf") == "https://example.com/datasheet.pdf"
    assert sanitize_url("javascript:alert(1)") is None

# ── 3. Search Provider Abstraction & Mocking ─────────────────

class CustomMockProvider(SearchProvider):
    def search(self, query: str, limit: int = 10):
        return [
            {
                "manufacturer": "TestCorp",
                "product_name": "Test Gearmotor 24V",
                "model": "TC-24V-100",
                "part_number": "TC-24V-100",
                "product_url": "https://testcorp.com/product",
                "datasheet_url": "https://testcorp.com/ds.pdf",
                "image_url": "https://testcorp.com/img.jpg",
                "voltage_v": 24.0,
                "power_w": 100.0,
                "nominal_speed_rpm": 2000.0,
                "nominal_torque_nm": 0.5,
                "gear_ratio": 20.0,
                "efficiency": 0.85,
                "max_output_torque_nm": 10.0,
                "availability_status": "IN_STOCK",
                "price": 150.0,
                "price_currency": "USD",
                "cad_available": "True",
                "cad_url": "https://testcorp.com/cad.step",
                "source": "TestCorp Supplier"
            },
            {
                "manufacturer": "IncompleteCorp",
                "product_name": "Incomplete Motor",
                "model": "INC-01",
                "part_number": "INC-01",
                "voltage_v": 24.0,
                "power_w": None, # Missing specs
                "nominal_speed_rpm": None,
                "gear_ratio": 10.0,
                "efficiency": None,
                "source": "Incomplete Feed"
            }
        ]

def test_discover_and_evaluate_components(db_session):
    provider = CustomMockProvider()
    results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=100.0,
        required_torque_nm=5.0,
        service_factor=1.2,
        max_voltage_v=24.0,
        provider=provider
    )
    
    assert len(results) == 2
    
    # Check Complete Product Evaluation (Deterministic Math applied)
    complete = results[0]
    assert complete["manufacturer"] == "TestCorp"
    assert complete["source_type"] == "INTERNET"
    assert complete["verification"]["data_status"] == "DISCOVERED"
    assert complete["engineering_status"] in ["MEETS", "DOES_NOT_MEET"]
    assert complete["performance"]["output_speed_rpm"] == 100.0 # 2000 / 20 = 100
    assert complete["performance"]["output_torque_nm"] == 8.5 # 0.5 * 20 * 0.85 = 8.5
    assert complete["calculation_trace"]["gearbox_output_torque"]["status"] == "MEETS"
    assert complete["cad"]["available"] is True
    
    # Check Incomplete Product Evaluation (DATA_INCOMPLETE handling)
    incomplete = results[1]
    assert incomplete["manufacturer"] == "IncompleteCorp"
    assert incomplete["verification"]["data_status"] == "DATA_INCOMPLETE"
    assert incomplete["engineering_status"] == "DATA_INCOMPLETE"

# ── 4. Graceful Error Handling Test ──────────────────────────

class FailingProvider(SearchProvider):
    def search(self, query: str, limit: int = 10):
        raise ConnectionError("External API provider unreachable")

def test_internet_discovery_failure_graceful_handling(db_session):
    failing_provider = FailingProvider()
    results = discover_and_evaluate_components(
        db=db_session,
        required_speed_rpm=100.0,
        required_torque_nm=6.0,
        service_factor=1.2,
        max_voltage_v=24.0,
        provider=failing_provider
    )
    # Should safely return empty list without throwing an unhandled exception
    assert results == []

# ── 5. SerpApi Provider Tests (Mocked) ───────────────────────

def test_serpapi_key_missing(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    from app.engine.search_provider import SerpApiSearchProvider
    with pytest.raises(ValueError, match="INTERNET_SEARCH_NOT_CONFIGURED"):
        SerpApiSearchProvider()

def test_serpapi_search_provider_mocked(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "mock_key_for_unit_tests")
    
    mock_dict_response = {
        "organic_results": [
            {
                "title": "Maxon DC Motor 24V 150 Nm 60 RPM",
                "link": "https://www.maxongroup.com/maxon/view/product/motor123",
                "snippet": "High performance 24V industrial gear motor.",
                "displayed_link": "maxongroup.com"
            }
        ]
    }

    class MockClient:
        def __init__(self, api_key=None):
            pass
        def search(self, params):
            return mock_dict_response

    monkeypatch.setattr("serpapi.Client", MockClient)

    from app.engine.search_provider import SerpApiSearchProvider
    provider = SerpApiSearchProvider()
    raw = provider.search("24V industrial DC motor gearbox 1.0 Nm 35 RPM", limit=5)

    assert len(raw) == 1
    # The display link is not a maker name: the readable name comes from the product URL
    from app.engine.discover import clean_manufacturer
    assert raw[0]["manufacturer"] is None
    assert clean_manufacturer(raw[0]) == "maxongroup.com"
    assert raw[0]["product_name"] == "Maxon DC Motor 24V 150 Nm 60 RPM"
    assert raw[0]["product_url"] == "https://www.maxongroup.com/maxon/view/product/motor123"


# ── 6. Task 10 URL Handling & Regression Tests ───────────────

def test_sanitize_url_valid_direct():
    assert sanitize_url("https://www.maxongroup.com/product/12345") == "https://www.maxongroup.com/product/12345"
    assert sanitize_url("http://dunkermotoren.com/spec?id=99&type=dc") == "http://dunkermotoren.com/spec?id=99&type=dc"

def test_sanitize_url_missing_or_invalid():
    assert sanitize_url(None) is None
    assert sanitize_url("") is None
    assert sanitize_url("javascript:alert('xss')") is None
    assert sanitize_url("/relative/path/file.pdf") is None
    assert sanitize_url("ftp://files.example.com") is None

def test_pdf_datasheet_url_extraction(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "mock_key_for_unit_tests")
    mock_dict_response = {
        "organic_results": [
            {
                "title": "Oriental Motor BLH230K Datasheet PDF",
                "link": "https://www.orientalmotor.com/pdf/BLH230K.pdf",
                "snippet": "Datasheet document for BLH230K motor."
            }
        ]
    }
    class MockClient:
        def __init__(self, api_key=None):
            pass
        def search(self, params):
            return mock_dict_response

    monkeypatch.setattr("serpapi.Client", MockClient)
    from app.engine.search_provider import SerpApiSearchProvider
    provider = SerpApiSearchProvider()
    raw = provider.search("query", limit=1)

    assert raw[0]["datasheet_url"] == "https://www.orientalmotor.com/pdf/BLH230K.pdf"
    assert raw[0]["product_url"] is None # Should NOT fabricate product webpage if link is a PDF

def test_no_fabricated_urls(db_session):
    # Ensure missing URLs remain None and are not manually constructed
    raw_item = {
        "manufacturer": "TestCorp",
        "product_name": "Test Motor",
        "product_url": None,
        "datasheet_url": None
    }
    cleaned_url = sanitize_url(raw_item["product_url"])
    cleaned_ds = sanitize_url(raw_item["datasheet_url"])
    assert cleaned_url is None
    assert cleaned_ds is None




# ── Real-search fixes (live SerpApi results reviewed 2026-10-19) ──

from app.engine.discover import clean_manufacturer, is_non_product_page, is_relevant_product_result


def test_manufacturer_from_link_not_display_text():
    assert clean_manufacturer({"manufacturer": "Https://www", "product_url":
        "https://www.omc-stepperonline.com/24v-60w-58-9rpm-geared-brushless-dc-motor"}) == "omc-stepperonline.com"
    assert clean_manufacturer({"manufacturer": None, "product_url":
        "https://www.amazon.com/Makermotor-Shaft-Reversible-Electric-Motor/dp/B084KY41Q1"}) == "Maker not stated (sold on amazon.com)"
    assert clean_manufacturer({"manufacturer": "Nanotec", "product_url": "https://www.nanotec.com/x"}) == "Nanotec"


@pytest.mark.parametrize("raw", [
    {"product_name": "24V DC Gear Motor with High Torque and Low RPM", "manufacturer": "17K+ views · 4 years ago",
     "product_url": "https://www.youtube.com/watch?v=Up1KFcZ8H08"},
    {"product_name": "25+ DC 24V Industrial Electric Gearmotors for sale",
     "product_url": "https://www.ebay.com/b/DC-24V-Industrial-Electric-Gearmotors/65452/bn_73765955"},
    {"product_name": "24V DC Motor with Gearbox for High Torque",
     "product_url": "https://www.zwgearbox.com/blog/24v-dc-motor-gearbox-high-torque"},
])
def test_non_product_pages_are_rejected(raw):
    assert is_non_product_page(raw)
    assert not is_relevant_product_result(raw)


def test_product_page_still_accepted():
    raw = {"product_name": "24V 60W 58.9RPM Geared Brushless DC Motor 7.00Nm",
           "product_url": "https://www.omc-stepperonline.com/24v-60w-58-9rpm-geared-brushless-dc-motor"}
    assert not is_non_product_page(raw)
    assert is_relevant_product_result(raw)


class GearmotorListingProvider(SearchProvider):
    """A complete gearmotor that states its OUTPUT speed and torque, no ratio or efficiency."""
    def search(self, query, limit=10):
        return [{"manufacturer": None, "product_name": "24V 60W 58.9RPM Geared Brushless DC Motor 7.00Nm Planetary Gearbox",
                 "part_number": "M52B60-G52-50", "product_url": "https://www.omc-stepperonline.com/m52b60-g52",
                 "voltage_v": 24.0, "power_w": 60.0, "nominal_speed_rpm": 58.9, "nominal_torque_nm": 7.0,
                 "gear_ratio": None, "efficiency": None, "max_output_torque_nm": None, "source": "test"}]


def test_complete_gearmotor_judged_on_listed_output(db_session):
    results = discover_and_evaluate_components(
        db=db_session, required_speed_rpm=50.0, required_torque_nm=2.0, service_factor=1.5,
        max_voltage_v=24.0, provider=GearmotorListingProvider(), top_n=5)
    r = next(x for x in results if x["part_number"] == "M52B60-G52-50")
    assert r["engineering_status"] == "MEETS"                 # 7 N·m ≥ 3 N·m at 58.9 rpm (within +50 %)
    assert r["rating_basis"] == "OUTPUT_AS_LISTED"
    assert "as listed" in r["calculation_trace"]["gearbox_output_torque"]["formula"]
    assert r["manufacturer"] == "omc-stepperonline.com"


def test_gearmotor_too_weak_is_not_meets(db_session):
    results = discover_and_evaluate_components(
        db=db_session, required_speed_rpm=50.0, required_torque_nm=6.0, service_factor=1.5,
        max_voltage_v=24.0, provider=GearmotorListingProvider(), top_n=5)
    assert not any(x["part_number"] == "M52B60-G52-50" and x["engineering_status"] == "MEETS" for x in results)


# ── Listings that state a torque too small for the job are dropped ─────

from app.engine.discover import listed_max_torque_nm


@pytest.mark.parametrize("text,nm", [
    ("Brushed 24V DC Gear Motor 22Kg.cm/6.4RPM w/ 720:1 Gearbox", 2.157),
    ("DC Gearmotor, 20 in-lb Max. Torque, 139 RPM", 2.260),
    ("1/4 Hp, 125 Rpm, 20:1, 419 Lb-in", 47.34),
    ("150 ft-lbs worm gear reducer", 203.4),
    ("Gearmotor 1200 Nm output at 20 rpm", 1200.0),
    ("rated torque: 2,5 N\u00b7m", 2.5),
])
def test_listed_torque_in_seller_units(text, nm):
    assert round(listed_max_torque_nm(text), 1) == round(nm, 1)


def test_no_torque_stated():
    assert listed_max_torque_nm("240 Series Super Sealed Industrial DC Gear Motor") is None
    assert listed_max_torque_nm("100 mm shaft, 5 nmax") is None


class SmallListingsProvider(SearchProvider):
    """Incomplete listings: two state a torque far below the need, one states none."""
    def search(self, query, limit=10):
        base = {"manufacturer": None, "voltage_v": None, "power_w": None, "nominal_speed_rpm": None,
                "nominal_torque_nm": None, "gear_ratio": None, "efficiency": None, "source": "test"}
        return [
            {**base, "product_name": "Brushed 24V DC Gear Motor 22Kg.cm/6.4RPM w/ 720:1 Gearbox",
             "part_number": "SMALL-1", "product_url": "https://www.example-motors.com/small-1"},
            {**base, "product_name": "DC Gearmotor, 20 in-lb Max. Torque, 139 RPM",
             "part_number": "SMALL-2", "product_url": "https://www.example-motors.com/small-2"},
            {**base, "product_name": "Industrial helical gear motor 230 V",
             "part_number": "UNKNOWN-1", "product_url": "https://www.example-motors.com/unknown-1"},
        ]


def test_listings_stating_too_little_torque_are_dropped(db_session):
    results = discover_and_evaluate_components(
        db=db_session, required_speed_rpm=21.0, required_torque_nm=733.0, service_factor=1.75,
        max_voltage_v=230.0, provider=SmallListingsProvider(), top_n=5)
    parts = {x["part_number"] for x in results}
    assert "SMALL-1" not in parts and "SMALL-2" not in parts
    assert "UNKNOWN-1" in parts      # no torque stated: kept, shown as data incomplete
