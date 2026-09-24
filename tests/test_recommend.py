import pytest
from app.database.database import SessionLocal
from app.database.seed import seed_database
from app.engine.recommend import get_recommendations

@pytest.fixture(scope="module")
def db_session():
    seed_database()
    db = SessionLocal()
    yield db
    db.close()

def test_recommendation_engine_finds_match(db_session):
    # Requirement: 500 RPM, 1.0 Nm Torque, SF 1.2, 24V max
    # We seeded the DB with a Maxon EC-max 40 (6100 RPM, 0.12 Nm nominal) 
    # and a GPX32_103 (103 ratio, 0.65 eff, 8Nm max)
    # Output Speed: 6100 / 103 = 59.2 RPM (too low for 500 RPM)
    
    # Let's find something suitable for high torque, low speed
    # Requirement: 50 RPM, 2.0 Nm Torque, SF 1.5, 24V max
    # Design Torque = 3.0 Nm
    # Required Power = 3.0 * 50 / 9.549 = 15.7 W
    
    recommendations = get_recommendations(
        db=db_session,
        required_speed_rpm=50.0,
        required_torque_nm=2.0,
        service_factor=1.5,
        max_voltage_v=24.0,
        top_n=5
    )
    
    assert len(recommendations) > 0, "Engine should find at least one valid combination"
    
    best = recommendations[0]
    
    assert best["performance"]["output_speed_rpm"] >= 50.0
    assert best["performance"]["output_torque_nm"] >= 3.0
    assert best["motor"]["voltage_v"] <= 24.0
    
def test_recommendation_engine_rejects_overvoltage(db_session):
    # Require strict 12V max
    recommendations = get_recommendations(
        db=db_session,
        required_speed_rpm=50.0,
        required_torque_nm=0.5,
        service_factor=1.0,
        max_voltage_v=12.0,
        top_n=10
    )
    
    for rec in recommendations:
        assert rec["motor"]["voltage_v"] <= 12.0

def test_recommendation_engine_rejects_impossible_requirements(db_session):
    # Requirement: 10,000 RPM AND 1,000 Nm Torque (Impossible for these small motors)
    recommendations = get_recommendations(
        db=db_session,
        required_speed_rpm=10000.0,
        required_torque_nm=1000.0,
        service_factor=2.0,
        max_voltage_v=24.0
    )
    
    assert len(recommendations) == 0, "Engine should reject combinations that exceed physical limits"
