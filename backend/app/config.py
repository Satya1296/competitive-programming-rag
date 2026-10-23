import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv()
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
USERS_DATA_DIR = DATA_DIR / "users"
CHROMADB_DIR = DATA_DIR / "chromadb"

# Ensure essential data directories exist
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
USERS_DATA_DIR.mkdir(parents=True, exist_ok=True)
CHROMADB_DIR.mkdir(parents=True, exist_ok=True)

# Relational Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# Security / Authentication Settings
# JWT Secret Key - Never hard-code production secrets; read from env or default for dev
SECRET_KEY = os.getenv(
    "SECRET_KEY", "cprag_dev_secret_key_8492049182390182309128301923"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

# Phase 4: Vector Database & Embeddings Configuration
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
CHROMA_PERSIST_DIR = str(CHROMADB_DIR)
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "cp_submissions")
CHROMA_HNSW_SPACE = os.getenv("CHROMA_HNSW_SPACE", "cosine")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "20"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.22"))

# Phase 5: LLM & RAG Configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini", "openai", "groq", "mock"
LLM_MODEL = os.getenv("LLM_MODEL") or "gemini-3.5-flash-lite"
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
MAX_RAG_CONTEXT_CHARS = int(os.getenv("MAX_RAG_CONTEXT_CHARS", "6000"))



