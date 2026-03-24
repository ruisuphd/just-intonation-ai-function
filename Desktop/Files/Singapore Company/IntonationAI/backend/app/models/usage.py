import uuid

from sqlalchemy import Column, Date, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Usage(Base):
    __tablename__ = "usage"
    __table_args__ = (UniqueConstraint("user_id", "period_start", name="uq_usage_user_period"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    period_start = Column(Date, nullable=False)
    coach_sessions_count = Column(Integer, default=0)
    warmup_sessions_count = Column(Integer, default=0)
    created_at = Column(Date, server_default=func.now())
