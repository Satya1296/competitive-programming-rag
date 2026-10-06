import os
import shutil
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.main import app
from app.db import Base, get_db
from app.models.user import User
from app.models.submission import SubmissionRecord
from app.models.source_code import SubmissionSourceCode
from app.models.profile import PlatformProfile
from app.auth.jwt import create_access_token
from app.collectors.leetcode import LeetCodeCollector, LeetCodeUserNotFoundError
from app.collectors.codechef import CodeChefCollector, CodeChefUserNotFoundError, CodeChefRateLimitError

TEST_DATABASE_URL = "sqlite:///:memory:"
TEST_CHROMA_DIR = "backend/data/test_multi_platform_chromadb"

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
    if os.path.exists(TEST_CHROMA_DIR):
        shutil.rmtree(TEST_CHROMA_DIR, ignore_errors=True)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists(TEST_CHROMA_DIR):
        shutil.rmtree(TEST_CHROMA_DIR, ignore_errors=True)


client = TestClient(app)

SAMPLE_CF_AUTHENTICATED_RESPONSE = {
    "status": "OK",
    "result": [
        {
            "id": 881001,
            "contestId": 1900,
            "creationTimeSeconds": 1710513000,
            "problem": {
                "contestId": 1900,
                "index": "A",
                "name": "Authenticated Codeforces DP",
                "rating": 1400,
                "tags": ["dp", "trees"],
            },
            "programmingLanguage": "GNU C++20",
            "verdict": "OK",
            "timeConsumedMillis": 50,
            "memoryConsumedBytes": 2048,
            "source": "#include <iostream>\nusing namespace std;\nint main() { cout << \"Authenticated CF Source Code\"; return 0; }",
        }
    ],
}

SAMPLE_LEETCODE_GRAPHQL_RESPONSE = {
    "data": {
        "matchedUser": {
            "username": "lc_coder",
            "profile": {"realName": "LC Coder", "ranking": 1000}
        },
        "recentSubmissionList": [
            {
                "title": "Two Sum",
                "titleSlug": "two-sum",
                "timestamp": "1710514000",
                "statusDisplay": "Accepted",
                "lang": "python3"
            }
        ]
    }
}

SAMPLE_CODECHEF_RESPONSE = {
    "status": "OK",
    "username": "chef_user",
    "result": [
        {
            "id": "FLOW001_2026-09-25",
            "problemCode": "FLOW001",
            "problemTitle": "Add Two Numbers",
            "language": "C++",
            "verdict": "ACCEPTED",
            "submitted_at": "2026-09-25T10:00:00Z"
        }
    ]
}


def register_user(email: str, username: str) -> tuple[str, str]:
    res = client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": "Password123!"},
    )
    data = res.json()
    return data["access_token"], data["user"]["id"]


# -----------------------------------------------------------------------------
# MULTI-PLATFORM TESTS
# -----------------------------------------------------------------------------

@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_codeforces_authenticated_source_retrieval(mock_cf_fetch):
    mock_cf_fetch.return_value = SAMPLE_CF_AUTHENTICATED_RESPONSE
    token, user_id = register_user("cf_auth@test.com", "cf_auth_user")
    headers = {"Authorization": f"Bearer {token}"}

    res_conn = client.post(
        "/api/platforms/codeforces/connect",
        json={"handle": "tourist", "api_key": "fake_key_123", "api_secret": "fake_secret_456"},
        headers=headers,
    )
    assert res_conn.status_code == 200
    assert res_conn.json()["has_api_credentials"] is True

    res_sync = client.post("/api/platforms/codeforces/sync", headers=headers)
    assert res_sync.status_code == 200
    assert res_sync.json()["new_synced_count"] == 1

    subs = client.get("/api/submissions", headers=headers).json()
    assert len(subs) == 1
    sub = subs[0]
    assert sub["has_source_code"] is True
    assert sub["code_source"] == "api_authenticated"
    assert "Authenticated CF Source Code" in sub["code"]


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_codeforces_metadata_only_fallback(mock_cf_fetch):
    mock_cf_fetch.return_value = {
        "status": "OK",
        "result": [
            {
                "id": 881002,
                "contestId": 1900,
                "creationTimeSeconds": 1710513000,
                "problem": {"contestId": 1900, "index": "B", "name": "Public CF Problem", "rating": 1200},
                "programmingLanguage": "GNU C++20",
                "verdict": "OK",
            }
        ]
    }
    token, user_id = register_user("cf_meta@test.com", "cf_meta_user")
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/platforms/codeforces/connect", json={"handle": "tourist"}, headers=headers)
    client.post("/api/platforms/codeforces/sync", headers=headers)

    subs = client.get("/api/submissions", headers=headers).json()
    assert len(subs) == 1
    sub = subs[0]
    assert sub["has_source_code"] is False
    assert sub["code_source"] == "api_metadata"
    assert "// Source code not provided" in sub["code"]


@patch("app.main.LeetCodeCollector.fetch_submissions")
def test_leetcode_metadata_sync(mock_lc_fetch):
    mock_lc_fetch.return_value = SAMPLE_LEETCODE_GRAPHQL_RESPONSE
    token, user_id = register_user("lc@test.com", "lc_user")
    headers = {"Authorization": f"Bearer {token}"}

    res_conn = client.post("/api/platforms/leetcode/connect", json={"handle": "lc_coder"}, headers=headers)
    assert res_conn.status_code == 200

    res_sync = client.post("/api/platforms/leetcode/sync", headers=headers)
    assert res_sync.status_code == 200
    assert res_sync.json()["new_synced_count"] == 1

    subs = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs) == 1
    sub = subs[0]
    assert sub["platform"] == "leetcode"
    assert sub["problem_title"] == "Two Sum"
    assert sub["has_source_code"] is False


@patch("app.main.LeetCodeCollector.fetch_submissions")
def test_leetcode_invalid_username_rejection(mock_lc_fetch):
    mock_lc_fetch.side_effect = LeetCodeUserNotFoundError("LeetCode username 'fake_user_999' not found or does not exist.")
    token, _ = register_user("lc_invalid@test.com", "lc_invalid_user")
    headers = {"Authorization": f"Bearer {token}"}

    res_conn = client.post("/api/platforms/leetcode/connect", json={"handle": "fake_user_999"}, headers=headers)
    assert res_conn.status_code == 400
    assert "Invalid LeetCode username" in res_conn.json()["detail"]


@patch("app.main.CodeChefCollector.fetch_submissions")
def test_codechef_metadata_sync(mock_cc_fetch):
    mock_cc_fetch.return_value = SAMPLE_CODECHEF_RESPONSE
    token, user_id = register_user("cc@test.com", "cc_user")
    headers = {"Authorization": f"Bearer {token}"}

    res_conn = client.post("/api/platforms/codechef/connect", json={"handle": "chef_coder"}, headers=headers)
    assert res_conn.status_code == 200

    res_sync = client.post("/api/platforms/codechef/sync", headers=headers)
    assert res_sync.status_code == 200

    subs = client.get("/api/submissions?platform=codechef", headers=headers).json()
    assert len(subs) == 1
    sub = subs[0]
    assert sub["platform"] == "codechef"
    assert sub["problem_title"] == "Add Two Numbers"
    assert sub["has_source_code"] is False


@patch("app.main.CodeChefCollector.fetch_submissions")
def test_codechef_invalid_username_rejection(mock_cc_fetch):
    mock_cc_fetch.side_effect = CodeChefUserNotFoundError("CodeChef username 'invalid_chef_xyz' not found.")
    token, _ = register_user("cc_invalid@test.com", "cc_invalid_user")
    headers = {"Authorization": f"Bearer {token}"}

    res_conn = client.post("/api/platforms/codechef/connect", json={"handle": "invalid_chef_xyz"}, headers=headers)
    assert res_conn.status_code == 400
    assert "Invalid CodeChef username" in res_conn.json()["detail"]


@patch("app.main.CodeforcesCollector.fetch_submissions")
@patch("app.main.LeetCodeCollector.fetch_submissions")
@patch("app.main.CodeChefCollector.fetch_submissions")
def test_multi_platform_filtering_and_stats(mock_cc, mock_lc, mock_cf):
    mock_cf.return_value = SAMPLE_CF_AUTHENTICATED_RESPONSE
    mock_lc.return_value = SAMPLE_LEETCODE_GRAPHQL_RESPONSE
    mock_cc.return_value = SAMPLE_CODECHEF_RESPONSE

    token, user_id = register_user("multi@test.com", "multi_user")
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/platforms/codeforces/connect", json={"handle": "cf_h"}, headers=headers)
    client.post("/api/platforms/codeforces/sync", headers=headers)

    client.post("/api/platforms/leetcode/connect", json={"handle": "lc_h"}, headers=headers)
    client.post("/api/platforms/leetcode/sync", headers=headers)

    client.post("/api/platforms/codechef/connect", json={"handle": "cc_h"}, headers=headers)
    client.post("/api/platforms/codechef/sync", headers=headers)

    all_subs = client.get("/api/submissions?platform=all", headers=headers).json()
    cf_subs = client.get("/api/submissions?platform=codeforces", headers=headers).json()
    lc_subs = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    cc_subs = client.get("/api/submissions?platform=codechef", headers=headers).json()

    assert len(all_subs) == 3
    assert len(cf_subs) == 1
    assert len(lc_subs) == 1
    assert len(cc_subs) == 1

    stats = client.get("/api/stats", headers=headers).json()
    assert stats["total_submissions"] == 3
    assert stats["codeforces_count"] == 1
    assert stats["leetcode_count"] == 1
    assert stats["codechef_count"] == 1


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_user_isolation_across_platforms(mock_cf):
    mock_cf.return_value = SAMPLE_CF_AUTHENTICATED_RESPONSE

    token_a, user_a_id = register_user("iso_a@test.com", "iso_user_a")
    token_b, user_b_id = register_user("iso_b@test.com", "iso_user_b")

    client.post("/api/platforms/codeforces/connect", json={"handle": "user_a_cf"}, headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/platforms/codeforces/sync", headers={"Authorization": f"Bearer {token_a}"})

    subs_b = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert len(subs_b) == 0

    stats_b = client.get("/api/stats", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert stats_b["total_submissions"] == 0


def test_database_schema_migration_and_data_preservation():
    from sqlalchemy import create_engine, text, inspect
    from app.db import run_migrations

    legacy_engine = create_engine("sqlite:///:memory:")

    with legacy_engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE platform_profiles ("
                "id VARCHAR PRIMARY KEY, "
                "user_id VARCHAR NOT NULL, "
                "platform VARCHAR NOT NULL, "
                "handle VARCHAR NOT NULL, "
                "created_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO platform_profiles (id, user_id, platform, handle) "
                "VALUES ('prof_1', 'usr_nebula', 'leetcode', 'NebulaOfCodeRK')"
            )
        )

    inspector = inspect(legacy_engine)
    cols_before = {col["name"] for col in inspector.get_columns("platform_profiles")}
    assert "api_key" not in cols_before
    assert "api_secret" not in cols_before

    run_migrations(legacy_engine)

    inspector = inspect(legacy_engine)
    cols_after = {col["name"] for col in inspector.get_columns("platform_profiles")}
    assert "api_key" in cols_after
    assert "api_secret" in cols_after

    with legacy_engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, user_id, platform, handle, api_key FROM platform_profiles WHERE id='prof_1'")
        ).fetchone()
        assert row is not None
        assert row[0] == "prof_1"
        assert row[1] == "usr_nebula"
        assert row[2] == "leetcode"
        assert row[3] == "NebulaOfCodeRK"
        assert row[4] is None

    run_migrations(legacy_engine)
    inspector = inspect(legacy_engine)
    cols_again = {col["name"] for col in inspector.get_columns("platform_profiles")}
    assert "api_key" in cols_again
    assert "api_secret" in cols_again


@patch("app.main.LeetCodeCollector.fetch_submissions")
def test_leetcode_handle_switch_purge(mock_lc_fetch):
    token, user_id = register_user("lc_switch@test.com", "lc_switch_user")
    headers = {"Authorization": f"Bearer {token}"}

    mock_lc_fetch.return_value = {
        "data": {
            "matchedUser": {"username": "NebulaOfCodeRK"},
            "recentSubmissionList": [{"title": "Old LeetCode Prob", "titleSlug": "old-prob", "timestamp": "1000", "statusDisplay": "Accepted", "lang": "cpp"}]
        }
    }
    client.post("/api/platforms/leetcode/connect", json={"handle": "NebulaOfCodeRK"}, headers=headers)
    client.post("/api/platforms/leetcode/sync", headers=headers)

    subs1 = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs1) == 1
    assert subs1[0]["problem_title"] == "Old LeetCode Prob"

    mock_lc_fetch.return_value = {
        "data": {
            "matchedUser": {"username": "pragnya"},
            "recentSubmissionList": [{"title": "New LeetCode Prob", "titleSlug": "new-prob", "timestamp": "2000", "statusDisplay": "Accepted", "lang": "cpp"}]
        }
    }
    conn_res = client.post("/api/platforms/leetcode/connect", json={"handle": "Pragnya"}, headers=headers)
    assert conn_res.status_code == 200

    subs_after_switch = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs_after_switch) == 0

    client.post("/api/platforms/leetcode/sync", headers=headers)
    subs2 = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs2) == 1
    assert subs2[0]["problem_title"] == "New LeetCode Prob"


@patch("app.main.CodeChefCollector.fetch_submissions")
def test_codechef_handle_switch_purge(mock_cc_fetch):
    token, user_id = register_user("cc_switch@test.com", "cc_switch_user")
    headers = {"Authorization": f"Bearer {token}"}

    mock_cc_fetch.return_value = {
        "status": "OK",
        "username": "chef1",
        "result": [{"id": "sub_1", "problemCode": "P1", "problemTitle": "Chef Prob 1", "language": "C++", "verdict": "ACCEPTED"}]
    }
    client.post("/api/platforms/codechef/connect", json={"handle": "chef1"}, headers=headers)
    client.post("/api/platforms/codechef/sync", headers=headers)

    subs1 = client.get("/api/submissions?platform=codechef", headers=headers).json()
    assert len(subs1) == 1

    mock_cc_fetch.return_value = {
        "status": "OK",
        "username": "chef2",
        "result": [{"id": "sub_2", "problemCode": "P2", "problemTitle": "Chef Prob 2", "language": "C++", "verdict": "ACCEPTED"}]
    }
    client.post("/api/platforms/codechef/connect", json={"handle": "chef2"}, headers=headers)
    client.post("/api/platforms/codechef/sync", headers=headers)

    subs2 = client.get("/api/submissions?platform=codechef", headers=headers).json()
    assert len(subs2) == 1
    assert subs2[0]["problem_title"] == "Chef Prob 2"


@patch("app.main.LeetCodeCollector.fetch_submissions")
def test_same_handle_reconnect_preserves_data(mock_lc_fetch):
    mock_lc_fetch.return_value = SAMPLE_LEETCODE_GRAPHQL_RESPONSE
    token, user_id = register_user("same_h@test.com", "same_h_user")
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/platforms/leetcode/connect", json={"handle": "lc_coder"}, headers=headers)
    client.post("/api/platforms/leetcode/sync", headers=headers)

    subs1 = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs1) == 1

    client.post("/api/platforms/leetcode/connect", json={"handle": "lc_coder"}, headers=headers)
    subs2 = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs2) == 1


@patch("app.main.LeetCodeCollector.fetch_submissions")
def test_repeated_sync_deduplication(mock_lc_fetch):
    mock_lc_fetch.return_value = SAMPLE_LEETCODE_GRAPHQL_RESPONSE
    token, user_id = register_user("dedup@test.com", "dedup_user")
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/platforms/leetcode/connect", json={"handle": "lc_coder"}, headers=headers)
    
    res1 = client.post("/api/platforms/leetcode/sync", headers=headers).json()
    assert res1["new_synced_count"] == 1

    res2 = client.post("/api/platforms/leetcode/sync", headers=headers).json()
    assert res2["new_synced_count"] == 0

    subs = client.get("/api/submissions?platform=leetcode", headers=headers).json()
    assert len(subs) == 1


@patch("app.main.CodeforcesCollector.fetch_submissions")
def test_public_profile_search_is_transient(mock_cf_fetch):
    mock_cf_fetch.return_value = SAMPLE_CF_AUTHENTICATED_RESPONSE
    token, user_id = register_user("public_srch@test.com", "public_srch_user")
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/public-profiles/search",
        json={"platform": "codeforces", "username": "tourist"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["platform"] == "codeforces"
    assert data["username"] == "tourist"
    assert data["total_solved"] == 1
    assert len(data["recent_activity"]) == 1

    db = TestingSessionLocal()
    try:
        profiles = db.query(PlatformProfile).all()
        assert len(profiles) == 0

        subs = db.query(SubmissionRecord).all()
        assert len(subs) == 0

        sources = db.query(SubmissionSourceCode).all()
        assert len(sources) == 0
    finally:
        db.close()

    user_subs = client.get("/api/submissions", headers=headers).json()
    assert len(user_subs) == 0

    user_stats = client.get("/api/stats", headers=headers).json()
    assert user_stats["total_submissions"] == 0


@patch("app.main.CodeforcesCollector.fetch_submissions")
@patch("app.main.LeetCodeCollector.fetch_submissions")
def test_user_isolation_with_public_search(mock_lc_fetch, mock_cf_fetch):
    mock_cf_fetch.return_value = SAMPLE_CF_AUTHENTICATED_RESPONSE
    mock_lc_fetch.return_value = SAMPLE_LEETCODE_GRAPHQL_RESPONSE

    token_a, user_a_id = register_user("user_a_owner@test.com", "user_a_owner")
    client.post("/api/platforms/codeforces/connect", json={"handle": "Jyoascoder"}, headers={"Authorization": f"Bearer {token_a}"})
    client.post("/api/platforms/codeforces/sync", headers={"Authorization": f"Bearer {token_a}"})

    token_b, user_b_id = register_user("user_b_searcher@test.com", "user_b_searcher")
    search_res = client.post(
        "/api/public-profiles/search",
        json={"platform": "leetcode", "username": "Pragnya"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert search_res.status_code == 200

    b_subs = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert len(b_subs) == 0

    b_stats = client.get("/api/stats", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert b_stats["total_submissions"] == 0

    a_subs = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert len(a_subs) == 1
    assert a_subs[0]["platform"] == "codeforces"


@patch("httpx.Client.get")
def test_codechef_pagination_multi_page_and_empty_termination(mock_get):
    """Test CodeChef collector page loop pagination, multi-page parsing, and empty page termination."""
    collector = CodeChefCollector(max_pages=10, page_delay=0)

    def mock_get_side_effect(url, headers=None):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = MagicMock()

        if "users/multipage_user" in url:
            mock_resp.url.path = "/users/multipage_user"
            mock_resp.text = "<html><body>Profile Page</body></html>"
            mock_resp.json.side_effect = Exception("HTML page")
        elif "page=0" in url:
            mock_resp.json.return_value = {
                "content": "<tr><td><span><span class='tooltiptext'>2026-09-25</span></span></td><td><a href='/problems/P1'>Prob 1</a></td><td>(100)</td><td>C++</td></tr>"
            }
        elif "page=1" in url:
            mock_resp.json.return_value = {
                "content": "<tr><td><span><span class='tooltiptext'>2026-09-26</span></span></td><td><a href='/problems/P2'>Prob 2</a></td><td>(100)</td><td>Python 3</td></tr>"
            }
        elif "page=2" in url:
            mock_resp.json.return_value = {"content": "No Recent Activity"}
        else:
            mock_resp.status_code = 404
        return mock_resp

    mock_get.side_effect = mock_get_side_effect

    res = collector.fetch_submissions("multipage_user")
    assert res["status"] == "OK"
    results = res["result"]
    assert len(results) == 2
    assert results[0]["problemCode"] == "P1"
    assert results[1]["problemCode"] == "P2"


@patch("httpx.Client.get")
@patch("time.sleep")
def test_codechef_rate_limit_backoff_and_retry_after(mock_sleep, mock_get):
    """Test CodeChef exponential backoff and Retry-After header parsing on HTTP 429."""
    collector = CodeChefCollector(max_pages=5, page_delay=0, max_retries_on_429=3, backoff_delays=[0.1, 0.2, 0.3])
    call_count = 0

    def mock_get_side_effect(url, headers=None):
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.url = MagicMock()

        if "users/rate_limited_user" in url:
            mock_resp.status_code = 200
            mock_resp.url.path = "/users/rate_limited_user"
            mock_resp.text = "<html><body>Profile Page</body></html>"
            mock_resp.json.side_effect = Exception("HTML page")
        elif "page=0" in url:
            if call_count == 2:  # First attempt for page=0 returns 429
                mock_resp.status_code = 429
                mock_resp.headers = {"Retry-After": "2"}
            else:  # Retry attempt returns 200
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "content": "<tr><td><span><span class='tooltiptext'>2026-09-25</span></span></td><td><a href='/problems/TEST1'>Test 1</a></td><td>(100)</td><td>C++</td></tr>"
                }
        elif "page=1" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"content": "No Recent Activity"}
        return mock_resp

    mock_get.side_effect = mock_get_side_effect

    res = collector.fetch_submissions("rate_limited_user")
    assert res["status"] == "OK"
    assert len(res["result"]) == 1
    assert res["result"][0]["problemCode"] == "TEST1"
    # Ensure sleep was called with 2 seconds from Retry-After header
    mock_sleep.assert_called_with(2.0)


@patch("app.main.CodeChefCollector.fetch_submissions")
def test_codechef_rate_limit_endpoint_429(mock_cc_fetch):
    """Test that CodeChefRateLimitError turns into HTTP 429 in API endpoints."""
    mock_cc_fetch.side_effect = CodeChefRateLimitError("Rate limit exceeded")
    token, _ = register_user("cc_429@test.com", "cc_429_user")
    headers = {"Authorization": f"Bearer {token}"}

    res_conn = client.post("/api/platforms/codechef/connect", json={"handle": "rate_limited_chef"}, headers=headers)
    assert res_conn.status_code == 429
    assert "CodeChef temporarily rate-limited this request" in res_conn.json()["detail"]

    # Also test sync endpoint when profile is connected
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "cc_429@test.com").first()
    prof = PlatformProfile(user_id=user.id, platform="codechef", handle="rate_limited_chef")
    db.add(prof)
    db.commit()
    db.close()

    res_sync = client.post("/api/platforms/codechef/sync", headers=headers)
    assert res_sync.status_code == 429
    assert "CodeChef temporarily rate-limited this request" in res_sync.json()["detail"]

