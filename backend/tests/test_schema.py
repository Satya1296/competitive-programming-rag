import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from app.schema.submission import UnifiedSubmission
from app.config import RAW_DATA_DIR


def test_valid_submission_direct_instantiation():
    """Test creating a UnifiedSubmission instance directly with valid fields."""
    sub = UnifiedSubmission(
        id="codeforces_100",
        user_id="usr_test_100",
        platform="codeforces",
        problem_id="1A",
        problem_title="Theatre Square",
        problem_url="https://codeforces.com/problemset/problem/1/A",
        submission_id="100",
        language="cpp",
        verdict="ACCEPTED",
        submitted_at="2024-01-01T00:00:00Z",
        code="int main() { return 0; }",
    )
    assert sub.id == "codeforces_100"
    assert sub.user_id == "usr_test_100"
    assert sub.platform == "codeforces"
    assert sub.language == "cpp"
    assert sub.verdict == "ACCEPTED"
    assert sub.tags == []  # default empty list


def test_missing_required_field_raises_validation_error():
    """Test that omitting required fields (like problem_id or code) raises ValidationError."""
    with pytest.raises(ValidationError):
        UnifiedSubmission(
            id="codeforces_100",
            platform="codeforces",
            # missing problem_id, problem_title, etc.
            language="cpp",
            verdict="ACCEPTED",
            submitted_at="2024-01-01T00:00:00Z",
            code="int main() {}",
        )


def test_raw_mock_json_files_validation():
    """Test loading and validating all 5 raw mock JSON records from backend/data/raw/."""
    expected_files = [
        "codeforces_cpp.json",
        "codeforces_python.json",
        "leetcode_cpp.json",
        "leetcode_python.json",
        "codechef_cpp.json",
    ]

    for filename in expected_files:
        filepath = RAW_DATA_DIR / filename
        assert filepath.exists(), f"Mock file missing: {filepath}"

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate with Pydantic model
        submission = UnifiedSubmission(**data)
        assert submission.id == data["id"]
        assert submission.user_id == data["user_id"]
        assert submission.platform == data["platform"]
        assert submission.code == data["code"]
        assert isinstance(submission.tags, list)
