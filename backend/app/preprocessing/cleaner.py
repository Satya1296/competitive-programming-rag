import re
from typing import Any, List, Dict, Optional


def clean_code_text(text: str) -> str:
    """
    Cleans and normalizes text/code while strictly preserving programming code structure,
    symbols, indentation, logic, keywords, and operators.
    """
    if not text:
        return ""

    # Replace carriage returns with standard line feed
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove non-printable control characters except standard tabs and newlines
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)

    # Trim trailing whitespace on each line while preserving leading indentation
    lines = [line.rstrip() for line in normalized.split("\n")]

    # Collapse >2 consecutive blank lines into at most 2 blank lines
    cleaned_lines = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append(line)
        else:
            blank_count = 0
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def clean_query_text(query: str) -> str:
    """
    Normalizes a natural language search query while strictly preserving programming terminology
    such as 'prefix sum', 'binary search', 'tree DP', 'DFS', 'BFS', 'segment tree', 'sliding window',
    'sorting', 'hashmap', 'two pointers', and technical operators.
    Aligns common plural tag variations ('prefix sums' -> 'prefix sum', 'sortings' -> 'sorting').
    """
    if not query:
        return ""

    # Remove non-printable control characters
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", query)
    # Collapse multiple spaces into single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Align common plural tag variations to standard competitive programming search terms
    term_replacements = {
        r"\bprefix sums\b": "prefix sum",
        r"\bsortings\b": "sorting",
        r"\bbinary searches\b": "binary search",
    }
    for pattern, replacement in term_replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    return cleaned


def construct_submission_document(submission: Any, source_code: Optional[str] = None) -> str:
    """
    Combines problem metadata and cleaned source code into a structured Markdown document.
    If source code is missing/empty, creates a metadata-only search document.
    """
    # Extract fields safely from ORM model or Pydantic model or dict
    problem_title = getattr(submission, "problem_title", None) or "Unknown Problem"
    problem_id = getattr(submission, "problem_id", None) or ""
    platform = getattr(submission, "platform", None) or "Unknown Platform"
    language = getattr(submission, "language", None) or "Unknown Language"
    verdict = getattr(submission, "verdict", None) or "Unknown Verdict"
    difficulty = getattr(submission, "difficulty", None) or ""

    # Handle tags (stored as JSON array/list or string)
    raw_tags = getattr(submission, "tags", [])
    if isinstance(raw_tags, list):
        tags_str = ", ".join(str(t) for t in raw_tags) if raw_tags else "None"
    elif isinstance(raw_tags, str):
        tags_str = raw_tags
    else:
        tags_str = "None"

    notes = getattr(submission, "notes", None) or ""

    cleaned_code = clean_code_text(source_code) if source_code else ""

    doc_parts = [
        f"# Problem: {problem_title} ({problem_id})",
        f"**Platform**: {platform} | **Language**: {language} | **Verdict**: {verdict}",
        f"**Difficulty**: {difficulty or 'N/A'} | **Tags**: {tags_str}",
    ]

    if notes:
        doc_parts.append(f"**Notes**: {notes}")

    if cleaned_code:
        doc_parts.extend([
            "",
            "## Source Code",
            f"```{language.lower()}",
            cleaned_code,
            "```"
        ])
    else:
        doc_parts.extend([
            "",
            "*[Metadata Only - No Source Code Attached]*"
        ])

    return "\n".join(doc_parts).strip()
