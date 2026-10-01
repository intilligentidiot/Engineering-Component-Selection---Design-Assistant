import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.database import Base, engine, get_db
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

Base.metadata.create_all(bind=test_engine)

# Seed the test database
from app.database.seed import seed_database
seed_database(custom_engine=test_engine, custom_session_local=TestingSessionLocal)
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def cleanup():
    yield
    # We could clean up the DB here if needed
