import pytest
from app.engine.product_enrichment import ProductEnricher

# Mock httpx.Client for deterministic tests
class MockResponse:
    def __init__(self, content, status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("HTTP Error")

class MockClient:
    def __init__(self, *args, **kwargs):
        pass
    def close(self):
        pass
    def get(self, url, *args, **kwargs):
        if "html_full" in url:
            return MockResponse(b"<html><body>Rated voltage: 12 V Output speed: 40 RPM Continuous output torque: 1.15 Nm</body></html>")
        if "html_missing_torque" in url:
            return MockResponse(b"<html><body>Rated voltage: 12 V Output speed: 40 RPM Torque: not specified</body></html>")
        if "html_24v" in url:
            return MockResponse(b"<html><body>Rated voltage: 24 V Output speed: 40 RPM Continuous output torque: 1.15 Nm</body></html>")
        if "html_unlabeled" in url:
            return MockResponse(b"<html><body>Product Name: 1308-24-100<br>This is a great product.</body></html>")
        if "pdf_datasheet" in url:
            # We mock the PDF extraction directly in the test to avoid making real pdfs
            pass
        if "404_page" in url:
            return MockResponse(b"", status_code=404)
        if "multiple_torques" in url:
            return MockResponse(b"<html><body>Rated voltage 24V, Output speed 40 RPM, continuous output torque 1.15 Nm, stall torque 10 Nm</body></html>")
        if "motor_only" in url:
            # Motor only
            return MockResponse(b"<html><body>Motor rated voltage 12V, rated speed 3000 RPM, continuous torque 0.05 Nm</body></html>")
        if "gearmotor" in url:
            return MockResponse(b"<html><body>Gearmotor rated voltage 12V, output speed 40 RPM, output torque 1.5 Nm, gear ratio 75:1</body></html>")
        return MockResponse(b"<html></html>")

@pytest.fixture
def enricher(monkeypatch):
    e = ProductEnricher()
    e.client = MockClient()
    return e

def test_1_html_full(enricher):
    c = [{"product_url": "http://test.com/html_full"}]
    res = enricher.enrich(c)[0]
    assert res["voltage_v"] == 12.0
    assert res["nominal_speed_rpm"] == 40.0
    assert res["nominal_torque_nm"] == 1.15
    assert res["verification_status"] == "ENRICHED_FROM_SOURCE"

def test_2_missing_torque(enricher):
    c = [{"product_url": "http://test.com/html_missing_torque"}]
    res = enricher.enrich(c)[0]
    assert res.get("nominal_torque_nm") is None
    assert res["voltage_v"] == 12.0

def test_3_24v_product(enricher):
    c = [{"product_url": "http://test.com/html_24v"}]
    res = enricher.enrich(c)[0]
    assert res["voltage_v"] == 24.0

def test_4_unlabeled(enricher):
    c = [{"product_url": "http://test.com/html_unlabeled"}]
    res = enricher.enrich(c)[0]
    assert res.get("voltage_v") is None
    assert res.get("nominal_speed_rpm") is None

def test_5_pdf_datasheet(enricher, monkeypatch):
    # Mock _extract_specifications for PDF to simulate pypdf success
    c = [{"product_url": "http://test.com/pdf_datasheet.pdf"}]
    # We'll just patch the client to return a mock content type
    def mock_get(*args, **kwargs):
        return MockResponse(b"Dummy PDF", headers={"content-type": "application/pdf"})
    enricher.client.get = mock_get
    
    # And mock pypdf
    class MockPdfPage:
        def extract_text(self):
            return "Rated voltage 12 V Output speed 40 RPM Continuous torque 1.15 Nm"
    class MockPdfReader:
        def __init__(self, *args, **kwargs):
            self.pages = [MockPdfPage()]
    import app.engine.product_enrichment
    monkeypatch.setattr(app.engine.product_enrichment, "PdfReader", MockPdfReader)
    
    res = enricher.enrich(c)[0]
    assert res["voltage_v"] == 12.0
    assert res["nominal_speed_rpm"] == 40.0
    assert res["nominal_torque_nm"] == 1.15

def test_6_pdf_no_text(enricher, monkeypatch):
    c = [{"product_url": "http://test.com/pdf_notext.pdf"}]
    def mock_get(*args, **kwargs):
        return MockResponse(b"Dummy PDF", headers={"content-type": "application/pdf"})
    enricher.client.get = mock_get
    
    class MockPdfPage:
        def extract_text(self):
            return None # Image only
    class MockPdfReader:
        def __init__(self, *args, **kwargs):
            self.pages = [MockPdfPage()]
    import app.engine.product_enrichment
    monkeypatch.setattr(app.engine.product_enrichment, "PdfReader", MockPdfReader)
    
    res = enricher.enrich(c)[0]
    assert res.get("voltage_v") is None

def test_7_http_404(enricher):
    c = [{"product_url": "http://test.com/404_page"}]
    res = enricher.enrich(c)[0]
    assert res.get("verification_status") is None

def test_8_multiple_torques(enricher):
    c = [{"product_url": "http://test.com/multiple_torques"}]
    res = enricher.enrich(c)[0]
    assert res["nominal_torque_nm"] == 1.15 # Did not pick up 10 Nm stall

def test_9_motor_only(enricher):
    c = [{"product_url": "http://test.com/motor_only"}]
    res = enricher.enrich(c)[0]
    # It extracts what it finds
    assert res["nominal_speed_rpm"] == 3000.0
    assert res["nominal_torque_nm"] == 0.05

def test_10_gearmotor(enricher):
    c = [{"product_url": "http://test.com/gearmotor"}]
    res = enricher.enrich(c)[0]
    assert res["gear_ratio"] == 75.0
    assert res["nominal_torque_nm"] == 1.5

def test_11_provenance(enricher):
    c = [{"product_url": "http://test.com/html_full"}]
    res = enricher.enrich(c)[0]
    assert res["specification_source_url"] == "http://test.com/html_full"
    assert res["specification_source"] == "Source Document Extraction"
    assert "extracted_at" in res
