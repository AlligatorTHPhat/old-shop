from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class SystemLog(Base):
    """Audit log, written by the DB functions in database/02_functions/system."""

    __tablename__ = "system_log"

    log_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(Integer)
    details = Column(Text)
    ip_address = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_system_log_user", "user_id"),
        Index("idx_system_log_action", "action"),
        Index("idx_system_log_created_at", "created_at"),
    )


class ViolationLog(Base):
    __tablename__ = "violation_log"

    log_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False, index=True)
    reason = Column(String(500), nullable=False)
    action_taken = Column(String(50), nullable=False)  # BAN, DEACTIVATE, PRODUCT_REMOVAL...
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")

    __table_args__ = (
        Index("idx_violation_log_user", "user_id"),
        Index("idx_violation_log_created_at", "created_at"),
    )


class SystemFeedback(Base):
    """Feedback and contact-form messages from users or guests."""

    __tablename__ = "system_feedback"

    feedback_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=True, index=True)
    guest_email = Column(String(255), nullable=True)
    subject = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(SmallInteger, default=0)  # 0: pending, 1: reviewed, 2: resolved
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="feedbacks")

    __table_args__ = (
        Index("idx_system_feedback_user", "user_id"),
        Index("idx_system_feedback_status", "status"),
        Index("idx_system_feedback_created_at", "created_at"),
    )
