import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk, utcnow
from app.models.enums import DealStatus, OfferParty, OfferStatus, TransactionType, enum_column

deal_ref_seq = Sequence("deal_ref_seq", metadata=Base.metadata)


class CommissionRule(UUIDPk, Timestamps, Base):
    """Editable commission rules. The most specific active rule (highest priority) applies."""

    __tablename__ = "commission_rules"
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType, "transaction_type"), nullable=False)
    property_type: Mapped[str | None] = mapped_column(ForeignKey("property_categories.code", ondelete="SET NULL", onupdate="CASCADE"))
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("0"), nullable=False)
    fixed_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("rate_percent >= 0 AND rate_percent <= 100", name="rate_range"),
        CheckConstraint("fixed_amount >= 0", name="fixed_positive"),
    )


class Deal(UUIDPk, Timestamps, Base):
    """A sale or rental transaction between a customer and a property."""

    __tablename__ = "deals"
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer_requests.id", ondelete="SET NULL"), index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    transaction_type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType, "transaction_type"), nullable=False)
    status: Mapped[DealStatus] = mapped_column(enum_column(DealStatus, "deal_status"), default=DealStatus.NEGOTIATION, nullable=False)
    asking_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    agreed_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="MAD", nullable=False)
    commission_rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("commission_rules.id", ondelete="SET NULL"))
    commission_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    commission_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expected_closing_date: Mapped[date | None] = mapped_column(Date)
    actual_closing_date: Mapped[date | None] = mapped_column(Date)
    lost_reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    # True while this deal holds the property's reservation. A partial unique index ensures only one
    # deal can hold it, unless an administrator explicitly authorised a parallel reservation.
    holds_reservation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reservation_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reservation_override_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    customer = relationship("Customer", lazy="joined")
    property = relationship("Property", lazy="joined")
    agent = relationship("User", foreign_keys=[agent_id], lazy="joined")
    offers: Mapped[list["Offer"]] = relationship(
        back_populates="deal", order_by="Offer.offered_at", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index(
            "uq_deals_single_reservation",
            "property_id",
            unique=True,
            postgresql_where=text("holds_reservation AND NOT reservation_override"),
        ),
        CheckConstraint("agreed_price IS NULL OR agreed_price >= 0", name="agreed_price_positive"),
    )


class Offer(UUIDPk, Base):
    __tablename__ = "offers"
    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    party: Mapped[OfferParty] = mapped_column(enum_column(OfferParty, "offer_party"), nullable=False)
    status: Mapped[OfferStatus] = mapped_column(enum_column(OfferStatus, "offer_status"), default=OfferStatus.PENDING, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    deal: Mapped[Deal] = relationship(back_populates="offers")

    __table_args__ = (CheckConstraint("amount >= 0", name="amount_positive"),)
