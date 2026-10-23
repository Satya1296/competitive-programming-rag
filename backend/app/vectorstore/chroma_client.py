import logging
import threading
from typing import List, Dict, Any, Optional
from app.config import (
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    CHROMA_HNSW_SPACE,
    SIMILARITY_THRESHOLD,
    DEFAULT_TOP_K,
)

logger = logging.getLogger(__name__)

_chroma_store_instance: Optional["ChromaVectorStore"] = None


class ChromaVectorStore:
    """
    Persistent ChromaDB vector store manager with explicit Cosine metric space,
    minimum similarity thresholding, and forced multi-user scoping.
    """

    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        collection_name: str = CHROMA_COLLECTION_NAME,
        hnsw_space: str = CHROMA_HNSW_SPACE,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.hnsw_space = hnsw_space
        self._client = None
        self._collection = None
        self._store_lock = threading.Lock()
        # ChromaDB client is initialized lazily on first access to preserve memory

    def _ensure_store(self):
        if self._collection is not None:
            return
        with self._store_lock:
            if self._collection is not None:
                return
            self._init_store()

    def _init_store(self):
        try:
            import chromadb
            from chromadb.config import Settings
            logger.info(f"Initializing Persistent ChromaDB client at: {self.persist_dir}")
            settings = Settings(anonymized_telemetry=False, is_persistent=True)
            self._client = chromadb.PersistentClient(path=self.persist_dir, settings=settings)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={
                    "hnsw:space": self.hnsw_space,
                    "description": "Competitive Programming Submissions Knowledge Store"
                }
            )
            meta = self._collection.metadata or {}
            self.effective_space = meta.get("hnsw:space", self.hnsw_space)
            logger.info(f"ChromaDB collection '{self.collection_name}' ready (effective_space={self.effective_space}).")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB at '{self.persist_dir}': {e}")
            raise RuntimeError(f"ChromaDB initialization failed: {e}") from e

    def upsert_chunks(
        self,
        user_id: str,
        submission_id: str,
        platform: str,
        language: str,
        problem_id: str,
        problem_title: str,
        chunks: List[str],
        embeddings: List[List[float]],
        has_source_code: bool = True,
    ) -> int:
        """
        Upserts document chunks and embeddings into ChromaDB with deterministic IDs and user_id metadata.
        """
        self._ensure_store()
        if not chunks or not embeddings or len(chunks) != len(embeddings):
            return 0

        ids: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc_id = f"{user_id}_{submission_id}_chunk_{idx}"
            ids.append(doc_id)
            metadatas.append({
                "user_id": str(user_id),
                "submission_id": str(submission_id),
                "platform": str(platform or "unknown"),
                "language": str(language or "unknown"),
                "problem_id": str(problem_id or ""),
                "problem_title": str(problem_title or "Unknown Problem"),
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "has_source_code": bool(has_source_code),
            })

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        logger.info(f"Upserted {len(ids)} vectors into ChromaDB for submission {submission_id} (user_id={user_id}, has_code={has_source_code}).")
        return len(ids)

    def get_indexed_submission_ids(self, user_id: str) -> set:
        """
        Retrieves a set of all submission_ids belonging strictly to user_id that are already stored in ChromaDB.
        """
        self._ensure_store()
        try:
            results = self._collection.get(
                where={"user_id": str(user_id)},
                include=["metadatas"]
            )
            metadatas = results.get("metadatas", [])
            indexed_ids = set()
            if metadatas:
                for meta in metadatas:
                    if meta and "submission_id" in meta:
                        indexed_ids.add(str(meta["submission_id"]))
            return indexed_ids
        except Exception as e:
            logger.warning(f"Failed to fetch indexed submission IDs for user_id={user_id}: {e}")
            return set()

    def batch_upsert_raw_chunks(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        batch_size: int = 250,
    ) -> int:
        """
        Upserts large collections of chunks into ChromaDB in safe batches to prevent memory/payload limits.
        """
        self._ensure_store()
        if not ids or not embeddings or len(ids) != len(embeddings) or len(ids) != len(documents):
            return 0

        total_upserted = 0
        total_items = len(ids)

        for i in range(0, total_items, batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]
            batch_documents = documents[i : i + batch_size]
            batch_metadatas = metadatas[i : i + batch_size]

            self._collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                documents=batch_documents,
                metadatas=batch_metadatas
            )
            total_upserted += len(batch_ids)

        logger.info(f"Successfully batch-upserted {total_upserted} vectors into ChromaDB.")
        return total_upserted

    def search(
        self,
        user_id: str,
        query_embedding: List[float],
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = SIMILARITY_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic vector search forced strictly by user_id metadata filter.
        Deduplicates candidate chunks at the submission level, returning up to top_k UNIQUE SUBMISSIONS
        that satisfy min_similarity threshold.
        """
        if not query_embedding:
            return []

        self._ensure_store()
        # STRICT MANDATORY MULTI-USER FILTER
        where_filter = {"user_id": str(user_id)}

        total_in_coll = self._collection.count()
        if total_in_coll == 0:
            return []

        # Fetch candidate chunks from ChromaDB (fetch candidate pool to ensure top_k unique submissions)
        fetch_n = min(max(top_k * 10, 50), total_in_coll)

        results = None
        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=fetch_n,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"ChromaDB query failed for user_id={user_id}: {e}")

        # If HNSW query filtered out all candidate chunks due to multi-user graph traversal,
        # fallback to direct user-scoped retrieval to ensure complete recall without leakage
        if not results or not results.get("ids") or len(results["ids"][0]) == 0:
            try:
                user_records = self._collection.get(
                    where=where_filter,
                    include=["documents", "metadatas", "embeddings"]
                )
                if user_records and user_records.get("ids") and len(user_records["ids"]) > 0:
                    import numpy as np
                    doc_embs = np.array(user_records["embeddings"], dtype=np.float32)
                    q_emb = np.array(query_embedding, dtype=np.float32)
                    denom = np.linalg.norm(doc_embs, axis=1) * np.linalg.norm(q_emb)
                    denom[denom == 0] = 1e-9
                    cos_sims = np.dot(doc_embs, q_emb) / denom

                    paired = sorted(
                        zip(user_records["ids"], user_records["documents"], user_records["metadatas"], cos_sims),
                        key=lambda x: x[3],
                        reverse=True
                    )
                    top_paired = paired[:top_k * 5]
                    results = {
                        "ids": [[p[0] for p in top_paired]],
                        "documents": [[p[1] for p in top_paired]],
                        "metadatas": [[p[2] for p in top_paired]],
                        "distances": [[round(float(max(0.0, 1.0 - p[3])), 4) for p in top_paired]]
                    }
            except Exception as e:
                logger.warning(f"Fallback direct user retrieval failed: {e}")

        raw_candidates: List[Dict[str, Any]] = []
        if results and results.get("ids") and len(results["ids"]) > 0:
            doc_ids = results["ids"][0]
            documents = results["documents"][0] if results.get("documents") else []
            metadatas = results["metadatas"][0] if results.get("metadatas") else []
            distances = results["distances"][0] if results.get("distances") else []

            for doc_id, doc_text, metadata, dist in zip(doc_ids, documents, metadatas, distances):
                distance_val = float(dist) if dist is not None else 1.0
                effective_space = getattr(self, "effective_space", self.hnsw_space)
                if effective_space == "cosine":
                    similarity_score = max(0.0, 1.0 - distance_val)
                elif effective_space == "ip":
                    similarity_score = max(0.0, distance_val)
                else:  # l2 distance for unit vectors
                    similarity_score = max(0.0, 1.0 - (distance_val / 2.0))

                similarity_score = round(similarity_score, 4)

                # THRESHOLD FILTER: Only include sufficiently relevant results
                if similarity_score >= min_similarity:
                    raw_candidates.append({
                        "id": doc_id,
                        "submission_id": metadata.get("submission_id"),
                        "platform": metadata.get("platform"),
                        "language": metadata.get("language"),
                        "problem_id": metadata.get("problem_id"),
                        "problem_title": metadata.get("problem_title"),
                        "chunk_index": metadata.get("chunk_index", 0),
                        "total_chunks": metadata.get("total_chunks", 1),
                        "has_source_code": metadata.get("has_source_code", True),
                        "document_text": doc_text,
                        "distance": distance_val,
                        "similarity_score": similarity_score,
                        "metadata": metadata
                    })

        # PROBLEM-LEVEL RESULT DEDUPLICATION & RANKING
        # Group candidate chunks by unique problem (problem_id if valid else problem_title)
        problem_map: Dict[str, Dict[str, Any]] = {}
        for item in raw_candidates:
            pid = (item.get("problem_id") or "").strip()
            title = (item.get("problem_title") or "").strip()
            p_key = pid.lower() if (pid and pid.upper() != "UNKNOWN") else title.lower()

            if p_key not in problem_map:
                problem_map[p_key] = item
            else:
                existing = problem_map[p_key]
                # Prioritize source-code attached over metadata-only, then higher similarity score
                item_rank = (1 if item.get("has_source_code") else 0, item.get("similarity_score", 0.0))
                exist_rank = (1 if existing.get("has_source_code") else 0, existing.get("similarity_score", 0.0))
                if item_rank > exist_rank:
                    problem_map[p_key] = item
                elif item_rank == exist_rank and item.get("chunk_index", 0) < existing.get("chunk_index", 0):
                    problem_map[p_key] = item

        # Sort deduplicated unique problem results descending by similarity score (with source code tie-breaker)
        deduped_results = sorted(
            problem_map.values(),
            key=lambda x: (x["similarity_score"], 1 if x.get("has_source_code") else 0),
            reverse=True
        )

        # Slice to top_k unique problems
        return deduped_results[:top_k]

    def delete_submission_vectors(self, user_id: str, submission_id: str) -> int:
        """
        Deletes all vector chunks for a specific submission owned strictly by user_id.
        Prevents orphaned or duplicate chunk vectors during re-indexing.
        """
        self._ensure_store()
        try:
            results = self._collection.get(
                where={"$and": [{"user_id": str(user_id)}, {"submission_id": str(submission_id)}]},
                include=[]
            )
            target_ids = results.get("ids", [])
            if target_ids:
                self._collection.delete(ids=target_ids)
                logger.info(f"Purged {len(target_ids)} old vectors for user_id={user_id}, submission_id={submission_id}.")
                return len(target_ids)
            return 0
        except Exception as e:
            logger.warning(f"Error purging submission vectors for user_id={user_id}, submission_id={submission_id}: {e}")
            return 0

    def delete_user_vectors(self, user_id: str) -> int:
        """
        Deletes all vector chunks owned strictly by user_id.
        Safely clears user data without affecting other users.
        """
        self._ensure_store()
        try:
            results = self._collection.get(
                where={"user_id": str(user_id)},
                include=[]
            )
            target_ids = results.get("ids", [])
            if target_ids:
                self._collection.delete(ids=target_ids)
                logger.info(f"Purged all {len(target_ids)} vectors for user_id={user_id}.")
                return len(target_ids)
            return 0
        except Exception as e:
            logger.warning(f"Error purging vectors for user_id={user_id}: {e}")
            return 0

    def delete_user_platform_vectors(self, user_id: str, platform: str) -> int:
        """
        Deletes all vector documents belonging strictly to user_id for a given platform.
        Used when a user updates/switches platform profile (e.g. Codeforces handle switch).
        """
        self._ensure_store()
        try:
            results = self._collection.get(
                where={"$and": [{"user_id": str(user_id)}, {"platform": str(platform)}]},
                include=[]
            )
            target_ids = results.get("ids", [])
            if target_ids:
                self._collection.delete(ids=target_ids)
                logger.info(f"Purged {len(target_ids)} old {platform} vectors for user_id={user_id}.")
                return len(target_ids)
            return 0
        except Exception as e:
            logger.warning(f"Error purging platform vectors for user_id={user_id}, platform={platform}: {e}")
            return 0


def get_chroma_store(
    persist_dir: str = CHROMA_PERSIST_DIR,
    collection_name: str = CHROMA_COLLECTION_NAME,
    hnsw_space: str = CHROMA_HNSW_SPACE,
) -> ChromaVectorStore:
    global _chroma_store_instance
    if _chroma_store_instance is None or _chroma_store_instance.persist_dir != persist_dir:
        _chroma_store_instance = ChromaVectorStore(
            persist_dir=persist_dir,
            collection_name=collection_name,
            hnsw_space=hnsw_space,
        )
    return _chroma_store_instance
