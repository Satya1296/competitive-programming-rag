from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConnectProfileRequest(BaseModel):
    handle: str = Field(..., min_length=1, description="Platform handle / username")
    api_key: Optional[str] = Field(default=None, description="Optional Codeforces API Key for authenticated source code fetch")
    api_secret: Optional[str] = Field(default=None, description="Optional Codeforces API Secret for authenticated source code fetch")

    model_config = ConfigDict(str_strip_whitespace=True)


class ConnectGitHubRequest(BaseModel):
    repo_url: str = Field(..., min_length=1, description="GitHub repository URL or owner/repo format")
    access_token: Optional[str] = Field(default=None, description="Optional GitHub Personal Access Token")

    model_config = ConfigDict(str_strip_whitespace=True)



class ProfileStatusResponse(BaseModel):
    platform: str
    handle: str
    connected_at: datetime
    total_submissions_synced: int
    has_api_credentials: bool = False

    model_config = ConfigDict(from_attributes=True)


class SyncResponse(BaseModel):
    platform: str
    handle: str
    fetched_count: int
    new_synced_count: int
    message: str


class SubmissionResponse(BaseModel):
    id: str
    user_id: str
    platform: str
    problem_id: str
    problem_title: str
    problem_url: str
    submission_id: str
    submission_url: Optional[str] = None
    language: str
    verdict: str
    time_complexity: Optional[str] = None
    space_complexity: Optional[str] = None
    difficulty: Optional[str] = None
    tags: List[str] = []
    execution_time_ms: Optional[int] = None
    memory_bytes: Optional[int] = None
    submitted_at: str
    code: str
    code_source: str
    has_source_code: bool = True
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PublicProfileSearchRequest(BaseModel):
    platform: str = Field(..., description="Platform identifier ('codeforces', 'leetcode', 'codechef')")
    username: str = Field(..., min_length=1, description="Public username or handle to search")

    model_config = ConfigDict(str_strip_whitespace=True)


class PublicProfileSearchResponse(BaseModel):
    platform: str
    username: str
    is_valid: bool
    title_or_name: Optional[str] = None
    rank_or_rating: Optional[str] = None
    total_solved: Optional[int] = 0
    recent_activity: List[dict] = []
    message: str

