import os
import shutil
import uuid
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base, get_db
from app.models.user import User
from app.models.profile import PlatformProfile
from app.models.submission import SubmissionRecord
from app.models.source_code import SubmissionSourceCode
from app.auth.jwt import hash_password, create_access_token
from app.preprocessing.cleaner import clean_code_text, construct_submission_document
from app.preprocessing.chunker import chunk_text
from app.vectorstore.embedder import get_embedding_service, EmbeddingService
from app.vectorstore.chroma_client import get_chroma_store, ChromaVectorStore
from app.vectorstore.service import (
    index_submission_for_user,
    index_all_user_submissions,
    search_user_knowledge,
)

from sqlalchemy.pool import StaticPool

# Test Database & ChromaDB paths
TEST_DB_URL = "sqlite:///:memory:"
TEST_CHROMA_DIR = "backend/data/test_chromadb"

engine = create_engine(
    TEST_DB_URL,
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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db_override():
    app.dependency_overrides[get_db] = override_get_db
    yield


@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    if os.path.exists(TEST_CHROMA_DIR):
        shutil.rmtree(TEST_CHROMA_DIR, ignore_errors=True)

    yield

    Base.metadata.drop_all(bind=engine)
    if os.path.exists(TEST_CHROMA_DIR):
        shutil.rmtree(TEST_CHROMA_DIR, ignore_errors=True)


@pytest.fixture
def test_db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------------------
# 1. PREPROCESSING & CHUNKING TESTS
# -----------------------------------------------------------------------------

def test_code_cleaner_preserves_structure():
    raw_code = """
    #include <iostream>
    using namespace std;
    
    // Binary search implementation
    int main() {
        int arr[] = {1, 2, 3, 4, 5};
        int target = 3;
        if (target > 0 && target <= 5) {
            cout << "Found target: " << target << endl;
        }
        return 0;
    }
    """
    cleaned = clean_code_text(raw_code)
    assert "int main()" in cleaned
    assert "target > 0 && target <= 5" in cleaned
    assert "#include <iostream>" in cleaned


def test_chunk_text_line_boundaries():
    text = "Line 1: #include <iostream>\n" * 50  # ~1350 chars
    chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 600
        assert "Line 1:" in chunk


# -----------------------------------------------------------------------------
# 2. EMBEDDING SERVICE TESTS
# -----------------------------------------------------------------------------

def test_embedding_service_generation():
    embedder = get_embedding_service()
    vec = embedder.embed_text("How did I implement binary search?")
    assert isinstance(vec, list)
    assert len(vec) == 384  # all-MiniLM-L6-v2 dimension

    batch_vecs = embedder.embed_batch(["binary search code", "prefix sums logic"])
    assert len(batch_vecs) == 2
    assert len(batch_vecs[0]) == 384


# -----------------------------------------------------------------------------
# 3. CHROMADB & USER-SCOPED INDEXING TESTS
# -----------------------------------------------------------------------------

def test_user_scoped_indexing_and_search(test_db_session):
    db = test_db_session

    # Create User A
    user_a = User(
        email="vector_a@example.com",
        username="vector_user_a",
        hashed_password=hash_password("Pass123!"),
    )
    # Create User B
    user_b = User(
        email="vector_b@example.com",
        username="vector_user_b",
        hashed_password=hash_password("Pass123!"),
    )
    db.add(user_a)
    db.add(user_b)
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)

    # Submission for User A
    sub_a = SubmissionRecord(
        id=f"{user_a.id}_codeforces_1001",
        user_id=user_a.id,
        platform="codeforces",
        problem_id="1001A",
        problem_title="User A Tree Dynamic Programming",
        problem_url="https://codeforces.com/problem/1001A",
        submission_id="1001",
        language="cpp",
        verdict="ACCEPTED",
        difficulty="1600",
        tags=["dp", "trees"],
        submitted_at="2026-09-23T10:00:00Z",
        code="// User A C++ Tree DP Code",
        code_source="user_upload",
    )
    code_a = SubmissionSourceCode(
        user_id=user_a.id,
        submission_id="1001",
        language="cpp",
        source_code="""
        #include <vector>
        using namespace std;
        // Tree DP solver by User A
        vector<int> adj[1005];
        int dp[1005];
        void dfs(int u, int p) {
            dp[u] = 1;
            for (int v : adj[u]) {
                if (v != p) {
                    dfs(v, u);
                    dp[u] += dp[v];
                }
            }
        }
        """,
        filename="treedp.cpp"
    )

    # Submission for User B
    sub_b = SubmissionRecord(
        id=f"{user_b.id}_codeforces_2002",
        user_id=user_b.id,
        platform="codeforces",
        problem_id="2002B",
        problem_title="User B Segment Tree Range Query",
        problem_url="https://codeforces.com/problem/2002B",
        submission_id="2002",
        language="python",
        verdict="ACCEPTED",
        difficulty="1800",
        tags=["data structures", "segment tree"],
        submitted_at="2026-09-23T11:00:00Z",
        code="# User B Python Segment Tree Code",
        code_source="user_upload",
    )
    code_b = SubmissionSourceCode(
        user_id=user_b.id,
        submission_id="2002",
        language="python",
        source_code="""
        # Segment tree by User B
        class SegmentTree:
            def __init__(self, data):
                self.n = len(data)
                self.tree = [0] * (4 * self.n)
                self.build(data, 1, 0, self.n - 1)
        """,
        filename="segtree.py"
    )

    db.add(sub_a)
    db.add(code_a)
    db.add(sub_b)
    db.add(code_b)
    db.commit()

    # Index User A's submission
    res_a = index_submission_for_user(user_a.id, "1001", db)
    assert res_a["submission_id"] == "1001"
    assert res_a["vectors_upserted"] >= 1

    # Index User B's submission
    res_b = index_submission_for_user(user_b.id, "2002", db)
    assert res_b["submission_id"] == "2002"
    assert res_b["vectors_upserted"] >= 1

    # Re-indexing User A submission should be idempotent
    res_a_again = index_submission_for_user(user_a.id, "1001", db)
    assert res_a_again["vectors_upserted"] == res_a["vectors_upserted"]

    # -------------------------------------------------------------------------
    # STRICT MULTI-USER ISOLATION SEARCH VERIFICATION
    # -------------------------------------------------------------------------

    # Search logged in as User A
    search_a = search_user_knowledge(user_a.id, "tree DP algorithm", top_k=5)
    assert search_a["total_results"] >= 1
    for item in search_a["results"]:
        assert item["metadata"]["user_id"] == user_a.id
        assert item["problem_title"] == "User A Tree Dynamic Programming"
        assert item["submission_id"] == "1001"

    # Search logged in as User B
    search_b = search_user_knowledge(user_b.id, "Segment Tree query", top_k=5)
    assert search_b["total_results"] >= 1
    for item in search_b["results"]:
        assert item["metadata"]["user_id"] == user_b.id
        assert item["problem_title"] == "User B Segment Tree Range Query"
        assert item["submission_id"] == "2002"

    # Verify User A CANNOT retrieve User B's vectors
    cross_search_a = search_user_knowledge(user_a.id, "SegmentTree python query", top_k=5)
    for item in cross_search_a["results"]:
        assert item["metadata"]["user_id"] == user_a.id  # Must belong to User A only
        assert item["submission_id"] != "2002"

    # Verify User A CANNOT index User B's submission
    with pytest.raises(Exception):
        index_submission_for_user(user_a.id, "2002", db)


# -----------------------------------------------------------------------------
# 4. API ENDPOINTS & HANDLE-SWITCH VECTOR CLEANUP TESTS
# -----------------------------------------------------------------------------

def test_api_vector_search_endpoint():
    with patch("app.main.CodeforcesCollector.fetch_submissions") as mock_fetch:
        mock_fetch.return_value = {
            "status": "OK",
            "result": [
                {
                    "id": 3003,
                    "contestId": 300,
                    "creationTimeSeconds": 1710513000,
                    "problem": {
                        "contestId": 300,
                        "index": "C",
                        "name": "Binary Search Target",
                        "rating": 1200,
                        "tags": ["binary search"],
                    },
                    "programmingLanguage": "GNU C++20",
                    "verdict": "OK",
                    "timeConsumedMillis": 15,
                    "memoryConsumedBytes": 1024,
                }
            ],
        }

        uid = uuid.uuid4().hex[:8]
        reg_res = client.post(
            "/api/auth/register",
            json={"email": f"api_user_{uid}@example.com", "username": f"api_usr_{uid}", "password": "Pass123!"}
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Connect and sync Codeforces handle
        client.post(
            "/api/platforms/codeforces/connect",
            json={"handle": f"cf_{uid}"},
            headers=headers,
        )
        client.post(
            "/api/platforms/codeforces/sync",
            headers=headers,
        )

        subs = client.get("/api/submissions", headers=headers).json()
        assert len(subs) > 0
        sub_id = subs[0]["id"]
        raw_sub_id = subs[0]["submission_id"]

        # Add source code via API
        add_code_res = client.post(
            f"/api/submissions/{sub_id}/source-code",
            headers=headers,
            json={
                "source_code": "int binary_search(int arr[], int n, int target) { int l=0, r=n-1; }",
                "language": "cpp",
                "filename": "solution.cpp"
            }
        )
        assert add_code_res.status_code == 201

        # 1. Index submission via API
        idx_resp = client.post(f"/api/vector/index/{raw_sub_id}", headers=headers)
        assert idx_resp.status_code == 200
        assert idx_resp.json()["submission_id"] == str(raw_sub_id)

        # 2. Search via API
        search_resp = client.post(
            "/api/vector/search",
            headers=headers,
            json={"query": "how to do binary search", "top_k": 3}
        )
        assert search_resp.status_code == 200
        res_data = search_resp.json()
        assert res_data["total_results"] >= 1
        assert res_data["results"][0]["submission_id"] == str(raw_sub_id)


def test_handle_switch_purges_chroma_vectors(test_db_session):
    db = test_db_session
    user = User(
        email="switch_user@example.com",
        username="switch_user",
        hashed_password=hash_password("Pass123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = PlatformProfile(
        user_id=user.id,
        platform="codeforces",
        handle="old_handle_cf",
    )
    sub = SubmissionRecord(
        id=f"{user.id}_codeforces_4004",
        user_id=user.id,
        platform="codeforces",
        problem_id="4004D",
        problem_title="Old Handle Problem",
        problem_url="https://codeforces.com/problem/4004D",
        submission_id="4004",
        language="cpp",
        verdict="ACCEPTED",
        submitted_at="2026-09-23T12:00:00Z",
        code="// Old Code",
        code_source="user_upload",
    )
    code_rec = SubmissionSourceCode(
        user_id=user.id,
        submission_id="4004",
        language="cpp",
        source_code="void solve_old() { int x = 42; }",
    )
    db.add(profile)
    db.add(sub)
    db.add(code_rec)
    db.commit()

    # Index vector
    index_submission_for_user(user.id, "4004", db)

    # Verify vector exists before switch
    pre_search = search_user_knowledge(user.id, "solve_old", top_k=5)
    assert pre_search["total_results"] >= 1

    # Perform ChromaDB vector purge for codeforces handle switch
    chroma_store = get_chroma_store()
    purged_count = chroma_store.delete_user_platform_vectors(user.id, "codeforces")
    assert purged_count >= 1

    # Verify vector is completely removed after handle switch
    post_search = search_user_knowledge(user.id, "solve_old", top_k=5)
    assert post_search["total_results"] == 0


def test_semantic_search_relevance_and_threshold(test_db_session):
    db = test_db_session

    user = User(
        email="relevance_user@example.com",
        username="rel_user",
        hashed_password=hash_password("Pass123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 1. Prefix Sums submission
    sub_ps = SubmissionRecord(
        id=f"{user.id}_codeforces_5001",
        user_id=user.id,
        platform="codeforces",
        problem_id="5001A",
        problem_title="Static Range Sum Queries",
        problem_url="https://codeforces.com/problem/5001A",
        submission_id="5001",
        language="cpp",
        verdict="ACCEPTED",
        code="// C++ Prefix sums code",
        code_source="user_upload",
        submitted_at="2026-09-23T12:00:00Z",
    )
    code_ps = SubmissionSourceCode(
        user_id=user.id,
        submission_id="5001",
        language="cpp",
        source_code="""
        #include <vector>
        using namespace std;
        // Prefix sum array algorithm
        int main() {
            vector<long long> pref = {0};
            int arr[] = {1, 2, 3, 4, 5};
            for(int x : arr) pref.push_back(pref.back() + x);
            // range sum query [l, r] = pref[r] - pref[l-1]
        }
        """,
    )

    # 2. Binary Search submission
    sub_bs = SubmissionRecord(
        id=f"{user.id}_codeforces_5002",
        user_id=user.id,
        platform="codeforces",
        problem_id="5002B",
        problem_title="Binary Search Lower Bound",
        problem_url="https://codeforces.com/problem/5002B",
        submission_id="5002",
        language="cpp",
        verdict="ACCEPTED",
        code="// C++ Binary search code",
        code_source="user_upload",
        submitted_at="2026-09-23T12:00:00Z",
    )
    code_bs = SubmissionSourceCode(
        user_id=user.id,
        submission_id="5002",
        language="cpp",
        source_code="""
        int binary_search_lower_bound(int arr[], int n, int target) {
            int low = 0, high = n - 1, ans = -1;
            while (low <= high) {
                int mid = low + (high - low) / 2;
                if (arr[mid] >= target) { ans = mid; high = mid - 1; }
                else low = mid + 1;
            }
            return ans;
        }
        """,
    )

    # 3. Metadata-Only submission (no source code attached)
    sub_meta = SubmissionRecord(
        id=f"{user.id}_codeforces_5003",
        user_id=user.id,
        platform="codeforces",
        problem_id="5003C",
        problem_title="Dijkstra Shortest Path Graph Algorithm",
        problem_url="https://codeforces.com/problem/5003C",
        submission_id="5003",
        language="cpp",
        verdict="ACCEPTED",
        code="// Source code not provided by Codeforces user.status API endpoint",
        code_source="api_metadata",
        tags=["graphs", "shortest path", "dijkstra"],
        submitted_at="2026-09-23T12:00:00Z",
    )

    db.add_all([sub_ps, code_ps, sub_bs, code_bs, sub_meta])
    db.commit()

    # Index all 3 submissions
    index_submission_for_user(user.id, "5001", db)
    index_submission_for_user(user.id, "5002", db)
    index_submission_for_user(user.id, "5003", db, allow_metadata_only=True)

    # Test 1: Query for prefix sums should rank submission 5001 highest
    res_ps = search_user_knowledge(user.id, "Show me prefix sums or range query solutions", top_k=5)
    assert res_ps["total_results"] >= 1
    assert res_ps["results"][0]["submission_id"] == "5001"
    assert res_ps["results"][0]["similarity_score"] >= 0.35

    # Test 2: Query for binary search should rank submission 5002 highest
    res_bs = search_user_knowledge(user.id, "How did I implement binary search lower bound?", top_k=5)
    assert res_bs["total_results"] >= 1
    assert res_bs["results"][0]["submission_id"] == "5002"
    assert res_bs["results"][0]["similarity_score"] >= 0.35

    # Test 3: Metadata-only submission searchability & metadata badge check
    res_meta = search_user_knowledge(user.id, "Dijkstra shortest path graph", top_k=5)
    assert res_meta["total_results"] >= 1
    meta_item = next(item for item in res_meta["results"] if item["submission_id"] == "5003")
    assert meta_item["has_source_code"] is False

    # Test 4: Unrelated query should trigger similarity threshold and return 0 results
    res_unrelated = search_user_knowledge(user.id, "chocolate cake recipe with baking soda and frosting", top_k=5)
    assert res_unrelated["total_results"] == 0
    assert len(res_unrelated["results"]) == 0
    assert "No sufficiently relevant submissions found for this query." in res_unrelated["message"]


def test_submission_level_deduplication_and_reindex_clean(test_db_session):
    db = test_db_session

    user = User(
        email="dedup_user@example.com",
        username="dedup_user",
        hashed_password=hash_password("Pass123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Submission with multi-chunk source code (~1500 chars)
    large_code = ("// Multi-chunk sorting algorithm implementation\n" +
                  "void sort_array(int arr[], int n) {\n" +
                  "    for(int i=0; i<n; i++) {\n" +
                  "        for(int j=i+1; j<n; j++) {\n" +
                  "            if(arr[i] > arr[j]) swap(arr[i], arr[j]);\n" +
                  "        }\n" +
                  "    }\n" +
                  "}\n") * 15

    sub_multi = SubmissionRecord(
        id=f"{user.id}_codeforces_6001",
        user_id=user.id,
        platform="codeforces",
        problem_id="6001A",
        problem_title="Bubble Sort Array",
        problem_url="https://codeforces.com/problem/6001A",
        submission_id="6001",
        language="cpp",
        verdict="ACCEPTED",
        code="// C++ Bubble sort code",
        code_source="user_upload",
        submitted_at="2026-09-23T12:00:00Z",
    )
    code_multi = SubmissionSourceCode(
        user_id=user.id,
        submission_id="6001",
        language="cpp",
        source_code=large_code,
    )

    db.add(sub_multi)
    db.add(code_multi)
    db.commit()

    # 1. Index multi-chunk submission
    idx_res = index_submission_for_user(user.id, "6001", db)
    assert idx_res["chunks_created"] >= 2

    # 2. Search for sorting - MUST return exactly 1 result card for submission 6001 (not multiple chunk cards)
    search_res = search_user_knowledge(user.id, "sorting algorithm", top_k=5)
    assert search_res["total_results"] == 1
    assert len(search_res["results"]) == 1
    assert search_res["results"][0]["submission_id"] == "6001"

    # 3. Re-indexing MUST overwrite cleanly without duplicating vectors
    re_idx_res = index_submission_for_user(user.id, "6001", db)
    assert re_idx_res["vectors_upserted"] == idx_res["chunks_created"]

    search_after_reindex = search_user_knowledge(user.id, "sorting algorithm", top_k=5)
    assert search_after_reindex["total_results"] == 1
    assert len(search_after_reindex["results"]) == 1


def test_problem_level_deduplication_different_submissions(test_db_session):
    db = test_db_session

    user = User(
        email="pdedup_user@example.com",
        username="pdedup_user",
        hashed_password=hash_password("Pass123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Attempt 1 for Problem 7001 (Nikita and Books)
    sub_1 = SubmissionRecord(
        id=f"{user.id}_codeforces_7001",
        user_id=user.id,
        platform="codeforces",
        problem_id="2244B",
        problem_title="Nikita and Books",
        problem_url="https://codeforces.com/problem/2244B",
        submission_id="7001",
        language="cpp",
        verdict="WRONG_ANSWER",
        code="// Attempt 1 for Nikita and Books",
        code_source="user_upload",
        submitted_at="2026-09-23T12:00:00Z",
    )
    code_1 = SubmissionSourceCode(
        user_id=user.id,
        submission_id="7001",
        language="cpp",
        source_code="void solve() { int a[] = {3,2,1}; sort(a, a+3); }",
    )

    # Attempt 2 for SAME Problem 7001 (Nikita and Books)
    sub_2 = SubmissionRecord(
        id=f"{user.id}_codeforces_7002",
        user_id=user.id,
        platform="codeforces",
        problem_id="2244B",
        problem_title="Nikita and Books",
        problem_url="https://codeforces.com/problem/2244B",
        submission_id="7002",
        language="cpp",
        verdict="ACCEPTED",
        code="// Attempt 2 for Nikita and Books",
        code_source="user_upload",
        submitted_at="2026-09-23T12:05:00Z",
    )
    code_2 = SubmissionSourceCode(
        user_id=user.id,
        submission_id="7002",
        language="cpp",
        source_code="void solve_ac() { int a[] = {3,2,1}; std::sort(a, a+3); }",
    )

    # Submission for DIFFERENT Problem (Short Sort)
    sub_3 = SubmissionRecord(
        id=f"{user.id}_codeforces_7003",
        user_id=user.id,
        platform="codeforces",
        problem_id="1873A",
        problem_title="Short Sort",
        problem_url="https://codeforces.com/problem/1873A",
        submission_id="7003",
        language="cpp",
        verdict="ACCEPTED",
        code="// Short sort problem code",
        code_source="user_upload",
        submitted_at="2026-09-23T12:10:00Z",
    )
    code_3 = SubmissionSourceCode(
        user_id=user.id,
        submission_id="7003",
        language="cpp",
        source_code="void short_sort() { string s = 'abc'; swap(s[0], s[1]); }",
    )

    db.add_all([sub_1, code_1, sub_2, code_2, sub_3, code_3])
    db.commit()

    index_submission_for_user(user.id, "7001", db)
    index_submission_for_user(user.id, "7002", db)
    index_submission_for_user(user.id, "7003", db)

    # Search for sorting - MUST return 2 unique problem results ('Nikita and Books' and 'Short Sort')
    # and MUST NOT duplicate 'Nikita and Books'
    search_res = search_user_knowledge(user.id, "sorting algorithm", top_k=5)
    assert search_res["total_results"] == 2
    titles = [r["problem_title"] for r in search_res["results"]]
    assert len(titles) == 2
    assert "Nikita and Books" in titles
    assert "Short Sort" in titles


def test_fast_reindexing_and_progress_status():
    """Verify skip-already-indexed logic and live progress polling endpoint."""
    db = TestingSessionLocal()
    user = User(
        email="reindex_user@example.com",
        username="reindex_user",
        hashed_password=hash_password("Pass123!"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    sub = SubmissionRecord(
        id=f"{user.id}_codeforces_8001",
        user_id=user.id,
        platform="codeforces",
        problem_id="8001A",
        problem_title="Binary Search Practice",
        problem_url="https://codeforces.com/problem/8001A",
        submission_id="8001",
        language="cpp",
        verdict="ACCEPTED",
        code="int binary_search(int arr[], int n, int x) { return 0; }",
        code_source="user_upload",
        submitted_at="2026-09-25T10:00:00Z",
    )
    db.add(sub)
    db.commit()

    # 1. Initial indexing
    res1 = index_all_user_submissions(user.id, db)
    assert res1["newly_indexed_count"] == 1
    assert res1["already_indexed_count"] == 0

    # 2. Fast re-indexing
    res2 = index_all_user_submissions(user.id, db)
    assert res2["newly_indexed_count"] == 0
    assert res2["already_indexed_count"] == 1
    assert "Already indexed: 1" in res2["message"]

    db.close()

    # 3. Test progress status via API endpoint
    token = create_access_token(subject=user.id)
    res_status = client.get("/api/vector/index-status", headers={"Authorization": f"Bearer {token}"})
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["status"] == "completed"
    assert status_data["total"] == 1
    assert status_data["already_indexed"] == 1




