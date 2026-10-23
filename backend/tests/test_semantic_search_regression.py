import os
import shutil
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db import Base, get_db
from app.models.user import User
from app.models.submission import SubmissionRecord
from app.models.source_code import SubmissionSourceCode
from app.auth.jwt import hash_password, create_access_token
from app.vectorstore.embedder import get_embedding_service
from app.vectorstore.chroma_client import get_chroma_store
from app.vectorstore.service import search_user_knowledge

TEST_DB_URL = "sqlite:///:memory:"

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
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db


def test_github_standalone_record_source_code_retrieval():
    """Verify that a standalone GitHub document indexed in ChromaDB can be retrieved via source-code endpoint without an SQLite record."""
    db = TestingSessionLocal()
    user = User(
        id="usr_test_gh_standalone",
        email="gh_standalone@example.com",
        username="gh_standalone",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()

    token = create_access_token(subject="usr_test_gh_standalone")
    headers = {"Authorization": f"Bearer {token}"}

    # Index a standalone GitHub document into ChromaDB for this user
    chroma = get_chroma_store()
    doc_text = """# Problem: Sum Root To Leaf Numbers (129)
**Platform**: github | **Language**: cpp | **Verdict**: ACCEPTED
**Difficulty**: N/A | **Tags**: None
**Notes**: Synced from GitHub repo Satya1296/Leetcode-solutions: 0129-sum-root-to-leaf-numbers/0129-sum-root-to-leaf-numbers.cpp

## Source Code
```cpp
int sumNumbers(TreeNode* root) {
    return dfs(root, 0);
}
```"""

    embedder = get_embedding_service()
    emb = embedder.embed_text(doc_text)

    chroma.upsert_chunks(
        user_id="usr_test_gh_standalone",
        submission_id="gh_0129-sum-root-to-leaf-numbers.cpp",
        platform="github",
        language="cpp",
        problem_id="129",
        problem_title="Sum Root To Leaf Numbers",
        chunks=[doc_text],
        embeddings=[emb],
        has_source_code=True,
    )

    # Call endpoint without any SQLite submission record existing!
    resp = client.get(
        "/api/submissions/gh_0129-sum-root-to-leaf-numbers.cpp/source-code",
        headers=headers,
    )

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["language"] == "cpp"
    assert "sumNumbers" in data["source_code"]
    assert "https://github.com/Satya1296/Leetcode-solutions" in data["github_url"]
    assert data["submission_id"] == "gh_0129-sum-root-to-leaf-numbers.cpp"


def test_prefix_sum_query_suppresses_irrelevant_tree_problem():
    """Verify that a prefix sum search does not return an unrelated tree problem."""
    db = TestingSessionLocal()
    user = User(
        id="usr_test_relevance_tree",
        email="tree_relevance@example.com",
        username="tree_relevance",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()

    chroma = get_chroma_store()
    tree_doc = """# Problem: Sum Root To Leaf Numbers (129)
**Platform**: github | **Language**: cpp | **Verdict**: ACCEPTED
**Difficulty**: N/A | **Tags**: None
**Notes**: Synced from GitHub repo Satya1296/Leetcode-solutions: 0129-sum-root-to-leaf-numbers/0129-sum-root-to-leaf-numbers.cpp

## Source Code
```cpp
int sumNumbers(TreeNode* root) {
    return dfs(root, 0);
}
```"""
    embedder = get_embedding_service()
    emb = embedder.embed_text(tree_doc)

    chroma.upsert_chunks(
        user_id="usr_test_relevance_tree",
        submission_id="gh_0129-tree.cpp",
        platform="github",
        language="cpp",
        problem_id="129",
        problem_title="Sum Root To Leaf Numbers",
        chunks=[tree_doc],
        embeddings=[emb],
        has_source_code=True,
    )

    # Search for prefix sums or range queries
    results = search_user_knowledge(
        user_id="usr_test_relevance_tree",
        query="Show me prefix sums or range query solutions",
        db=db,
    )

    # Sum Root To Leaf Numbers MUST be filtered out because it has 0 prefix-sum concepts
    matching_titles = [r["problem_title"] for r in results["results"]]
    assert "Sum Root To Leaf Numbers" not in matching_titles
    assert results["total_results"] == 0


def test_prefix_sum_query_retrieves_genuine_prefix_sum():
    """Verify that a genuine prefix sum problem is retrieved with high relevance."""
    db = TestingSessionLocal()
    user = User(
        id="usr_test_relevance_ps",
        email="ps_relevance@example.com",
        username="ps_relevance",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()

    chroma = get_chroma_store()
    ps_doc = """# Problem: Range Sum Query (303)
**Platform**: leetcode | **Language**: cpp | **Verdict**: ACCEPTED
**Difficulty**: Easy | **Tags**: prefix sum, range query

## Source Code
```cpp
class NumArray {
    vector<int> prefix;
public:
    NumArray(vector<int>& nums) {
        prefix.resize(nums.size() + 1, 0);
        for (int i = 0; i < nums.size(); ++i) prefix[i+1] = prefix[i] + nums[i];
    }
    int sumRange(int left, int right) {
        return prefix[right + 1] - prefix[left];
    }
};
```"""
    embedder = get_embedding_service()
    emb = embedder.embed_text(ps_doc)

    chroma.upsert_chunks(
        user_id="usr_test_relevance_ps",
        submission_id="lc_303",
        platform="leetcode",
        language="cpp",
        problem_id="303",
        problem_title="Range Sum Query",
        chunks=[ps_doc],
        embeddings=[emb],
        has_source_code=True,
    )

    results = search_user_knowledge(
        user_id="usr_test_relevance_ps",
        query="Show me prefix sums or range query solutions",
        db=db,
    )

    assert results["total_results"] >= 1
    assert results["results"][0]["problem_title"] == "Range Sum Query"
    assert results["results"][0]["similarity_score"] >= 0.75


def test_binary_search_query_retrieval():
    """Verify that binary search queries retrieve genuine binary search solutions."""
    db = TestingSessionLocal()
    user = User(
        id="usr_test_bs",
        email="bs_test@example.com",
        username="bs_test",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user)
    db.commit()

    chroma = get_chroma_store()
    bs_doc = """# Problem: Search In Rotated Sorted Array (33)
**Platform**: leetcode | **Language**: cpp | **Verdict**: ACCEPTED
**Difficulty**: Medium | **Tags**: binary search, array

## Source Code
```cpp
int search(vector<int>& nums, int target) {
    int low = 0, high = nums.size() - 1;
    while (low <= high) {
        int mid = low + (high - low) / 2;
        if (nums[mid] == target) return mid;
    }
    return -1;
}
```"""
    embedder = get_embedding_service()
    emb = embedder.embed_text(bs_doc)

    chroma.upsert_chunks(
        user_id="usr_test_bs",
        submission_id="lc_33",
        platform="leetcode",
        language="cpp",
        problem_id="33",
        problem_title="Search In Rotated Sorted Array",
        chunks=[bs_doc],
        embeddings=[emb],
        has_source_code=True,
    )

    results = search_user_knowledge(
        user_id="usr_test_bs",
        query="How did I implement binary search?",
        db=db,
    )

    assert results["total_results"] >= 1
    assert "Search In Rotated Sorted Array" in [r["problem_title"] for r in results["results"]]
    assert results["results"][0]["similarity_score"] >= 0.75


def test_multi_user_isolation_standalone_github():
    """Verify that User B cannot access User A's standalone GitHub source code."""
    db = TestingSessionLocal()
    user_a = User(
        id="usr_test_user_a",
        email="usera@example.com",
        username="usera",
        hashed_password=hash_password("Password123!"),
    )
    user_b = User(
        id="usr_test_user_b",
        email="userb@example.com",
        username="userb",
        hashed_password=hash_password("Password123!"),
    )
    db.add(user_a)
    db.add(user_b)
    db.commit()

    # Index standalone GitHub document for User A
    chroma = get_chroma_store()
    doc_text = """# Problem: User A Secret Solution (100)
**Platform**: github | **Language**: cpp | **Verdict**: ACCEPTED

## Source Code
```cpp
int userAOnlyCode() { return 42; }
```"""
    embedder = get_embedding_service()
    emb = embedder.embed_text(doc_text)

    chroma.upsert_chunks(
        user_id="usr_test_user_a",
        submission_id="gh_usera_secret.cpp",
        platform="github",
        language="cpp",
        problem_id="100",
        problem_title="User A Secret Solution",
        chunks=[doc_text],
        embeddings=[emb],
        has_source_code=True,
    )

    # User B tries to retrieve User A's GitHub source code
    token_b = create_access_token(subject="usr_test_user_b")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get("/api/submissions/gh_usera_secret.cpp/source-code", headers=headers_b)
    # Must be 404 Not Found (User B has no access to User A's documents)
    assert resp.status_code == 404

    # User B's search also returns 0 results
    search_b = search_user_knowledge(
        user_id="usr_test_user_b",
        query="userAOnlyCode",
        db=db,
    )
    assert search_b["total_results"] == 0
