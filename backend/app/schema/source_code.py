from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AddSourceCodeRequest(BaseModel):
    source_code: str = Field(..., min_length=1, description="Raw source code string")
    language: Optional[str] = Field(None, description="Programming language identifier ('cpp', 'python', 'java', etc.)")
    filename: Optional[str] = Field(None, description="Optional filename e.g. solution.cpp")

    model_config = ConfigDict(str_strip_whitespace=True)


class SourceCodeResponse(BaseModel):
    id: str
    user_id: str
    submission_id: str
    language: str
    source_code: str
    filename: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
