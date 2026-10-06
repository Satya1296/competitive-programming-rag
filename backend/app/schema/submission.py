from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class UnifiedSubmission(BaseModel):
    """
    Standardized schema for competitive programming submissions across platforms
    (Codeforces, LeetCode, CodeChef), scoped to a specific owner user.
    """

    id: str = Field(
        ...,
        description="Globally unique identifier formatted as {user_id}_{platform}_{submission_id}",
        examples=["usr_100_codeforces_19284712"],
    )
    user_id: str = Field(
        default="default_user",
        description="ID of the user who owns this submission",
        examples=["usr_100"],
    )
    platform: str = Field(
        ...,
        description="Platform name ('codeforces', 'leetcode', 'codechef')",
        examples=["codeforces"],
    )
    problem_id: str = Field(
        ...,
        description="Platform problem code or slug ('1900C', 'two-sum', 'FLOW001')",
        examples=["1900C"],
    )
    problem_title: str = Field(
        ...,
        description="Full title of the problem",
        examples=["Anji's Binary Tree"],
    )
    problem_url: str = Field(
        ...,
        description="URL to the problem statement page",
        examples=["https://codeforces.com/problemset/problem/1900/C"],
    )
    submission_id: str = Field(
        ...,
        description="Platform-specific submission ID string",
        examples=["19284712"],
    )
    submission_url: Optional[str] = Field(
        default=None,
        description="URL to view the submission details (if publicly accessible)",
        examples=["https://codeforces.com/contest/1900/submission/19284712"],
    )
    language: str = Field(
        ...,
        description="Normalized language identifier ('cpp', 'python', 'java')",
        examples=["cpp"],
    )
    verdict: str = Field(
        ...,
        description="Standardized verdict ('ACCEPTED', 'WRONG_ANSWER', 'TIME_LIMIT_EXCEEDED')",
        examples=["ACCEPTED"],
    )
    time_complexity: Optional[str] = Field(
        default=None,
        description="Time complexity notation",
        examples=["O(N)"],
    )
    space_complexity: Optional[str] = Field(
        default=None,
        description="Space complexity notation",
        examples=["O(N)"],
    )
    difficulty: Optional[str] = Field(
        default=None,
        description="Problem difficulty rating or tier ('1300', 'Medium', 'Hard')",
        examples=["1300"],
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Algorithm and data structure tags",
        examples=[["trees", "dfs", "dp"]],
    )
    execution_time_ms: Optional[int] = Field(
        default=None,
        description="Execution time in milliseconds",
        examples=[145],
    )
    memory_bytes: Optional[int] = Field(
        default=None,
        description="Memory used in bytes",
        examples=[4194304],
    )
    submitted_at: str = Field(
        ...,
        description="ISO 8601 string representation of submission timestamp",
        examples=["2024-03-15T14:30:00Z"],
    )
    code: str = Field(
        ...,
        description="Complete source code string",
        examples=["#include <iostream>\nint main() { return 0; }"],
    )
    code_source: str = Field(
        default="api_metadata",
        description="Source of code text ('api_metadata', 'user_upload', 'github_sync')",
        examples=["api_metadata"],
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional solution approach notes or editorial summary",
        examples=["Bottom-up tree DP to compute minimum operations to reach a leaf."],
    )

    model_config = ConfigDict(str_strip_whitespace=True)
