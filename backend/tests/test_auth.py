import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # Ensures all SQLAlchemy models are registered with Base.metadata!
from app.main import app
from app.db import Base, get_db

# Use StaticPool so in-memory SQLite database persists across sessions during tests
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_database():
    """Create fresh database tables before each test and drop them afterwards."""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


def test_successful_registration():
    response = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "username": "alice123",
            "password": "secretpassword",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["username"] == "alice123"
    assert "hashed_password" not in data["user"]  # Password hash MUST NOT be exposed!


def test_duplicate_email_rejection():
    client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "pass123"},
    )
    response = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice2", "password": "pass123"},
    )
    assert response.status_code == 400
    assert "email already exists" in response.json()["detail"].lower()


def test_duplicate_username_rejection():
    client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "pass123"},
    )
    response = client.post(
        "/api/auth/register",
        json={"email": "bob@example.com", "username": "alice", "password": "pass123"},
    )
    assert response.status_code == 400
    assert "username is already taken" in response.json()["detail"].lower()


def test_successful_login():
    client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "pass123"},
    )

    response1 = client.post(
        "/api/auth/login",
        json={"email_or_username": "alice@example.com", "password": "pass123"},
    )
    assert response1.status_code == 200
    assert "access_token" in response1.json()

    response2 = client.post(
        "/api/auth/login",
        json={"email_or_username": "alice", "password": "pass123"},
    )
    assert response2.status_code == 200
    assert "access_token" in response2.json()


def test_incorrect_password_rejection():
    client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "pass123"},
    )
    response = client.post(
        "/api/auth/login",
        json={"email_or_username": "alice", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


def test_get_me_authenticated():
    reg = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "username": "alice", "password": "pass123"},
    ).json()

    token = reg["access_token"]
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["username"] == "alice"


def test_get_me_unauthenticated_rejection():
    response = client.get("/api/auth/me")
    assert response.status_code == 401
