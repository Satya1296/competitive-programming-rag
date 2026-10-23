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
from app.collectors.github import (
    GitHubCollector,
    GitHubRepoNotFoundError,
    GitHubRateLimitError,
    GitHubAuthError,
    GitHubAPIError,
    parse_github_repo_url,
    detect_language_from_filename,
)

TEST_DATABASE_URL = "sqlite:///:memory:"
TEST_CHROMA_DIR = "backend/data/test_github_chromadb"

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


def test_parse_github_repo_url():
    """Verify URL parsing handles multiple formats and rejects invalid ones."""
    assert parse_github_repo_url("https://github.com/torvalds/linux") == ("torvalds", "linux")
    assert parse_github_repo_url("https://github.com/torvalds/linux.git") == ("torvalds", "linux")
    assert parse_github_repo_url("http://github.com/user/cp-solutions/") == ("user", "cp-solutions")
    assert parse_github_repo_url("github.com/alice/leetcode-solutions") == ("alice", "leetcode-solutions")
    assert parse_github_repo_url("bob/algo-cpp") == ("bob", "algo-cpp")
    assert parse_github_repo_url("  https://github.com/charlie/codeforces  ") == ("charlie", "codeforces")

    # Invalid formats
    with pytest.raises(ValueError, match="cannot be empty"):
        parse_github_repo_url("")

    with pytest.raises(ValueError, match="Expected format"):
        parse_github_repo_url("https://google.com/search")

    with pytest.raises(ValueError, match="Expected format"):
        parse_github_repo_url("just-a-single-name")


def test_detect_language_from_filename():
    """Verify language detection from file extensions."""
    assert detect_language_from_filename("solution.cpp") == "cpp"
    assert detect_language_from_filename("two_sum.py") == "python"
    assert detect_language_from_filename("Solution.java") == "java"
    assert detect_language_from_filename("main.js") == "javascript"
    assert detect_language_from_filename("index.ts") == "typescript"
    assert detect_language_from_filename("unknown.txt") == "unknown"


def test_github_connect_invalid_url(monkeypatch):
    """Attempting to connect with an invalid URL returns HTTP 400 Bad Request."""
    db = TestingSessionLocal()
    user = User(id="user_gh_1", email="gh1@example.com", username="gh_user1", hashed_password="pw")
    db.add(user)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_1")
    resp = client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "invalid-url"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "Invalid GitHub repository URL" in resp.json()["detail"]


def test_github_connect_repository_not_found(monkeypatch):
    """Attempting to connect to a nonexistent or inaccessible repo returns 404."""
    db = TestingSessionLocal()
    user = User(id="user_gh_2", email="gh2@example.com", username="gh_user2", hashed_password="pw")
    db.add(user)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_2")

    def mock_validate(*args, **kwargs):
        raise GitHubRepoNotFoundError("Repository not found")

    monkeypatch.setattr(GitHubCollector, "validate_repository", mock_validate)

    resp = client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "https://github.com/nonexistent/fake-repo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert "Repository not found" in resp.json()["detail"]


def test_github_connect_auth_error(monkeypatch):
    """Attempting to connect with invalid credentials returns 401 Unauthorized."""
    db = TestingSessionLocal()
    user = User(id="user_gh_3", email="gh3@example.com", username="gh_user3", hashed_password="pw")
    db.add(user)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_3")

    def mock_validate(*args, **kwargs):
        raise GitHubAuthError("GitHub authentication failed")

    monkeypatch.setattr(GitHubCollector, "validate_repository", mock_validate)

    resp = client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "myorg/private-repo", "access_token": "bad_token"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "authentication failed" in resp.json()["detail"]


def test_github_connect_success_status_and_disconnect(monkeypatch):
    """Connecting a valid repository persists configuration, status returns data, and disconnect cleans it up."""
    db = TestingSessionLocal()
    user = User(id="user_gh_4", email="gh4@example.com", username="gh_user4", hashed_password="pw")
    db.add(user)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_4")

    def mock_validate(self, repo_url_or_handle, token=None):
        return {
            "owner": "testuser",
            "repo": "cp-repo",
            "full_name": "testuser/cp-repo",
            "private": False,
            "default_branch": "main",
            "description": "My CP Solutions",
        }

    monkeypatch.setattr(GitHubCollector, "validate_repository", mock_validate)

    # 1. Connect
    resp = client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "https://github.com/testuser/cp-repo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "github"
    assert data["handle"] == "testuser/cp-repo"
    assert data["total_submissions_synced"] == 0

    # 2. Get status
    status_resp = client.get(
        "/api/platforms/github/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["handle"] == "testuser/cp-repo"

    # 3. Disconnect
    disc_resp = client.delete(
        "/api/platforms/github/disconnect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disc_resp.status_code == 200

    # 4. Status after disconnect should be 404
    after_resp = client.get(
        "/api/platforms/github/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_resp.status_code == 404


def test_github_lookup_on_view_code(monkeypatch):
    """
    When user clicks View Code on an existing LeetCode submission without stored code,
    system looks up solution from connected GitHub repository, caches it, and returns it.
    """
    db = TestingSessionLocal()
    user = User(id="user_gh_lookup", email="lookup@example.com", username="lookup_user", hashed_password="pw")
    db.add(user)

    # Connect GitHub repo
    profile = PlatformProfile(
        user_id="user_gh_lookup",
        platform="github",
        handle="Satya1296/Leetcode-solutions",
    )
    db.add(profile)

    # Create an existing LeetCode submission without source code (metadata only)
    sub = SubmissionRecord(
        id="user_gh_lookup_leetcode_1614",
        user_id="user_gh_lookup",
        platform="leetcode",
        problem_id="maximum-nesting-depth-of-the-parentheses",
        problem_title="Maximum Nesting Depth of the Parentheses",
        problem_url="https://leetcode.com/problems/maximum-nesting-depth-of-the-parentheses/",
        submission_id="1790556485",
        language="cpp",
        verdict="ACCEPTED",
        submitted_at="2024-04-04 12:00:00",
        code="// Source code not provided",
        code_source="api_metadata",
    )
    db.add(sub)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_lookup")

    # Mock lookup_solution to simulate finding the file
    mock_solution = {
        "code": "class Solution {\npublic:\n    int maxDepth(string s) { return 0; }\n};",
        "language": "cpp",
        "filename": "1614-maximum-nesting-depth-of-the-parentheses.cpp",
        "url": "https://github.com/Satya1296/Leetcode-solutions/blob/main/1614-maximum-nesting-depth-of-the-parentheses/1614-maximum-nesting-depth-of-the-parentheses.cpp",
        "path": "1614-maximum-nesting-depth-of-the-parentheses/1614-maximum-nesting-depth-of-the-parentheses.cpp",
    }

    lookup_calls = []
    def mock_lookup(self, repo_handle, token=None, problem_title="", problem_slug="", problem_id=None):
        lookup_calls.append(problem_title)
        return mock_solution

    monkeypatch.setattr(GitHubCollector, "lookup_solution", mock_lookup)

    # 1. First call: trigger dynamic GitHub lookup
    resp = client.get(
        "/api/submissions/user_gh_lookup_leetcode_1614/source-code",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert "class Solution" in res_data["source_code"]
    assert res_data["language"] == "cpp"
    assert res_data["github_url"] == mock_solution["url"]
    assert len(lookup_calls) == 1

    # Verify database was updated and cached
    db_verify = TestingSessionLocal()
    updated_sub = db_verify.query(SubmissionRecord).filter(SubmissionRecord.id == "user_gh_lookup_leetcode_1614").first()
    assert updated_sub.code_source == "github_lookup"
    assert updated_sub.notes == f"GitHub: {mock_solution['url']}"
    assert updated_sub.has_source_code is True

    src_code = db_verify.query(SubmissionSourceCode).filter(SubmissionSourceCode.submission_id == "user_gh_lookup_leetcode_1614").first()
    assert src_code is not None
    assert "class Solution" in src_code.source_code
    db_verify.close()

    # 2. Second call: should return cached source code without calling GitHub lookup again
    resp2 = client.get(
        "/api/submissions/user_gh_lookup_leetcode_1614/source-code",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["source_code"] == res_data["source_code"]
    assert len(lookup_calls) == 1  # Not called again!


def test_github_lookup_not_found_returns_404(monkeypatch):
    """
    If no reliable match is found in the GitHub repo, return 404 (Source Code Unavailable).
    Never display mismatched code or code belonging to a different problem.
    """
    db = TestingSessionLocal()
    user = User(id="user_gh_nomatch", email="nomatch@example.com", username="nomatch_user", hashed_password="pw")
    db.add(user)

    profile = PlatformProfile(
        user_id="user_gh_nomatch",
        platform="github",
        handle="Satya1296/Leetcode-solutions",
    )
    db.add(profile)

    sub = SubmissionRecord(
        id="user_gh_nomatch_leetcode_9999",
        user_id="user_gh_nomatch",
        platform="leetcode",
        problem_id="unmatched-problem-slug",
        problem_title="Unmatched Problem Title",
        problem_url="https://leetcode.com/problems/unmatched-problem-slug/",
        submission_id="999999",
        language="python",
        verdict="ACCEPTED",
        submitted_at="2024-04-04 12:00:00",
        code="// Source code not provided",
        code_source="api_metadata",
    )
    db.add(sub)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_nomatch")

    # Mock lookup returning None (no match found)
    def mock_lookup(*args, **kwargs):
        return None

    monkeypatch.setattr(GitHubCollector, "lookup_solution", mock_lookup)

    resp = client.get(
        "/api/submissions/user_gh_nomatch_leetcode_9999/source-code",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Source Code Unavailable"


def test_github_solutions_never_create_new_submissions(monkeypatch):
    """
    GitHub files must NEVER create new submission records or alter platform submission counts.
    Submissions list must contain ONLY genuine platform submissions.
    """
    db = TestingSessionLocal()
    user = User(id="user_gh_nodummy", email="nodummy@example.com", username="nodummy_user", hashed_password="pw")
    db.add(user)

    sub = SubmissionRecord(
        id="user_gh_nodummy_leetcode_1",
        user_id="user_gh_nodummy",
        platform="leetcode",
        problem_id="two-sum",
        problem_title="Two Sum",
        problem_url="https://leetcode.com/problems/two-sum/",
        submission_id="111111",
        language="cpp",
        verdict="ACCEPTED",
        submitted_at="2024-04-04 12:00:00",
        code="// Source code not provided",
        code_source="api_metadata",
    )
    db.add(sub)
    db.commit()
    db.close()

    token = create_access_token(subject="user_gh_nodummy")

    def mock_validate(self, repo_url_or_handle, token=None):
        return {"owner": "test", "repo": "repo", "default_branch": "main"}

    monkeypatch.setattr(GitHubCollector, "validate_repository", mock_validate)

    # Connect repository
    client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "test/repo"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check submissions list
    subs_resp = client.get("/api/submissions", headers={"Authorization": f"Bearer {token}"})
    assert subs_resp.status_code == 200
    subs = subs_resp.json()
    # There is only 1 submission (the genuine LeetCode submission)
    assert len(subs) == 1
    assert subs[0]["platform"] == "leetcode"
    assert all(s["platform"] in ("leetcode", "codeforces", "codechef") for s in subs)


def test_github_user_isolation(monkeypatch):
    """User A and User B configurations and submissions are strictly isolated."""
    db = TestingSessionLocal()
    user_a = User(id="user_iso_a", email="iso_a@example.com", username="iso_a", hashed_password="pw")
    user_b = User(id="user_iso_b", email="iso_b@example.com", username="iso_b", hashed_password="pw")
    db.add_all([user_a, user_b])

    # User A submission
    sub_a = SubmissionRecord(
        id="user_iso_a_sub_1",
        user_id="user_iso_a",
        platform="leetcode",
        problem_id="prob-a",
        problem_title="Problem A",
        problem_url="https://leetcode.com/problems/prob-a/",
        submission_id="sub_a_1",
        language="cpp",
        verdict="ACCEPTED",
        submitted_at="2024-04-04 12:00:00",
        code="code for A",
        code_source="user_upload",
    )
    # User B submission
    sub_b = SubmissionRecord(
        id="user_iso_b_sub_1",
        user_id="user_iso_b",
        platform="leetcode",
        problem_id="prob-b",
        problem_title="Problem B",
        problem_url="https://leetcode.com/problems/prob-b/",
        submission_id="sub_b_1",
        language="python",
        verdict="ACCEPTED",
        submitted_at="2024-04-04 12:00:00",
        code="code for B",
        code_source="user_upload",
    )
    db.add_all([sub_a, sub_b])
    db.commit()
    db.close()

    token_a = create_access_token(subject="user_iso_a")
    token_b = create_access_token(subject="user_iso_b")

    def mock_validate(self, repo_url_or_handle, token=None):
        owner, repo = repo_url_or_handle.split("/")
        return {"owner": owner, "repo": repo, "default_branch": "main"}

    monkeypatch.setattr(GitHubCollector, "validate_repository", mock_validate)

    # User A connects repo_a
    client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "user_a/repo_a"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # User B connects repo_b
    client.post(
        "/api/platforms/github/connect",
        json={"repo_url": "user_b/repo_b"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # User A status
    status_a = client.get("/api/platforms/github/status", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert status_a["handle"] == "user_a/repo_a"

    # User B status
    status_b = client.get("/api/platforms/github/status", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert status_b["handle"] == "user_b/repo_b"

    # User A cannot access User B's submission source code (returns 403)
    resp_cross = client.get(
        "/api/submissions/user_iso_b_sub_1/source-code",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_cross.status_code == 403

    # Disconnect User A
    disc_a = client.delete("/api/platforms/github/disconnect", headers={"Authorization": f"Bearer {token_a}"})
    assert disc_a.status_code == 200

    # User A status is now 404
    assert client.get("/api/platforms/github/status", headers={"Authorization": f"Bearer {token_a}"}).status_code == 404

    # User B status remains intact
    assert client.get("/api/platforms/github/status", headers={"Authorization": f"Bearer {token_b}"}).status_code == 200
