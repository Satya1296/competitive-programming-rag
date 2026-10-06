import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import PROCESSED_DATA_DIR, USERS_DATA_DIR
from app.schema.submission import UnifiedSubmission


def normalize_language(lang_str: str) -> str:
    """Normalize platform language string to standard identifier ('cpp', 'python', 'java', etc.)."""
    if not lang_str:
        return "unknown"

    lower = lang_str.lower()
    if "c++" in lower or "cpp" in lower or "g++" in lower or "clang++" in lower:
        return "cpp"
    if "python" in lower or "pypy" in lower:
        return "python"
    if "java" in lower:
        return "java"
    if "c#" in lower or "csharp" in lower:
        return "csharp"
    if "rust" in lower:
        return "rust"
    if "go" in lower:
        return "go"
    if "javascript" in lower or "js" in lower or "node" in lower:
        return "javascript"
    if "typescript" in lower or "ts" in lower:
        return "typescript"
    return lower.strip()


def normalize_verdict(verdict_str: Optional[str]) -> str:
    """Normalize verdict string across platforms (Codeforces, LeetCode, CodeChef) to standard verdict format."""
    if not verdict_str:
        return "OTHER"

    v_upper = verdict_str.upper().strip()
    mapping = {
        "OK": "ACCEPTED",
        "ACCEPTED": "ACCEPTED",
        "AC": "ACCEPTED",
        "WRONG_ANSWER": "WRONG_ANSWER",
        "WRONG ANSWER": "WRONG_ANSWER",
        "WA": "WRONG_ANSWER",
        "TIME_LIMIT_EXCEEDED": "TIME_LIMIT_EXCEEDED",
        "TIME LIMIT EXCEEDED": "TIME_LIMIT_EXCEEDED",
        "TLE": "TIME_LIMIT_EXCEEDED",
        "MEMORY_LIMIT_EXCEEDED": "MEMORY_LIMIT_EXCEEDED",
        "MEMORY LIMIT EXCEEDED": "MEMORY_LIMIT_EXCEEDED",
        "MLE": "MEMORY_LIMIT_EXCEEDED",
        "COMPILATION_ERROR": "COMPILATION_ERROR",
        "COMPILE ERROR": "COMPILATION_ERROR",
        "CTE": "COMPILATION_ERROR",
        "RUNTIME_ERROR": "RUNTIME_ERROR",
        "RUNTIME ERROR": "RUNTIME_ERROR",
        "RTE": "RUNTIME_ERROR",
    }
    return mapping.get(v_upper, "OTHER")


def normalize_leetcode_submission(
    raw_sub: Dict[str, Any],
    user_id: str = "default_user",
    code: Optional[str] = None,
) -> UnifiedSubmission:
    """
    Convert a single raw LeetCode submission object into a UnifiedSubmission model.
    """
    title_slug = raw_sub.get("titleSlug", "unknown-problem")
    title = raw_sub.get("title", title_slug.replace("-", " ").title())
    ts = raw_sub.get("timestamp")

    if ts:
        try:
            submitted_at = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    raw_id = raw_sub.get("id")
    sub_id = f"lc_{raw_id}" if raw_id else f"lc_{title_slug}_{ts or '0'}"
    problem_url = f"https://leetcode.com/problems/{title_slug}/"
    lang = normalize_language(raw_sub.get("lang", raw_sub.get("language", "")))
    status_disp = raw_sub.get("statusDisplay") or "Accepted"
    verdict = normalize_verdict(status_disp)

    source_code = code if code is not None else "// Source code not provided by LeetCode public GraphQL API endpoint"

    return UnifiedSubmission(
        id=f"leetcode_{sub_id}",
        user_id=user_id,
        platform="leetcode",
        problem_id=title_slug,
        problem_title=title,
        problem_url=problem_url,
        submission_id=sub_id,
        submission_url=problem_url,
        language=lang,
        verdict=verdict,
        time_complexity=None,
        space_complexity=None,
        difficulty=None,
        tags=[],
        execution_time_ms=None,
        memory_bytes=None,
        submitted_at=submitted_at,
        code=source_code,
        code_source="api_metadata" if code is None else "user_upload",
        notes=None,
    )


def normalize_leetcode_submissions(
    raw_data: Dict[str, Any],
    user_id: str = "default_user",
    code_map: Optional[Dict[str, str]] = None,
) -> List[UnifiedSubmission]:
    """Process LeetCode GraphQL recentSubmissionList or recentAcSubmissionList payload into UnifiedSubmissions."""
    data_obj = raw_data.get("data", {})
    results = data_obj.get("recentSubmissionList")
    if not results or not isinstance(results, list):
        results = data_obj.get("recentAcSubmissionList", [])
    if not isinstance(results, list):
        return []

    code_map = code_map or {}
    normalized = []
    for raw_sub in results:
        raw_id = raw_sub.get("id")
        sub_id = f"lc_{raw_id}" if raw_id else f"lc_{raw_sub.get('titleSlug')}_{raw_sub.get('timestamp')}"
        code = code_map.get(sub_id)
        sub_model = normalize_leetcode_submission(raw_sub, user_id=user_id, code=code)
        normalized.append(sub_model)
    return normalized


def normalize_codechef_submission(
    raw_sub: Dict[str, Any],
    user_id: str = "default_user",
    code: Optional[str] = None,
) -> UnifiedSubmission:
    """
    Convert a raw CodeChef submission dictionary into a UnifiedSubmission model.
    """
    prob_code = raw_sub.get("problemCode") or raw_sub.get("code") or "UNKNOWN"
    title = raw_sub.get("problemTitle") or raw_sub.get("title") or prob_code
    sub_id = str(raw_sub.get("id") or raw_sub.get("submission_id") or f"cc_{prob_code}")
    submitted_at = raw_sub.get("submitted_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    problem_url = f"https://www.codechef.com/problems/{prob_code}"
    lang = normalize_language(raw_sub.get("language", ""))
    verdict = normalize_verdict(raw_sub.get("verdict") or raw_sub.get("result"))

    source_code = code if code is not None else "// Source code not provided by CodeChef public profile endpoint"

    return UnifiedSubmission(
        id=f"codechef_{sub_id}",
        user_id=user_id,
        platform="codechef",
        problem_id=prob_code,
        problem_title=title,
        problem_url=problem_url,
        submission_id=sub_id,
        submission_url=problem_url,
        language=lang,
        verdict=verdict,
        time_complexity=None,
        space_complexity=None,
        difficulty=None,
        tags=[],
        execution_time_ms=None,
        memory_bytes=None,
        submitted_at=submitted_at,
        code=source_code,
        code_source="api_metadata" if code is None else "user_upload",
        notes=None,
    )


def normalize_codechef_submissions(
    raw_data: Dict[str, Any],
    user_id: str = "default_user",
    code_map: Optional[Dict[str, str]] = None,
) -> List[UnifiedSubmission]:
    """Process CodeChef user submission payload into UnifiedSubmissions."""
    results = raw_data.get("result", [])
    if not isinstance(results, list):
        return []

    code_map = code_map or {}
    normalized = []
    for raw_sub in results:
        sub_id = str(raw_sub.get("id") or raw_sub.get("submission_id"))
        code = code_map.get(sub_id)
        sub_model = normalize_codechef_submission(raw_sub, user_id=user_id, code=code)
        normalized.append(sub_model)
    return normalized



def normalize_codeforces_submission(
    raw_sub: Dict[str, Any],
    user_id: str = "default_user",
    code: Optional[str] = None,
) -> UnifiedSubmission:
    """
    Convert a single raw Codeforces submission object (from user.status API result)
    into a UnifiedSubmission model scoped to user_id.
    """
    sub_id = str(raw_sub.get("id", "0"))
    problem = raw_sub.get("problem", {})

    contest_id = problem.get("contestId") or raw_sub.get("contestId")
    index = problem.get("index", "")

    if contest_id and index:
        problem_id = f"{contest_id}{index}"
        problem_url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        submission_url = f"https://codeforces.com/contest/{contest_id}/submission/{sub_id}"
    elif index:
        problem_id = str(index)
        problem_url = "https://codeforces.com/problemset"
        submission_url = None
    else:
        problem_id = "UNKNOWN"
        problem_url = "https://codeforces.com/problemset"
        submission_url = None

    problem_title = problem.get("name", "Unknown Problem")

    # Format timestamp
    creation_time = raw_sub.get("creationTimeSeconds")
    if creation_time:
        submitted_at = datetime.fromtimestamp(creation_time, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    else:
        submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Rating / Difficulty
    rating = problem.get("rating")
    difficulty = str(rating) if rating is not None else None

    # Tags
    tags = problem.get("tags", [])

    # Source code handling (supports authenticated Codeforces API source retrieval)
    raw_api_source = raw_sub.get("source")
    if code is not None:
        source_code = code
        code_source = "user_upload"
    elif raw_api_source and isinstance(raw_api_source, str) and raw_api_source.strip():
        source_code = raw_api_source.strip()
        code_source = "api_authenticated"
    else:
        source_code = "// Source code not provided by Codeforces user.status API endpoint"
        code_source = "api_metadata"

    return UnifiedSubmission(
        id=f"codeforces_{sub_id}",
        user_id=user_id,
        platform="codeforces",
        problem_id=problem_id,
        problem_title=problem_title,
        problem_url=problem_url,
        submission_id=sub_id,
        submission_url=submission_url,
        language=normalize_language(raw_sub.get("programmingLanguage", "")),
        verdict=normalize_verdict(raw_sub.get("verdict")),
        time_complexity=None,
        space_complexity=None,
        difficulty=difficulty,
        tags=tags,
        execution_time_ms=raw_sub.get("timeConsumedMillis"),
        memory_bytes=raw_sub.get("memoryConsumedBytes"),
        submitted_at=submitted_at,
        code=source_code,
        code_source=code_source,
        notes=None,
    )


def normalize_codeforces_submissions(
    raw_data: Dict[str, Any],
    user_id: str = "default_user",
    code_map: Optional[Dict[str, str]] = None,
) -> List[UnifiedSubmission]:
    """
    Process complete Codeforces user.status API payload and return list of UnifiedSubmissions.
    """
    results = raw_data.get("result", [])
    if not isinstance(results, list):
        return []

    code_map = code_map or {}
    normalized = []
    for raw_sub in results:
        sub_id = str(raw_sub.get("id"))
        code = code_map.get(sub_id)
        sub_model = normalize_codeforces_submission(raw_sub, user_id=user_id, code=code)
        normalized.append(sub_model)
    return normalized


def save_normalized_codeforces(
    user_id: str, handle: str, submissions: List[UnifiedSubmission]
) -> Path:
    """Save a list of normalized UnifiedSubmission objects to disk under user directory."""
    filepath = USERS_DATA_DIR / user_id / "processed" / f"codeforces_{handle.strip().lower()}.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    data = [sub.model_dump() for sub in submissions]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath
