import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk, utcnow
from app.models.enums import (
    ActivityType,
    ContactMethod,
    CustomerSource,
    Priority,
    RequestStatus,
    TaskStatus,
    TransactionType,
    VisitStatus,
    enum_column,
)

customer_ref_seq = Sequence("customer_ref_seq", metadata=Base.metadata)
request_ref_seq = Sequence("request_ref_seq", metadata=Base.metadata)


class Customer(UUIDPk, Timestamps, Base):
    __tablename__ = "customers"
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    phone_key: Mapped[str | None] = mapped_column(String(32), index=True)  # digits only, for search & duplicates
    email: Mapped[str | None] = mapped_column(String(254))
    preferred_contact: Mapped[ContactMethod] = mapped_column(
        enum_column(ContactMethod, "contact_method"), default=ContactMethod.PHONE, nullable=False
    )
    source: Mapped[CustomerSource] = mapped_column(
        enum_column(CustomerSource, "customer_source"), default=CustomerSource.OTHER, nullable=False
    )
    preferences: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assigned_agent = relationship("User", foreign_keys=[assigned_agent_id], lazy="joined")

    __table_args__ = (
        Index("ix_customers_email_lower", func.lower(email)),
        Index("ix_customers_name_lower", func.lower(full_name)),
    )


class CustomerRequest(UUIDPk, Timestamps, Base):
    """A customer's search for a property. Never deleted: closed/archived only."""

    __tablename__ = "customer_requests"
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    property_type: Mapped[str] = mapped_column(
        ForeignKey("property_categories.code", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    transaction_type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType, "transaction_type"), nullable=False)
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="MAD", nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    city_key: Mapped[str] = mapped_column(String(100), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    neighborhood_key: Mapped[str | None] = mapped_column(String(120))
    surface_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    surface_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    bedrooms_min: Mapped[int | None] = mapped_column(Integer)
    bathrooms_min: Mapped[int | None] = mapped_column(Integer)
    required_features: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, nullable=False)
    preferred_features: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[Priority] = mapped_column(enum_column(Priority, "priority"), default=Priority.NORMAL, nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        enum_column(RequestStatus, "request_status"), default=RequestStatus.NEW, nullable=False
    )
    source: Mapped[CustomerSource] = mapped_column(
        enum_column(CustomerSource, "customer_source"), default=CustomerSource.OTHER, nullable=False
    )
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(255))
    follow_up_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    customer: Mapped[Customer] = relationship(lazy="joined")
    assigned_agent = relationship("User", foreign_keys=[assigned_agent_id], lazy="joined")

    __table_args__ = (
        CheckConstraint("budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max", name="budget_range"),
        CheckConstraint("surface_min IS NULL OR surface_max IS NULL OR surface_min <= surface_max", name="surface_range"),
        Index("ix_customer_requests_match", "status", "transaction_type", "property_type", "city_key"),
        Index("ix_customer_requests_created_at", "created_at"),
    )


class Activity(UUIDPk, Base):
    """Contact history: calls, meetings, notes, offers... Append-only."""

    __tablename__ = "activities"
    type: Mapped[ActivityType] = mapped_column(enum_column(ActivityType, "activity_type"), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer_requests.id", ondelete="CASCADE"), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("properties.id", ondelete="SET NULL"))
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    created_by = relationship("User", lazy="joined")


class Task(UUIDPk, Timestamps, Base):
    """Follow-up tasks and reminders."""

    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[TaskStatus] = mapped_column(enum_column(TaskStatus, "task_status"), default=TaskStatus.OPEN, nullable=False)
    assigned_to_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer_requests.id", ondelete="CASCADE"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    assigned_to = relationship("User", foreign_keys=[assigned_to_id], lazy="joined")


class Visit(UUIDPk, Timestamps, Base):
    __tablename__ = "visits"
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customer_requests.id", ondelete="SET NULL"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"))
    agent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    status: Mapped[VisitStatus] = mapped_column(enum_column(VisitStatus, "visit_status"), default=VisitStatus.SCHEDULED, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    customer_feedback: Mapped[str | None] = mapped_column(Text)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    customer: Mapped[Customer] = relationship(lazy="joined")
    property = relationship("Property", lazy="joined")
    agent = relationship("User", foreign_keys=[agent_id], lazy="joined")
    request = relationship("CustomerRequest", lazy="select")
