import logging
import threading
from typing import List, Optional
from app.config import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

_embedding_service_instance: Optional["EmbeddingService"] = None
_service_lock = threading.Lock()


class EmbeddingService:
    """
    Thread-safe singleton service wrapper around SentenceTransformers for local vector embeddings.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._init_error: Optional[str] = None
        self._model_lock = threading.Lock()
        # Model is loaded lazily on first embedding request to preserve memory on boot

    def _init_model(self):
        with self._model_lock:
            if self._model is not None:
                return
            try:
                # Constrain PyTorch thread pool on CPU to reduce thread-local memory overhead on container environments
                try:
                    import torch
                    torch.set_num_threads(1)
                    if hasattr(torch, "set_num_interop_threads"):
                        torch.set_num_interop_threads(1)
                except Exception:
                    pass

                from sentence_transformers import SentenceTransformer
                logger.info(f"Initializing SentenceTransformer model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                self._init_error = None
                logger.info("SentenceTransformer model loaded successfully.")
            except Exception as e:
                self._init_error = str(e)
                logger.error(f"Failed to initialize SentenceTransformer model '{self.model_name}': {e}")
                raise RuntimeError(f"Embedding model initialization failed for '{self.model_name}': {e}") from e

    def embed_text(self, text: str) -> List[float]:
        if not text or not str(text).strip():
            return []
        if self._model is None:
            if self._init_error is not None:
                raise RuntimeError(f"Embedding model initialization failed for '{self.model_name}': {self._init_error}")
            self._init_model()
        
        try:
            import torch
            with torch.inference_mode():
                vector = self._model.encode(str(text), convert_to_numpy=True)
                return vector.tolist()
        except Exception:
            vector = self._model.encode(str(text), convert_to_numpy=True)
            return vector.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._model is None:
            if self._init_error is not None:
                raise RuntimeError(f"Embedding model initialization failed for '{self.model_name}': {self._init_error}")
            self._init_model()

        clean_texts = [str(t) if (t and str(t).strip()) else " " for t in texts]
        try:
            import torch
            with torch.inference_mode():
                vectors = self._model.encode(clean_texts, batch_size=16, show_progress_bar=False, convert_to_numpy=True)
                return vectors.tolist()
        except Exception:
            vectors = self._model.encode(clean_texts, batch_size=16, show_progress_bar=False, convert_to_numpy=True)
            return vectors.tolist()


def get_embedding_service(model_name: str = EMBEDDING_MODEL_NAME) -> EmbeddingService:
    global _embedding_service_instance
    if _embedding_service_instance is None or _embedding_service_instance.model_name != model_name:
        with _service_lock:
            if _embedding_service_instance is None or _embedding_service_instance.model_name != model_name:
                _embedding_service_instance = EmbeddingService(model_name=model_name)
    return _embedding_service_instance


def reset_embedding_service() -> None:
    """Reset the singleton instance for testing isolation."""
    global _embedding_service_instance
    with _service_lock:
        _embedding_service_instance = None

