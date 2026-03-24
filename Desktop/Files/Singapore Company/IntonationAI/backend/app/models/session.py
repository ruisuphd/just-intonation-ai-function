import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID

from app.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    coach_type = Column(String(64))
    locale = Column(String(32), nullable=False, default="en")
    practice_mode = Column(Boolean, nullable=False, default=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    summary_json = Column(JSON, nullable=True)


class SessionMessage(Base):
    __tablename__ = "session_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    role = Column(String(32))
    content = Column(Text)
    audio_url = Column(String(512), nullable=True)
    analysis_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
