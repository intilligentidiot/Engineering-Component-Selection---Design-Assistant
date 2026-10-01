import pytest
from app.database.database import SessionLocal
from app.database.models import DiscoveredComponent
from app.engine.discover import discover_and_evaluate_components, SearchProvider

class DeduplicationTestProvider(SearchProvider):
    def __init__(self, results):
        self._results = results
        
    def search(self, query: str, limit: int = 10):
        return self._results


@pytest.fixture
def clean_db():
    db = SessionLocal()
    from app.database.models import DiscoverySearchCache
    # Clear out tables for a clean state
    db.query(DiscoveredComponent).delete()
    db.query(DiscoverySearchCache).delete()
    db.commit()
    yield db
    db.close()


def test_deduplication_same_manufacturer_and_part_number(clean_db):
    """1. Same manufacturer + same part number → update existing product."""
    provider1 = DeduplicationTestProvider([
        {
            "manufacturer": "Oriental Motor",
            "part_number": "ABC123",
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81,
            "product_name": "Motor V1",
            "source": "Initial Source"
        }
    ])
    
    discover_and_evaluate_components(
        db=clean_db, required_speed_rpm=100.0, required_torque_nm=1.0,
        service_factor=1.0, max_voltage_v=24.0, provider=provider1
    )
    
    count_after_first = clean_db.query(DiscoveredComponent).count()
    assert count_after_first == 1
    
    # Run again with same mfg and part_number
    provider2 = DeduplicationTestProvider([
        {
            "manufacturer": "Oriental Motor",
            "part_number": "ABC123",
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81,
            "product_name": "Motor V2",  # Changed name
            "source": "New Source"
        }
    ])
    
    discover_and_evaluate_components(
        db=clean_db, required_speed_rpm=100.0, required_torque_nm=1.0,
        service_factor=1.0, max_voltage_v=24.0, provider=provider2
    )
    
    count_after_second = clean_db.query(DiscoveredComponent).count()
    assert count_after_second == 1, "Should merge into existing product"


def test_deduplication_different_manufacturer_same_part_number(clean_db):
    """2. Different manufacturer + same part number → separate products."""
    provider = DeduplicationTestProvider([
        {
            "manufacturer": "Oriental Motor",
            "part_number": "ABC123",
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81
        },
        {
            "manufacturer": "Another Manufacturer",
            "part_number": "ABC123",  # Same part number!
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81
        }
    ])
    
    discover_and_evaluate_components(
        db=clean_db, required_speed_rpm=100.0, required_torque_nm=1.0,
        service_factor=1.0, max_voltage_v=24.0, provider=provider
    )
    
    count = clean_db.query(DiscoveredComponent).count()
    assert count == 2, "Different manufacturers with same part number should be separate products"


def test_deduplication_missing_manufacturer(clean_db):
    """3. Missing manufacturer → do not incorrectly merge."""
    provider = DeduplicationTestProvider([
        {
            "manufacturer": None,
            "part_number": "MISSING-MFG-01",
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81
        },
        {
            "manufacturer": None,
            "part_number": "MISSING-MFG-01",
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81
        }
    ])
    
    discover_and_evaluate_components(
        db=clean_db, required_speed_rpm=100.0, required_torque_nm=1.0,
        service_factor=1.0, max_voltage_v=24.0, provider=provider
    )
    
    # Since manufacturer is missing, they should not merge
    count = clean_db.query(DiscoveredComponent).count()
    assert count == 2, "Should not merge if manufacturer is missing"


def test_deduplication_missing_part_number(clean_db):
    """4. Missing part number → do not incorrectly merge."""
    provider = DeduplicationTestProvider([
        {
            "manufacturer": "Generic Brand",
            "part_number": None,
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81
        },
        {
            "manufacturer": "Generic Brand",
            "part_number": None,
            "voltage_v": 24.0, "power_w": 30.0, "nominal_speed_rpm": 3000.0,
            "nominal_torque_nm": 0.1, "gear_ratio": 30.0, "efficiency": 0.81
        }
    ])
    
    discover_and_evaluate_components(
        db=clean_db, required_speed_rpm=100.0, required_torque_nm=1.0,
        service_factor=1.0, max_voltage_v=24.0, provider=provider
    )
    
    # Since part number is missing, they should not merge
    count = clean_db.query(DiscoveredComponent).count()
    assert count == 2, "Should not merge if part number is missing"
