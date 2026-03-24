import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    stripe_customer_id = Column(String(128))
    stripe_sub_id = Column(String(128), nullable=True)
    plan = Column(String(32), default="free")
    status = Column(String(32), default="active")
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    last_stripe_event_created = Column(Integer, nullable=True)
