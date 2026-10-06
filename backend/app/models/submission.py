from sqlalchemy import Column, String, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base


class SubmissionRecord(Base):
    __tablename__ = "submissions"

    id = Column(String, primary_key=True)       # Format: {user_id}_{platform}_{submission_id}
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    platform = Column(String, index=True, nullable=False)
    problem_id = Column(String, nullable=False)
    problem_title = Column(String, nullable=False)
    problem_url = Column(String, nullable=False)
    submission_id = Column(String, nullable=False)
    submission_url = Column(String, nullable=True)
    language = Column(String, nullable=False)
    verdict = Column(String, nullable=False)
    time_complexity = Column(String, nullable=True)
    space_complexity = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    tags = Column(JSON, nullable=False, default=[])
    execution_time_ms = Column(Integer, nullable=True)
    memory_bytes = Column(Integer, nullable=True)
    submitted_at = Column(String, nullable=False)
    code = Column(Text, nullable=False)
    code_source = Column(String, default="api_metadata")  # "api_metadata", "user_upload", "github_sync"
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="submissions")

    @property
    def has_source_code(self) -> bool:
        """Return True if genuine source code is attached, False if metadata-only."""
        if not self.code or not self.code.strip():
            return False
        if self.code_source == "api_metadata" and self.code.startswith("// Source code not provided"):
            return False
        return True

