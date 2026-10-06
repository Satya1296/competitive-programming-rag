from typing import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import DATABASE_URL

# SQLite requires check_same_thread=False for multi-threaded FastAPI execution
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(bind_engine):
    """
    Safely inspect SQLite database tables and apply incremental column additions
    if missing (api_key, api_secret on platform_profiles).
    Preserves all existing tables and rows without data loss.
    """
    try:
        inspector = inspect(bind_engine)
        if inspector.has_table("platform_profiles"):
            existing_cols = {col["name"] for col in inspector.get_columns("platform_profiles")}
            with bind_engine.begin() as conn:
                if "api_key" not in existing_cols:
                    conn.execute(text("ALTER TABLE platform_profiles ADD COLUMN api_key TEXT"))
                if "api_secret" not in existing_cols:
                    conn.execute(text("ALTER TABLE platform_profiles ADD COLUMN api_secret TEXT"))
    except Exception as exc:
        print(f"Warning: SQLite migration check returned error: {exc}")


def init_db():
    """Create all relational database tables and run incremental column migrations."""
    import app.models  # Ensures models are registered with Base.metadata before table creation
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
