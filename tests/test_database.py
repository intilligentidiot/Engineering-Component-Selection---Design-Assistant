import pytest
from app.database.database import SessionLocal
from app.database.models import Manufacturer, Motor, Gearbox
from app.database.seed import seed_database

@pytest.fixture(scope="module")
def db_session():
    # We can use the actual seed script since we want to test its output
    seed_database()
    
    db = SessionLocal()
    yield db
    db.close()

def test_database_seed_manufacturers(db_session):
    manufacturers = db_session.query(Manufacturer).all()
    assert len(manufacturers) >= 3
    names = [m.name for m in manufacturers]
    assert "Maxon" in names
    assert "Faulhaber" in names

def test_database_seed_motors(db_session):
    motors = db_session.query(Motor).all()
    assert len(motors) == 20
    
    # Verify provenance
    first_motor = motors[0]
    assert first_motor.verification_status == "Verified"
    assert first_motor.source is not None

def test_database_seed_gearboxes(db_session):
    gearboxes = db_session.query(Gearbox).all()
    assert len(gearboxes) == 20
    
    # Verify relations
    first_gb = gearboxes[0]
    assert first_gb.manufacturer is not None
    assert first_gb.efficiency <= 1.0
