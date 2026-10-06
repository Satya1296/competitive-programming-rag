import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.main import app
from app.db import Base, get_db

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

SAMPLE_CF_API_RESPONSE = {
    "status": "OK",
    "result": [
        {
            "id": 19284712,
            "contestId": 1900,
            "creationTimeSeconds": 1710513000,
            "problem": {
                "contestId": 1900,
                "index": "C",
                "name": "Anji's Binary Tree",
                "rating": 1300,
                "tags": ["trees", "dfs", "dp"],
            },
            "programmingLanguage": "GNU C++20 (64 bit)",
            "verdict": "OK",
            "timeConsumedMillis": 145,
            "memoryConsumedBytes": 4194304,
        }
    ],
}


def register_and_login(email: str, username: str) -> tuple[str, str]:
    res = client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": "password123"},
    )
    data = res.json()
    return data["access_token"], data["user"]["id"]


def create_user_with_submission(email: str, username: str):
    with patch("app.main.CodeforcesCollector.fetch_submissions") as mock_fetch:
        mock_fetch.return_value = SAMPLE_CF_API_RESPONSE
        token, user_id = register_and_login(email, username)

        client.post(
            "/api/platforms/codeforces/connect",
            json={"handle": f"handle_{username}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        client.post(
            "/api/platforms/codeforces/sync",
            headers={"Authorization": f"Bearer {token}"},
        )

        subs = client.get(
            "/api/submissions",
            headers={"Authorization": f"Bearer {token}"},
        ).json()

        sub_id = subs[0]["id"]
        return token, user_id, sub_id


def test_user_a_add_and_get_source_code():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_a@test.com", "user_a")

    # Add source code manually
    cpp_code = "#include <iostream>\nusing namespace std;\nint main() { cout << 42; return 0; }"
    res_add = client.post(
        f"/api/submissions/{sub_id_a}/source-code",
        json={"source_code": cpp_code, "language": "cpp", "filename": "solution.cpp"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_add.status_code == 201
    data_add = res_add.json()
    assert data_add["source_code"] == cpp_code
    assert data_add["language"] == "cpp"
    assert data_add["filename"] == "solution.cpp"

    # Get source code
    res_get = client.get(
        f"/api/submissions/{sub_id_a}/source-code",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_get.status_code == 200
    assert res_get.json()["source_code"] == cpp_code


def test_user_a_file_upload_source_code():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_a_file@test.com", "user_a_file")

    python_code = "print('Hello World from Python file')"
    file_payload = ("main.py", io.BytesIO(python_code.encode("utf-8")), "text/x-python")

    res = client.post(
        f"/api/submissions/{sub_id_a}/upload-source-code",
        files={"file": file_payload},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["source_code"] == python_code
    assert data["filename"] == "main.py"
    assert data["language"] == "python"


def test_user_a_cannot_add_or_get_user_b_source_code():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_a_sec@test.com", "user_a_sec")
    token_b, user_b_id, sub_id_b = create_user_with_submission("user_b_sec@test.com", "user_b_sec")

    # User A tries to add code to User B's submission -> 403 Forbidden
    res_add = client.post(
        f"/api/submissions/{sub_id_b}/source-code",
        json={"source_code": "code", "language": "cpp"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_add.status_code == 403
    assert "permission" in res_add.json()["detail"].lower()

    # User A tries to get User B's source code -> 403 Forbidden
    res_get = client.get(
        f"/api/submissions/{sub_id_b}/source-code",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_get.status_code == 403

    # User A tries to update User B's source code -> 403 Forbidden
    res_put = client.put(
        f"/api/submissions/{sub_id_b}/source-code",
        json={"source_code": "updated code", "language": "cpp"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_put.status_code == 403


def test_unauthenticated_requests_rejected():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_unauth@test.com", "user_unauth")

    # POST without token -> 401 Unauthorized
    res1 = client.post(
        f"/api/submissions/{sub_id_a}/source-code",
        json={"source_code": "code", "language": "cpp"},
    )
    assert res1.status_code == 401

    # GET without token -> 401 Unauthorized
    res2 = client.get(f"/api/submissions/{sub_id_a}/source-code")
    assert res2.status_code == 401


def test_empty_source_code_rejected():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_empty@test.com", "user_empty")

    res = client.post(
        f"/api/submissions/{sub_id_a}/source-code",
        json={"source_code": "   ", "language": "cpp"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code in (400, 422)


def test_unsupported_file_type_rejected():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_filetype@test.com", "user_filetype")

    # Upload executable or pdf
    bad_file = ("program.exe", io.BytesIO(b"binary data"), "application/octet-stream")
    res = client.post(
        f"/api/submissions/{sub_id_a}/upload-source-code",
        files={"file": bad_file},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 400
    assert "unsupported file extension" in res.json()["detail"].lower()


def test_has_source_code_flag_updates_and_triggers_vector_indexing():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_indexing@test.com", "user_indexing")

    # 1. Fetch initial submission -> metadata only
    subs_before = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_a}"}).json()
    sub_initial = next(s for s in subs_before if s["id"] == sub_id_a)
    assert sub_initial["has_source_code"] is False
    assert sub_initial["code_source"] == "api_metadata"

    # 2. Attach genuine source code
    source_code = """
    #include <iostream>
    #include <vector>
    using namespace std;
    // Anji binary tree solution with dfs
    int main() {
        vector<int> tree = {1, 2, 3};
        cout << "DFS Tree Traversal Solution";
        return 0;
    }
    """
    res_attach = client.post(
        f"/api/submissions/{sub_id_a}/source-code",
        json={"source_code": source_code, "language": "cpp", "filename": "anji.cpp"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_attach.status_code == 201

    # 3. Verify submission response has_source_code is now True
    subs_after = client.get("/api/submissions", headers={"Authorization": f"Bearer {token_a}"}).json()
    sub_updated = next(s for s in subs_after if s["id"] == sub_id_a)
    assert sub_updated["has_source_code"] is True
    assert sub_updated["code_source"] == "user_upload"

    # 4. Perform semantic search -> should return actual source code in document_text
    search_res = client.post(
        "/api/vector/search",
        json={"query": "Anji binary tree solution with dfs", "top_k": 5},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total_results"] >= 1
    matched_doc = search_data["results"][0]
    assert matched_doc["has_source_code"] is True
    assert "vector<int> tree" in matched_doc["document_text"]


def test_user_a_cannot_retrieve_user_b_attached_source_code_vectors():
    token_a, user_a_id, sub_id_a = create_user_with_submission("user_sec_a@test.com", "user_sec_a")
    token_b, user_b_id, sub_id_b = create_user_with_submission("user_sec_b@test.com", "user_sec_b")

    # User B attaches secret source code
    secret_code = "void top_secret_user_b_algorithm() { int secret_key = 987654321; }"
    res_b = client.post(
        f"/api/submissions/{sub_id_b}/source-code",
        json={"source_code": secret_code, "language": "cpp"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 201

    # User A searches for User B's secret algorithm keyword
    search_a = client.post(
        "/api/vector/search",
        json={"query": "top_secret_user_b_algorithm secret_key", "top_k": 5},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert search_a.status_code == 200
    res_a_data = search_a.json()

    # User A must get 0 results for User B's vectors
    for item in res_a_data["results"]:
        assert item["metadata"]["user_id"] == user_a_id
        assert "secret_key" not in item["document_text"]

