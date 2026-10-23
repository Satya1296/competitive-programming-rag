import re
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

STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "with", "of", "by", "from",
    "is", "are", "was", "were", "be", "been", "being",
    "how", "did", "i", "we", "my", "me", "show", "give", "find", "get", "list",
    "code", "problem", "problems", "solution", "solutions", "approach", "approaches", "implement",
    "implementation", "solve", "solved", "using", "use", "what", "which", "where"
}

CP_CONCEPT_PATTERNS = {
    "prefix_sum": [
        r"\bprefix[\s_\-]*sums?\b",
        r"\bcumulative[\s_\-]*sums?\b",
        r"\brunning[\s_\-]*sums?\b",
        r"\bpartial[\s_\-]*sums?\b",
        r"\brange[\s_\-]*sums?\b",
        r"\bsubarray[\s_\-]*sums?\b",
        r"\bprefix[\s_\-]*array\b",
        r"\bprefix[\s_\-]*common[\s_\-]*array\b",
        r"\bsequential[\s_\-]*prefix[\s_\-]*sum\b",
        r"\bdifference[\s_\-]*array\b",
    ],
    "range_query": [
        r"\brange[\s_\-]*query\b",
        r"\brange[\s_\-]*queries\b",
        r"\brange[\s_\-]*add\b",
        r"\bin[\s_\-]*ranges?\b",
        r"\bin[\s_\-]*an[\s_\-]*interval[\s_\-]*range\b",
        r"\bqueries[\s_\-]*in[\s_\-]*ranges?\b",
        r"\bsegment[\s_\-]*tree\b",
        r"\bfenwick\b",
        r"\bbinary[\s_\-]*indexed[\s_\-]*tree\b",
        r"\bsparse[\s_\-]*table\b",
        r"\bcount[\s_\-]*commas[\s_\-]*in[\s_\-]*range\b",
        r"\bcompatible[\s_\-]*numbers[\s_\-]*in[\s_\-]*range\b",
    ],
    "binary_search": [r"\bbinary[\s_\-]*search\b", r"\blower[\s_\-]*bound\b", r"\bupper[\s_\-]*bound\b", r"\bbsearch\b"],
    "tree_dp": [r"\btree[\s_\-]*dp\b", r"\bdynamic[\s_\-]*programming[\s_\-]*on[\s_\-]*trees?\b", r"\bdp[\s_\-]*on[\s_\-]*trees?\b"],
    "tree": [r"\bbinary[\s_\-]*tree\b", r"\broot[\s_\-]*to[\s_\-]*leaf\b", r"\bbst\b", r"\btrees?\b", r"\bsubtrees?\b"],
    "bfs": [r"\bbfs\b", r"\bbreadth[\s_\-]*first\b", r"\blevel[\s_\-]*order\b"],
    "dfs": [r"\bdfs\b", r"\bdepth[\s_\-]*first\b", r"\bbacktracking\b"],
    "dp": [r"\bdp\b", r"\bdynamic[\s_\-]*programming\b", r"\bmemoization\b", r"\bknapsack\b"],
    "graph": [r"\bgraph\b", r"\bgraphs\b", r"\bdijkstra\b", r"\bshortest[\s_\-]*path\b", r"\btopological\b"],
    "greedy": [r"\bgreedy\b"],
    "sorting": [r"\bsort\b", r"\bsorting\b", r"\btwo[\s_\-]*pointers\b"],
}

CODE_CONCEPT_SIGNATURES = {
    "prefix_sum": [
        r"\bprefix\[", r"\bpref\[", r"\bcsum\[", r"\bpartial_sum\b", r"\baccumulate\b",
        r"\bsuff\[", r"\bsuffix\[", r"pref\[r\]\s*-\s*pref\[l", r"pref\[i\]\s*=\s*pref\[i\s*-\s*1\]",
        r"pref\[i\]\s*\+=", r"\bfindThePrefixCommonArray\b", r"\bmissingInteger\b",
    ],
    "range_query": [
        r"\brangeAddQueries\b", r"\bqueries\[i\]", r"\bsegment_tree\b", r"\bfenwick\b",
        r"\btree\[", r"\bquery\(", r"\bupdate\(", r"pref\[r\]\s*-\s*pref\[l",
    ],
    "binary_search": [r"\blower_bound\b", r"\bupper_bound\b", r"\bbinary_search\b", r"low\s*<=\s*high", r"mid\s*=\s*(?:low\s*\+\s*high|low\s*\+\s*\(high)"],
    "tree": [r"TreeNode", r"root->left", r"root->right", r"left\s*=\s*nullptr", r"\.left", r"\.right"],
    "bfs": [r"queue<", r"collections\.deque", r"q\.pop\(\)", r"q\.push\("],
    "dfs": [r"dfs\(", r"visited\[", r"backtrack\("],
    "dp": [r"dp\[", r"memo\[", r"vector<vector<int>>\s*dp"],
    "graph": [r"adj\[", r"vector<vector<int>>\s*adj", r"edges\b"],
}

def extract_query_concepts(query: str) -> List[str]:
    q_low = query.lower()
    return [c for c, pats in CP_CONCEPT_PATTERNS.items() if any(re.search(p, q_low) for p in pats)]

def matches_any_concept(text: str, concepts: List[str]) -> bool:
    if not concepts:
        return True
    t_low = text.lower()
    for c in concepts:
        if any(re.search(p, t_low) for p in CP_CONCEPT_PATTERNS.get(c, [])):
            return True
        if any(re.search(s, text) for s in CODE_CONCEPT_SIGNATURES.get(c, [])):
            return True
    return False

def compute_token_match_score(title: str, q_tokens: List[str]) -> float:
    if not title or not q_tokens:
        return 0.0
    matched = sum(1 for t in q_tokens if re.search(r"\b" + re.escape(t) + r"\b", title.lower()))
    ratio = matched / len(q_tokens)
    if ratio == 1.0:
        return 0.90
    elif ratio >= 0.5:
        return 0.70 + 0.15 * ratio
    return 0.0



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


def index_user_github_solutions(user_id: str, db: Session) -> Dict[str, Any]:
    """
    Safely indexes unindexed solution files from the user's connected GitHub profile into ChromaDB.
    Never overwrites or deletes existing vectors.
    """
    try:
        from pathlib import Path
        import httpx
        from app.models.profile import PlatformProfile
        from app.collectors.github import GitHubCollector, extract_problem_info_from_path, detect_language_from_filename, ALLOWED_EXTENSIONS

        profile = db.query(PlatformProfile).filter(
            PlatformProfile.user_id == user_id,
            PlatformProfile.platform == "github"
        ).first()

        if not profile or not profile.handle:
            return {"newly_indexed": 0, "total_chunks": 0}

        full_repo = profile.handle
        parts = full_repo.split("/")
        if len(parts) != 2:
            return {"newly_indexed": 0, "total_chunks": 0}
        owner, repo = parts[0], parts[1]
        token = profile.api_key

        collector = GitHubCollector(access_token=token)
        collector.lookup_solution(full_repo, problem_title="prefix")

        import app.collectors.github as gh_module
        cache_data = gh_module._REPO_TREE_CACHE.get(f"{owner.lower()}/{repo.lower()}")
        if not cache_data or not cache_data.get("paths"):
            return {"newly_indexed": 0, "total_chunks": 0}

        all_paths = cache_data["paths"]
        branch = cache_data.get("branch", "main")
        code_files = [p for p in all_paths if Path(p).suffix.lower() in ALLOWED_EXTENSIONS]

        chroma_store = get_chroma_store()
        indexed_sub_ids = chroma_store.get_indexed_submission_ids(user_id)

        unindexed = []
        for file_path in code_files:
            norm_path = file_path.replace("\\", "/")
            f_parts = norm_path.split("/")
            filename = f_parts[-1]
            base_folder = f_parts[-2] if len(f_parts) > 1 else Path(filename).stem
            sub_id = f"gh_{base_folder}_{filename}"
            if sub_id not in indexed_sub_ids:
                unindexed.append((file_path, base_folder, filename, sub_id))

        if not unindexed:
            return {"newly_indexed": 0, "total_chunks": 0}

        headers = {"User-Agent": "CP-Knowledge-Retrieval-System"}
        if token:
            headers["Authorization"] = f"Bearer {token.strip()}"

        all_chunk_ids = []
        all_chunks_text = []
        all_metadatas = []

        with httpx.Client(timeout=10.0) as client:
            for file_path, base_folder, filename, sub_id in unindexed:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
                code = None
                try:
                    resp = client.get(raw_url, headers=headers)
                    if resp.status_code == 200 and resp.text.strip():
                        code = resp.text
                except Exception:
                    pass

                if not code:
                    continue

                platform, problem_id, clean_title = extract_problem_info_from_path(file_path)
                lang = detect_language_from_filename(filename)

                doc_text = (
                    f"# Problem: {clean_title} ({problem_id})\n"
                    f"**Platform**: github | **Language**: {lang} | **Verdict**: ACCEPTED\n"
                    f"**Difficulty**: N/A | **Tags**: None\n"
                    f"**Notes**: Synced from GitHub repo {full_repo}: {file_path}\n\n"
                    f"## Source Code\n```{lang}\n{code}\n```"
                )

                chunks = chunk_text(doc_text, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
                for idx, chunk in enumerate(chunks):
                    all_chunk_ids.append(f"{user_id}_{sub_id}_chunk_{idx}")
                    all_chunks_text.append(chunk)
                    all_metadatas.append({
                        "user_id": str(user_id),
                        "submission_id": str(sub_id),
                        "platform": "github",
                        "language": str(lang),
                        "problem_id": str(problem_id),
                        "problem_title": str(clean_title),
                        "chunk_index": idx,
                        "total_chunks": len(chunks),
                        "has_source_code": True,
                    })

        if not all_chunks_text:
            return {"newly_indexed": 0, "total_chunks": 0}

        embedder = get_embedding_service()
        all_embeddings = embedder.embed_batch(all_chunks_text)

        total_vectors = chroma_store.batch_upsert_raw_chunks(
            ids=all_chunk_ids,
            embeddings=all_embeddings,
            documents=all_chunks_text,
            metadatas=all_metadatas,
            batch_size=250
        )

        return {"newly_indexed": len(unindexed), "total_chunks": total_vectors}
    except Exception as e:
        logger.warning(f"Incremental GitHub solution indexing failed for user '{user_id}': {e}")
        return {"newly_indexed": 0, "total_chunks": 0}


def index_all_user_submissions(user_id: str, db: Session) -> Dict[str, Any]:
    """
    Indexes all submissions owned by the user into ChromaDB using high-performance batching.
    Also incrementally indexes unindexed solution files from user's connected GitHub profile.
    Skips submissions that are already indexed into ChromaDB.
    """
    # Safe incremental indexing for connected GitHub repository
    gh_res = index_user_github_solutions(user_id=user_id, db=db)
    gh_newly_indexed = gh_res.get("newly_indexed", 0)
    gh_total_chunks = gh_res.get("total_chunks", 0)

    user_submissions = db.query(SubmissionRecord).filter(
        SubmissionRecord.user_id == user_id
    ).all()

    total_submissions = len(user_submissions)
    if total_submissions == 0:
        INDEXING_PROGRESS[user_id] = {
            "status": "completed",
            "total": gh_newly_indexed,
            "processed": gh_newly_indexed,
            "already_indexed": 0,
            "newly_indexed": gh_newly_indexed,
            "percent": 100,
            "message": f"GitHub solutions indexed: {gh_newly_indexed}." if gh_newly_indexed else "No submissions found for user."
        }
        return {
            "total_submissions_processed": 0,
            "already_indexed_count": 0,
            "newly_indexed_count": gh_newly_indexed,
            "total_chunks_created": gh_total_chunks,
            "total_vectors_upserted": gh_total_chunks,
            "message": f"GitHub solutions newly indexed: {gh_newly_indexed}." if gh_newly_indexed else "Already indexed: 0. Newly indexed: 0."
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

    # Fast path: If all SQLite submissions are already indexed, return
    if not unindexed_submissions:
        logger.info(f"All {already_indexed_count} SQLite submissions already indexed for user '{user_id}'.")
        msg = f"Already indexed: {already_indexed_count}. Newly indexed: {gh_newly_indexed}."
        res_info = {
            "status": "completed",
            "total": total_submissions,
            "processed": total_submissions,
            "already_indexed": already_indexed_count,
            "newly_indexed": gh_newly_indexed,
            "percent": 100,
            "message": msg
        }
        INDEXING_PROGRESS[user_id] = res_info
        return {
            "total_submissions_processed": total_submissions,
            "already_indexed_count": already_indexed_count,
            "newly_indexed_count": gh_newly_indexed,
            "total_chunks_created": gh_total_chunks,
            "total_vectors_upserted": gh_total_chunks,
            "message": msg
        }
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

    try:
        # Initialize progress status
        INDEXING_PROGRESS[user_id] = {
            "status": "in_progress",
            "total": total_submissions,
            "processed": already_indexed_count,
            "already_indexed": already_indexed_count,
            "newly_indexed": 0,
            "percent": int((already_indexed_count / total_submissions) * 100),
            "message": f"Chunking submissions... {already_indexed_count} / {total_submissions}"
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

        # Generate embeddings in manageable chunk batches
        embedder = get_embedding_service()
        BATCH_SIZE = 64
        all_embeddings: List[List[float]] = []

        for i in range(0, len(all_chunks_text), BATCH_SIZE):
            batch_texts = all_chunks_text[i : i + BATCH_SIZE]
            batch_embs = embedder.embed_batch(batch_texts)
            all_embeddings.extend(batch_embs)

            chunks_done = len(all_embeddings)
            prog_ratio = chunks_done / max(len(all_chunks_text), 1)
            processed_so_far = already_indexed_count + int(prog_ratio * len(unindexed_submissions))
            INDEXING_PROGRESS[user_id] = {
                "status": "in_progress",
                "total": total_submissions,
                "processed": min(processed_so_far, total_submissions),
                "already_indexed": already_indexed_count,
                "newly_indexed": int(prog_ratio * len(unindexed_submissions)),
                "percent": int((min(processed_so_far, total_submissions) / total_submissions) * 100),
                "message": f"Embedding chunks... {chunks_done} / {len(all_chunks_text)}"
            }

        # Execute batch upsert into ChromaDB
        total_vectors = chroma_store.batch_upsert_raw_chunks(
            ids=all_chunk_ids,
            embeddings=all_embeddings,
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to index submissions for user '{user_id}': {exc}", exc_info=True)
        INDEXING_PROGRESS[user_id] = {
            "status": "failed",
            "total": total_submissions,
            "processed": already_indexed_count,
            "already_indexed": already_indexed_count,
            "newly_indexed": 0,
            "percent": 0,
            "message": f"Indexing failed: {exc}",
        }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {exc}",
        )


def search_user_knowledge(
    user_id: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    min_similarity: float = SIMILARITY_THRESHOLD,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Executes hybrid semantic vector and keyword search over the authenticated user's indexed code knowledge.
    Combines ChromaDB vector search with exact/fuzzy problem ID, problem title, tags, and source code matching.
    Guarantees strict multi-user isolation and safe fallback on embedding failures.
    """
    cleaned_query = clean_query_text(query)
    if not cleaned_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty."
        )

    q_lower = cleaned_query.lower()
    q_tokens = [t for t in re.split(r"[^a-zA-Z0-9_\-]+", q_lower) if len(t) >= 2 and t not in STOP_WORDS]
    target_concepts = extract_query_concepts(query)

    # 1. Vector Search via ChromaDB
    vector_candidates: List[Dict[str, Any]] = []
    vector_error = None
    try:
        embedder = get_embedding_service()
        query_vector = embedder.embed_text(cleaned_query)
        if query_vector:
            chroma_store = get_chroma_store()
            vector_candidates = chroma_store.search(
                user_id=user_id,
                query_embedding=query_vector,
                top_k=max(top_k * 5, 50),
                min_similarity=0.20,  # capture candidates for concept gating & scoring
            )
    except Exception as e:
        logger.warning(f"ChromaDB search failed for query '{cleaned_query}' (user_id={user_id}): {e}")
        vector_error = str(e)
        if db is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Semantic search failed during query embedding: {e}"
            )

    # Safe Fallback: If vector search returned 0 candidates or failed, search ChromaDB documents directly
    if not vector_candidates:
        try:
            chroma_store = get_chroma_store()
            c_docs = chroma_store._collection.get(
                where={"user_id": str(user_id)},
                include=["metadatas", "documents"]
            )
            for cid, meta, doc in zip(c_docs.get("ids", []), c_docs.get("metadatas", []), c_docs.get("documents", [])):
                p_title = meta.get("problem_title", "")
                p_id = meta.get("problem_id", "")
                combined = f"{p_title}\n{doc}"
                if target_concepts and matches_any_concept(combined, target_concepts):
                    vector_candidates.append({
                        "id": cid,
                        "submission_id": meta.get("submission_id", cid),
                        "platform": meta.get("platform", "unknown"),
                        "language": meta.get("language", "unknown"),
                        "problem_id": p_id,
                        "problem_title": p_title,
                        "chunk_index": meta.get("chunk_index", 0),
                        "total_chunks": meta.get("total_chunks", 1),
                        "has_source_code": meta.get("has_source_code", True),
                        "document_text": doc,
                        "similarity_score": 0.85,
                        "distance": 0.15,
                        "metadata": meta,
                    })
                elif not target_concepts:
                    t_score = compute_token_match_score(p_title, q_tokens)
                    if t_score >= 0.70:
                        vector_candidates.append({
                            "id": cid,
                            "submission_id": meta.get("submission_id", cid),
                            "platform": meta.get("platform", "unknown"),
                            "language": meta.get("language", "unknown"),
                            "problem_id": p_id,
                            "problem_title": p_title,
                            "chunk_index": meta.get("chunk_index", 0),
                            "total_chunks": meta.get("total_chunks", 1),
                            "has_source_code": meta.get("has_source_code", True),
                            "document_text": doc,
                            "similarity_score": t_score,
                            "distance": 1.0 - t_score,
                            "metadata": meta,
                        })
        except Exception as fb_err:
            logger.warning(f"ChromaDB direct document fallback scan encountered an error: {fb_err}")

    # 2. Database Keyword & Metadata Match (when DB session is available)
    db_candidates: List[Dict[str, Any]] = []
    if db is not None:
        try:
            user_subs = db.query(SubmissionRecord).filter(
                SubmissionRecord.user_id == user_id
            ).all()

            src_recs = db.query(SubmissionSourceCode).filter(
                SubmissionSourceCode.user_id == user_id
            ).all()
            src_map: Dict[str, str] = {
                sr.submission_id: sr.source_code for sr in src_recs if sr.source_code and sr.source_code.strip()
            }
            for s in user_subs:
                if s.submission_id not in src_map and s.code and s.code.strip() and not s.code.startswith("// Source code not provided"):
                    src_map[s.submission_id] = s.code

            for sub in user_subs:
                pid = (sub.problem_id or "").lower()
                title = (sub.problem_title or "").lower()
                tags_list = [str(t).lower() for t in (sub.tags or [])]
                tags_str = " ".join(tags_list)
                raw_code = (src_map.get(sub.submission_id) or "")
                combined_text = f"{title} {pid} {tags_str} {raw_code}"

                match_score = 0.0

                # Exact Problem ID match (e.g. "2000A", "158A", "2254C1", "swap-nodes-in-pairs")
                if pid and (pid == q_lower or pid in q_tokens or q_lower == pid.lstrip("0")):
                    match_score = max(match_score, 0.98)
                elif pid and any(term == pid for term in q_tokens):
                    match_score = max(match_score, 0.92)

                # Problem Title match (e.g. "Two Sum", "Marenol")
                if title and (q_lower == title or q_lower in title):
                    match_score = max(match_score, 0.95)
                elif not target_concepts:
                    t_score = compute_token_match_score(title, q_tokens)
                    if t_score > 0:
                        match_score = max(match_score, t_score)

                # Tag match (e.g. "binary search", "bfs", "sortings")
                if any(q_lower == t or t in q_lower for t in tags_list):
                    match_score = max(match_score, 0.92)
                elif any(term in tags_str for term in q_tokens if len(term) >= 3):
                    match_score = max(match_score, 0.82)

                # Target concept match in code/tags/title
                if target_concepts and matches_any_concept(combined_text, target_concepts):
                    match_score = max(match_score, 0.85)

                if match_score >= 0.70:
                    has_code = bool(src_map.get(sub.submission_id)) or sub.has_source_code
                    doc_text = construct_submission_document(sub, src_map.get(sub.submission_id) if has_code else None)
                    db_candidates.append({
                        "id": f"{user_id}_{sub.submission_id}_match",
                        "submission_id": sub.submission_id,
                        "platform": sub.platform,
                        "language": sub.language,
                        "problem_id": sub.problem_id,
                        "problem_title": sub.problem_title,
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "has_source_code": has_code,
                        "document_text": doc_text,
                        "similarity_score": round(match_score, 4),
                        "distance": round(max(0.0, 1.0 - match_score), 4),
                        "metadata": {
                            "user_id": str(user_id),
                            "submission_id": str(sub.submission_id),
                            "platform": str(sub.platform or "unknown"),
                            "language": str(sub.language or "unknown"),
                            "problem_id": str(sub.problem_id or ""),
                            "problem_title": str(sub.problem_title or "Unknown Problem"),
                            "has_source_code": bool(has_code),
                        }
                    })
        except Exception as e:
            logger.warning(f"Database keyword matching encountered an error: {e}")

    # 3. Deduplicate and Merge Results
    problem_map: Dict[str, Dict[str, Any]] = {}

    for item in db_candidates:
        pid = (item.get("problem_id") or "").strip().lower()
        title = (item.get("problem_title") or "").strip().lower()
        key = pid if (pid and pid != "unknown") else title
        problem_map[key] = item

    for item in vector_candidates:
        pid = (item.get("problem_id") or "").strip().lower()
        title = (item.get("problem_title") or "").strip().lower()
        key = pid if (pid and pid != "unknown") else title
        doc_text = item.get("document_text", "")
        v_score = item.get("similarity_score", 0.0)

        # Check exact title or problem ID in vector item
        if (title and q_lower == title) or (pid and pid == q_lower):
            v_score = max(v_score, 0.96)
        elif not target_concepts:
            t_score = compute_token_match_score(title, q_tokens)
            if t_score > 0:
                v_score = max(v_score, t_score)

        # Concept relevance gating
        if target_concepts:
            has_concept = matches_any_concept(f"{title}\n{doc_text}", target_concepts)
            if not has_concept:
                # Document has none of the requested CP concepts; filter out noise
                if v_score < 0.65:
                    continue
            else:
                # Document matches target concept; boost score based on direct code / title match
                t_low = title.lower()
                has_code_sig = any(re.search(s, doc_text) for c in target_concepts for s in CODE_CONCEPT_SIGNATURES.get(c, []))
                has_title_pat = any(re.search(p, t_low) for c in target_concepts for p in CP_CONCEPT_PATTERNS.get(c, []))

                if has_title_pat or has_code_sig:
                    v_score = min(0.99, max(v_score, 0.88) + (0.06 if has_code_sig else 0.03))
                else:
                    v_score = min(0.95, max(v_score, 0.78) + 0.05)
        else:
            # When no specific concept is requested, filter low vector noise
            if v_score < max(min_similarity, 0.45):
                continue

        item["similarity_score"] = round(v_score, 4)

        if key not in problem_map:
            problem_map[key] = item
        else:
            existing = problem_map[key]
            # Boost score if found by both vector and keyword search
            boosted_score = min(1.0, max(existing["similarity_score"], item["similarity_score"]) + 0.05)
            existing["similarity_score"] = round(boosted_score, 4)
            if item.get("has_source_code"):
                existing["has_source_code"] = True
                existing["document_text"] = item.get("document_text", existing.get("document_text"))

    # 4. Sort results descending by score
    sorted_results = sorted(
        problem_map.values(),
        key=lambda x: (x["similarity_score"], 1 if x.get("has_source_code") else 0),
        reverse=True
    )

    final_results = sorted_results[:top_k]

    message = (
        f"Found {len(final_results)} relevant results."
        if final_results
        else "No sufficiently relevant submissions found for this query."
    )

    return {
        "query": cleaned_query,
        "top_k": top_k,
        "min_similarity_threshold": min_similarity,
        "total_results": len(final_results),
        "results": final_results,
        "message": message,
    }

