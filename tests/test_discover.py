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
    assert raw[0]["manufacturer"] == "Maxongroup"
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


