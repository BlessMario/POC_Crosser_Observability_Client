import uuid
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Index, SmallInteger, Text, func
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class RecordingSession(Base):
    __tablename__ = "recording_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node: Mapped[str] = mapped_column(Text, nullable=False)
    topic_filters: Mapped[list] = mapped_column(JSONB, nullable=False)  # JSON list of topic filters
    state: Mapped[str] = mapped_column(Text, nullable=False, default="CREATED")

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages = relationship("MqttMessage", back_populates="session")

class MqttMessage(Base):
    __tablename__ = "mqtt_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recording_session.id"), index=True)

    ts: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    qos: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    retained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    session = relationship("RecordingSession", back_populates="messages")

Index("ix_msg_session_ts", MqttMessage.session_id, MqttMessage.ts)
Index("ix_msg_session_topic", MqttMessage.session_id, MqttMessage.topic)
Index("ix_msg_payload_gin", MqttMessage.payload_json, postgresql_using="gin")
