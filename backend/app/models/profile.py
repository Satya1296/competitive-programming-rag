import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base


class PlatformProfile(Base):
    __tablename__ = "platform_profiles"

    id = Column(String, primary_key=True, default=lambda: f"prof_{uuid.uuid4().hex[:12]}")
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)  # "codeforces", "leetcode", "codechef"
    handle = Column(String, nullable=False)     # e.g., "tourist"
    api_key = Column(String, nullable=True)     # Codeforces API Key (optional)
    api_secret = Column(String, nullable=True)  # Codeforces API Secret (optional, encrypted/protected)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="profiles")
