from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.main import app
from app.db import Base, get_db
from app.models.submission import SubmissionRecord
from app.models.source_code import SubmissionSourceCode
from app.collectors.codeforces import CodeforcesAPIError, CodeforcesUserNotFoundError

# Setup isolated in-memory database with StaticPool
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
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


client = TestClient(app)

SAMPLE_CF_API_RESPONSE_HANDLE_A = {
    "status": "OK",
    "result": [
        {
            "id": 10000001,
            "contestId": 1900,
            "creationTimeSeconds": 1710513000,
            "problem": {
                "contestId": 1900,
                "index": "A",
                "name": "Handle A Problem 1",
                "rating": 1200,
                "tags": ["implementation"],
            },
            "programmingLanguage": "GNU C++20 (64 bit)",
            "verdict": "OK",
            "timeConsumedMillis": 100,
            "memoryConsumedBytes": 1000000,
        }
    ],
}

SAMPLE_CF_API_RESPONSE_HANDLE_B = {
    "status": "OK",
    "result": [
        {
            "id": 20000002,
            "contestId": 1901,
            "creationTimeSeconds": 1712772900,
            "problem": {
                "contestId": 1901,
                "index": "B",
                "name": "Handle B Problem 2",
                "rating": 1600,
                "tags": ["dp", "trees"],
            },
            "programmingLanguage": "Python 3",
            "verdict": "OK",
            "timeConsumedMillis": 250,
            "memoryConsumedBytes": 5000000,
        }
    ],
}

SAMPLE_CF_API_RESPONSE_HANDLE_C = {
    "status": "OK",
    "result": [
        {
            "id": 30000003,
            "contestId": 1902,
            "creationTimeSeconds": 1713000000,
            "problem": {
                "contestId": 1902,
                "index": "C",
                "name": "User B Problem 3",
                "rating": 1800,
                "tags": ["math"],
            },
            "programmingLanguage": "Java 11",
            "verdict": "OK",
            "timeConsumedMillis": 180,
            "memoryConsumedBytes": 8000000,
        }
    ],
}


def register_and_login(email: str, username: str) -> str:
    res = client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": "password123"},
    )
    return res.json()["access_token"]


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_connect_codeforces_profile_success(mock_fetch):
    mock_fetch.return_value = SAMPLE_CF_API_RESPONSE_HANDLE_A
    token = register_and_login("user1@example.com", "user1")

    res = client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "handle_a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "codeforces"
    assert data["handle"] == "handle_a"
    assert data["total_submissions_synced"] == 0


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_connect_codeforces_invalid_handle(mock_fetch):
    mock_fetch.side_effect = CodeforcesUserNotFoundError("User not found")
    token = register_and_login("user1@example.com", "user1")

    res = client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "invalid_handle_xyz_999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "invalid codeforces handle" in res.json()["detail"].lower()


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_connect_codeforces_api_failure(mock_fetch):
    mock_fetch.side_effect = CodeforcesAPIError("Network down")
    token = register_and_login("user1@example.com", "user1")

    res = client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "handle_a"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 502
    assert "codeforces api error" in res.json()["detail"].lower()


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_sync_codeforces_submissions_and_deduplication(mock_fetch):
    mock_fetch.return_value = SAMPLE_CF_API_RESPONSE_HANDLE_A
    token = register_and_login("user1@example.com", "user1")

    client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "handle_a"},
        headers={"Authorization": f"Bearer {token}"},
    )

    res1 = client.post(
        "/api/platforms/codeforces/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["fetched_count"] == 1
    assert data1["new_synced_count"] == 1

    res2 = client.post(
        "/api/platforms/codeforces/sync",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["fetched_count"] == 1
    assert data2["new_synced_count"] == 0  # Deduplicated!


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_handle_switch_replaces_old_data_for_user_a(mock_fetch):
    """
    REGRESSION TEST FOR HANDLE SWITCHING BUG:
    Verifies that when User A connects Handle B after Handle A:
    1. Handle A submissions & attached source codes are purged for User A.
    2. Only Handle B submissions are returned in /api/submissions and status.
    3. User B's profile and submissions remain untouched.
    """
    token_a = register_and_login("usera@example.com", "usera")
    token_b = register_and_login("userb@example.com", "userb")

    # 1. User A connects & syncs Handle A
    mock_fetch.return_value = SAMPLE_CF_API_RESPONSE_HANDLE_A
    client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "handle_a"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    client.post(
        "/api/platforms/codeforces/sync",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Attach a source code record to User A's Handle A submission
    subs_a1 = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert len(subs_a1) == 1
    assert subs_a1[0]["problem_title"] == "Handle A Problem 1"
    sub_id_a1 = subs_a1[0]["id"]

    client.post(
        f"/api/submissions/{sub_id_a1}/source-code",
        json={"source_code": "int main() { return 0; }", "language": "cpp"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # 2. User B connects & syncs Handle C
    mock_fetch.return_value = SAMPLE_CF_API_RESPONSE_HANDLE_C
    client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "handle_c"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    client.post(
        "/api/platforms/codeforces/sync",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # Verify User B has Handle C submission
    subs_b1 = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert len(subs_b1) == 1
    assert subs_b1[0]["problem_title"] == "User B Problem 3"

    # 3. User A switches to Handle B & syncs
    mock_fetch.return_value = SAMPLE_CF_API_RESPONSE_HANDLE_B
    client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "handle_b"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    client.post(
        "/api/platforms/codeforces/sync",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # 4. Verify User A's submission list contains ONLY Handle B data (Handle A purged!)
    subs_a2 = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert len(subs_a2) == 1
    assert subs_a2[0]["problem_title"] == "Handle B Problem 2"

    # 5. Verify User B's submission list is UNTOUCHED (User B still has Handle C)
    subs_b2 = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert len(subs_b2) == 1
    assert subs_b2[0]["problem_title"] == "User B Problem 3"

    # 6. Verify User A's old source code was purged cleanly without orphan rows
    db = TestingSessionLocal()
    orphaned_sources = db.query(SubmissionSourceCode).filter(
        SubmissionSourceCode.submission_id == sub_id_a1
    ).all()
    assert len(orphaned_sources) == 0
    db.close()
