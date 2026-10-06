import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.submission import SubmissionRecord
from app.models.source_code import SubmissionSourceCode
from app.preprocessing.cleaner import construct_submission_document, clean_query_text
from app.preprocessing.chunker import chunk_text
from app.vectorstore.embedder import get_embedding_service
from app.vectorstore.chroma_client import get_chroma_store
from app.config import CHUNK_SIZE, CHUNK_OVERLAP, DEFAULT_TOP_K, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)


def index_submission_for_user(
    user_id: str,
    submission_id: str,
    db: Session,
    allow_metadata_only: bool = False,
) -> Dict[str, Any]:
    """
    Indexes a single submission belonging to the authenticated user into ChromaDB.
    Supports both full source-code-backed submissions and metadata-only submissions.
    """
    # 1. Verify ownership and fetch submission metadata
    submission = db.query(SubmissionRecord).filter(
        SubmissionRecord.submission_id == submission_id,
        SubmissionRecord.user_id == user_id
    ).first()

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{submission_id}' not found or does not belong to user."
        )

    # 2. Fetch attached source code
    source_code_rec = db.query(SubmissionSourceCode).filter(
        SubmissionSourceCode.submission_id == submission_id,
        SubmissionSourceCode.user_id == user_id
    ).first()

    raw_code = None
    has_source_code = False

    if source_code_rec and source_code_rec.source_code and source_code_rec.source_code.strip():
        raw_code = source_code_rec.source_code
        has_source_code = True
    elif submission and submission.code and submission.code.strip():
        # Check if code is genuine user source code vs API metadata placeholder comment
        if submission.code_source in ["user_upload", "github_sync"] and not submission.code.startswith("// Source code not provided"):
            raw_code = submission.code
            has_source_code = True

    if not has_source_code and not allow_metadata_only:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No source code available for submission '{submission_id}'. Please upload or paste code first."
        )

    # 3. Preprocess and format document text
    doc_text = construct_submission_document(submission, raw_code if has_source_code else None)

    # 4. Chunk document text
    chunks = chunk_text(doc_text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    # 5. Generate embeddings
    embedder = get_embedding_service()
    embeddings = embedder.embed_batch(chunks)

    # 6. Purge old submission vectors for current user to avoid stale chunks, then upsert new vectors
    chroma_store = get_chroma_store()
    chroma_store.delete_submission_vectors(user_id=user_id, submission_id=submission.submission_id)
    vectors_upserted = chroma_store.upsert_chunks(
        user_id=user_id,
        submission_id=submission.submission_id,
        platform=submission.platform,
        language=submission.language,
        problem_id=submission.problem_id,
        problem_title=submission.problem_title,
        chunks=chunks,
        embeddings=embeddings,
        has_source_code=has_source_code,
    )

    return {
        "submission_id": submission.submission_id,
        "problem_title": submission.problem_title,
        "platform": submission.platform,
        "has_source_code": has_source_code,
        "chunks_created": len(chunks),
        "vectors_upserted": vectors_upserted,
        "message": f"Successfully indexed {vectors_upserted} chunks into knowledge base."
    }


INDEXING_PROGRESS: Dict[str, Dict[str, Any]] = {}


def get_indexing_progress(user_id: str) -> Dict[str, Any]:
    """Return current indexing progress status for user."""
    return INDEXING_PROGRESS.get(user_id, {
        "status": "completed",
        "total": 0,
        "processed": 0,
        "already_indexed": 0,
        "newly_indexed": 0,
        "percent": 100,
        "message": "No indexing currently in progress."
    })


def index_all_user_submissions(user_id: str, db: Session) -> Dict[str, Any]:
    """
    Indexes all submissions owned by the user into ChromaDB using high-performance batching.
    Skips submissions that are already indexed into ChromaDB.
    """
    user_submissions = db.query(SubmissionRecord).filter(
        SubmissionRecord.user_id == user_id
    ).all()

    total_submissions = len(user_submissions)
    if total_submissions == 0:
        INDEXING_PROGRESS[user_id] = {
            "status": "completed",
            "total": 0,
            "processed": 0,
            "already_indexed": 0,
            "newly_indexed": 0,
            "percent": 100,
            "message": "No submissions found for user."
        }
        return {
            "total_submissions_processed": 0,
            "already_indexed_count": 0,
            "newly_indexed_count": 0,
            "total_chunks_created": 0,
            "total_vectors_upserted": 0,
            "message": "Already indexed: 0. Newly indexed: 0."
        }

    chroma_store = get_chroma_store()
    indexed_ids = chroma_store.get_indexed_submission_ids(user_id)

    # Bulk fetch attached source codes for user
    source_records = db.query(SubmissionSourceCode).filter(
        SubmissionSourceCode.user_id == user_id
    ).all()
    source_map = {sr.submission_id: sr.source_code for sr in source_records if sr.source_code and sr.source_code.strip()}

    unindexed_submissions = [sub for sub in user_submissions if sub.submission_id not in indexed_ids]
    already_indexed_count = total_submissions - len(unindexed_submissions)

    # Fast path: If all submissions are already indexed, return immediately
    if not unindexed_submissions:
        logger.info(f"All {already_indexed_count} submissions already indexed for user '{user_id}'. Skipping embedding generation.")
        res_info = {
            "status": "completed",
            "total": total_submissions,
            "processed": total_submissions,
            "already_indexed": already_indexed_count,
            "newly_indexed": 0,
            "percent": 100,
            "message": f"Already indexed: {already_indexed_count}. Newly indexed: 0."
        }
        INDEXING_PROGRESS[user_id] = res_info
        return {
            "total_submissions_processed": total_submissions,
            "already_indexed_count": already_indexed_count,
            "newly_indexed_count": 0,
            "total_chunks_created": 0,
            "total_vectors_upserted": 0,
            "message": f"Already indexed: {already_indexed_count}. Newly indexed: 0."
        }

    # Initialize progress status
    INDEXING_PROGRESS[user_id] = {
        "status": "in_progress",
        "total": total_submissions,
        "processed": already_indexed_count,
        "already_indexed": already_indexed_count,
        "newly_indexed": 0,
        "percent": int((already_indexed_count / total_submissions) * 100),
        "message": f"Indexing submissions... {already_indexed_count} / {total_submissions}"
    }

    all_chunk_ids: List[str] = []
    all_chunks_text: List[str] = []
    all_metadatas: List[Dict[str, Any]] = []

    for sub in unindexed_submissions:
        raw_code = source_map.get(sub.submission_id)
        has_source_code = bool(raw_code)
        if not has_source_code and sub.code and sub.code.strip():
            if sub.code_source in ["user_upload", "github_sync"] and not sub.code.startswith("// Source code not provided"):
                raw_code = sub.code
                has_source_code = True

        doc_text = construct_submission_document(sub, raw_code if has_source_code else None)
        chunks = chunk_text(doc_text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

        for idx, chunk in enumerate(chunks):
            chunk_id = f"{user_id}_{sub.submission_id}_chunk_{idx}"
            all_chunk_ids.append(chunk_id)
            all_chunks_text.append(chunk)
            all_metadatas.append({
                "user_id": str(user_id),
                "submission_id": str(sub.submission_id),
                "platform": str(sub.platform or "unknown"),
                "language": str(sub.language or "unknown"),
                "problem_id": str(sub.problem_id or ""),
                "problem_title": str(sub.problem_title or "Unknown Problem"),
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "has_source_code": bool(has_source_code),
            })

    # Generate embeddings in batched passes
    embedder = get_embedding_service()
    embeddings = embedder.embed_batch(all_chunks_text)

    # Execute batch upsert into ChromaDB
    total_vectors = chroma_store.batch_upsert_raw_chunks(
        ids=all_chunk_ids,
        embeddings=embeddings,
        documents=all_chunks_text,
        metadatas=all_metadatas,
        batch_size=250
    )

    newly_indexed_count = len(unindexed_submissions)
    msg = f"Already indexed: {already_indexed_count}. Newly indexed: {newly_indexed_count} ({total_vectors} chunks total)."

    INDEXING_PROGRESS[user_id] = {
        "status": "completed",
        "total": total_submissions,
        "processed": total_submissions,
        "already_indexed": already_indexed_count,
        "newly_indexed": newly_indexed_count,
        "percent": 100,
        "message": msg
    }

    return {
        "total_submissions_processed": total_submissions,
        "already_indexed_count": already_indexed_count,
        "newly_indexed_count": newly_indexed_count,
        "total_chunks_created": len(all_chunks_text),
        "total_vectors_upserted": total_vectors,
        "message": msg
    }


def search_user_knowledge(
    user_id: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = SIMILARITY_THRESHOLD,
) -> Dict[str, Any]:
    """
    Executes semantic search over the authenticated user's indexed code knowledge.
    Returns up to top_k results that satisfy min_similarity threshold.
    """
    cleaned_query = clean_query_text(query)
    if not cleaned_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty."
        )

    # 1. Embed search query
    embedder = get_embedding_service()
    query_vector = embedder.embed_text(cleaned_query)

    # 2. Search ChromaDB with enforced user_id filter and min_similarity threshold
    chroma_store = get_chroma_store()
    results = chroma_store.search(
        user_id=user_id,
        query_embedding=query_vector,
        top_k=top_k,
        min_similarity=min_similarity,
    )

    message = (
        f"Found {len(results)} relevant results."
        if results
        else "No sufficiently relevant submissions found for this query."
    )

    return {
        "query": cleaned_query,
        "top_k": top_k,
        "min_similarity_threshold": min_similarity,
        "total_results": len(results),
        "results": results,
        "message": message,
    }
