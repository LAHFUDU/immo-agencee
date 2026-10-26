import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk
from app.models.enums import MatchCategory, MatchStatus, enum_column


class Match(UUIDPk, Timestamps, Base):
    """Persisted request <-> property match. One row per pair (unique), updated in place.

    `is_active` is False when the property stopped being eligible (sold, rented, price raised
    above budget...) or the request was closed. History is preserved, never deleted.
    """

    __tablename__ = "matches"
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customer_requests.id", ondelete="CASCADE"), nullable=False)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[MatchCategory] = mapped_column(enum_column(MatchCategory, "match_category"), nullable=False)
    explanation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        enum_column(MatchStatus, "match_status"), default=MatchStatus.SUGGESTED, nullable=False
    )
    customer_feedback: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Signature of the match state that was last notified; a new notification is only sent
    # when this materially changes (category/price) or an agent explicitly asks for it.
    notified_signature: Mapped[str | None] = mapped_column(String(120))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    request = relationship("CustomerRequest", lazy="joined")
    property = relationship("Property", lazy="joined")

    __table_args__ = (
        UniqueConstraint("request_id", "property_id", name="uq_matches_request_property"),
        Index("ix_matches_request_active", "request_id", "is_active"),
    )
