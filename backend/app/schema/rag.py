from typing import List, Optional
from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question about personal competitive programming submissions.")
    top_k: Optional[int] = Field(default=5, description="Maximum number of unique submission context sources to retrieve.")


class RAGSourceCitation(BaseModel):
    submission_id: str
    problem_id: str
    problem_title: str
    platform: str
    language: str
    has_source_code: bool
    similarity_score: float


class RAGQueryResponse(BaseModel):
    query: str
    answer: str
    sources: List[RAGSourceCitation]
    retrieval_count: int
    has_relevant_context: bool
    intent_category: Optional[str] = None
    analytics_summary: Optional[dict] = None
