import json
from unittest.mock import MagicMock, patch
import httpx
import pytest

from app.collectors.codeforces import CodeforcesCollector, CodeforcesAPIError
from app.preprocessing.normalizer import (
    normalize_codeforces_submission,
    normalize_codeforces_submissions,
    normalize_language,
    normalize_verdict,
)
from app.schema.submission import UnifiedSubmission


# Sample Codeforces API submission fixture
SAMPLE_CF_SUBMISSION = {
    "id": 19284712,
    "contestId": 1900,
    "creationTimeSeconds": 1710513000,
    "relativeTimeSeconds": 2147483647,
    "problem": {
        "contestId": 1900,
        "index": "C",
        "name": "Anji's Binary Tree",
        "type": "PROGRAMMING",
        "points": 1500.0,
        "rating": 1300,
        "tags": ["trees", "dfs", "dp"],
    },
    "author": {
        "contestId": 1900,
        "members": [{"handle": "test_user"}],
        "participantType": "PRACTICE",
        "ghost": False,
        "startTimeSeconds": 1701009300,
    },
    "programmingLanguage": "GNU C++20 (64 bit)",
    "verdict": "OK",
    "testset": "TESTS",
    "passTestCount": 45,
    "timeConsumedMillis": 145,
    "memoryConsumedBytes": 4194304,
}

SAMPLE_CF_API_RESPONSE = {
    "status": "OK",
    "result": [
        SAMPLE_CF_SUBMISSION,
        {
            "id": 20485910,
            "contestId": 455,
            "creationTimeSeconds": 1712772900,
            "relativeTimeSeconds": 2147483647,
            "problem": {
                "contestId": 455,
                "index": "A",
                "name": "Boredom",
                "type": "PROGRAMMING",
                "rating": 1500,
                "tags": ["dp"],
            },
            "programmingLanguage": "PyPy 3-64",
            "verdict": "WRONG_ANSWER",
            "timeConsumedMillis": 280,
            "memoryConsumedBytes": 12582912,
        },
    ],
}


def test_normalize_language():
    assert normalize_language("GNU C++17") == "cpp"
    assert normalize_language("GNU C++20 (64 bit)") == "cpp"
    assert normalize_language("Python 3.8") == "python"
    assert normalize_language("PyPy 3-64") == "python"
    assert normalize_language("Java 11") == "java"
    assert normalize_language("Rust 2021") == "rust"
    assert normalize_language("") == "unknown"


def test_normalize_verdict():
    assert normalize_verdict("OK") == "ACCEPTED"
    assert normalize_verdict("WRONG_ANSWER") == "WRONG_ANSWER"
    assert normalize_verdict("TIME_LIMIT_EXCEEDED") == "TIME_LIMIT_EXCEEDED"
    assert normalize_verdict("MEMORY_LIMIT_EXCEEDED") == "MEMORY_LIMIT_EXCEEDED"
    assert normalize_verdict("COMPILATION_ERROR") == "COMPILATION_ERROR"
    assert normalize_verdict("UNKNOWN_VERDICT") == "OTHER"


def test_normalize_codeforces_submission_successful_mapping():
    sub = normalize_codeforces_submission(SAMPLE_CF_SUBMISSION)

    assert isinstance(sub, UnifiedSubmission)
    assert sub.id == "codeforces_19284712"
    assert sub.platform == "codeforces"
    assert sub.problem_id == "1900C"
    assert sub.problem_title == "Anji's Binary Tree"
    assert sub.problem_url == "https://codeforces.com/problemset/problem/1900/C"
    assert sub.submission_id == "19284712"
    assert sub.submission_url == "https://codeforces.com/contest/1900/submission/19284712"
    assert sub.language == "cpp"
    assert sub.verdict == "ACCEPTED"
    assert sub.difficulty == "1300"
    assert sub.tags == ["trees", "dfs", "dp"]
    assert sub.execution_time_ms == 145
    assert sub.memory_bytes == 4194304
    assert sub.submitted_at == "2024-03-15T14:30:00Z"
    assert "// Source code not provided" in sub.code


def test_normalize_codeforces_submission_missing_optional_fields():
    minimal_sub = {
        "id": 99999,
        "problem": {
            "index": "B",
            "name": "Minimal Problem",
        },
        "programmingLanguage": "Python 3",
        "verdict": "OK",
    }
    sub = normalize_codeforces_submission(minimal_sub)

    assert isinstance(sub, UnifiedSubmission)
    assert sub.id == "codeforces_99999"
    assert sub.problem_id == "B"
    assert sub.difficulty is None
    assert sub.tags == []
    assert sub.execution_time_ms is None
    assert sub.memory_bytes is None


def test_normalize_codeforces_submissions_list():
    normalized_list = normalize_codeforces_submissions(SAMPLE_CF_API_RESPONSE)
    assert len(normalized_list) == 2
    assert normalized_list[0].verdict == "ACCEPTED"
    assert normalized_list[1].verdict == "WRONG_ANSWER"
    assert normalized_list[1].language == "python"


@patch("httpx.Client.get")
def test_codeforces_collector_success(mock_get, tmp_path):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = SAMPLE_CF_API_RESPONSE
    mock_get.return_value = mock_response

    collector = CodeforcesCollector()
    data = collector.fetch_submissions("tourist", count=2)

    assert data["status"] == "OK"
    assert len(data["result"]) == 2
    mock_get.assert_called_once()


@patch("httpx.Client.get")
def test_codeforces_collector_api_error_response(mock_get):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "status": "FAILED",
        "comment": "handle: User not found",
    }
    mock_get.return_value = mock_response

    collector = CodeforcesCollector()
    with pytest.raises(CodeforcesAPIError, match="User not found"):
        collector.fetch_submissions("non_existent_user_12345")


@patch("httpx.Client.get")
def test_codeforces_collector_network_error(mock_get):
    mock_get.side_effect = httpx.HTTPError("Network down")

    collector = CodeforcesCollector()
    with pytest.raises(CodeforcesAPIError, match="API failed"):
        collector.fetch_submissions("tourist")
