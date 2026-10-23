from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SearchQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language semantic search query")
    top_k: Optional[int] = Field(5, ge=1, le=20, description="Maximum number of relevant chunks to retrieve")
    min_similarity: Optional[float] = Field(None, ge=0.0, le=1.0, description="Optional custom minimum similarity threshold")


class SearchResultItem(BaseModel):
    id: str
    submission_id: str
    platform: str
    language: str
    problem_id: Optional[str] = None
    problem_title: Optional[str] = None
    chunk_index: int
    total_chunks: int
    has_source_code: bool = True
    document_text: str
    distance: Optional[float] = 0.0
    similarity_score: float
    metadata: Optional[Dict[str, Any]] = None


class SearchQueryResponse(BaseModel):
    query: str
    top_k: int
    min_similarity_threshold: float
    total_results: int
    results: List[SearchResultItem]
    message: Optional[str] = None


class IndexingResponse(BaseModel):
    submission_id: Optional[str] = None
    problem_title: Optional[str] = None
    platform: Optional[str] = None
    has_source_code: bool = True
    chunks_created: int
    vectors_upserted: int
    message: str


class BulkIndexingResponse(BaseModel):
    total_submissions_processed: int
    total_chunks_created: int
    total_vectors_upserted: int
    message: str
