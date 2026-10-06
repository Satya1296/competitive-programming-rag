import logging
from typing import List, Optional
from app.config import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

_embedding_service_instance: Optional["EmbeddingService"] = None


class EmbeddingService:
    """
    Singleton service wrapper around SentenceTransformers for local vector embeddings.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._init_model()

    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Initializing SentenceTransformer model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize SentenceTransformer model '{self.model_name}': {e}")
            raise RuntimeError(f"Embedding model initialization failed for '{self.model_name}': {e}") from e

    def embed_text(self, text: str) -> List[float]:
        if not text:
            return []
        if self._model is None:
            self._init_model()
        
        vector = self._model.encode(text, convert_to_numpy=True)
        return vector.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._model is None:
            self._init_model()

        vectors = self._model.encode(texts, batch_size=16, show_progress_bar=False, convert_to_numpy=True)
        return vectors.tolist()


def get_embedding_service(model_name: str = EMBEDDING_MODEL_NAME) -> EmbeddingService:
    global _embedding_service_instance
    if _embedding_service_instance is None or _embedding_service_instance.model_name != model_name:
        _embedding_service_instance = EmbeddingService(model_name=model_name)
    return _embedding_service_instance
