"""
Vectorstore package for embedding generation, ChromaDB persistent storage, and user-scoped semantic search.
"""
from app.vectorstore.embedder import get_embedding_service, EmbeddingService
from app.vectorstore.chroma_client import get_chroma_store, ChromaVectorStore
from app.vectorstore.service import (
    index_submission_for_user,
    index_all_user_submissions,
    get_indexing_progress,
    search_user_knowledge,
)

__all__ = [
    "get_embedding_service",
    "EmbeddingService",
    "get_chroma_store",
    "ChromaVectorStore",
    "index_submission_for_user",
    "index_all_user_submissions",
    "get_indexing_progress",
    "search_user_knowledge",
]
