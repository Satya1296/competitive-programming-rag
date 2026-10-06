import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base


class SubmissionSourceCode(Base):
    __tablename__ = "submission_source_codes"

    id = Column(String, primary_key=True, default=lambda: f"src_{uuid.uuid4().hex[:12]}")
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    submission_id = Column(String, ForeignKey("submissions.id"), index=True, nullable=False)
    language = Column(String, nullable=False)
    source_code = Column(Text, nullable=False)
    filename = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User")
    submission = relationship("SubmissionRecord")
