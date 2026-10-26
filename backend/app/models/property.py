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
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPk, utcnow
from app.models.enums import PropertyStatus, TransactionType, enum_column

property_ref_seq = Sequence("property_ref_seq", metadata=Base.metadata)


class PropertyCategory(Base):
    """Configurable property types (apartment, villa, land...)."""

    __tablename__ = "property_categories"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    has_rooms: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PropertyFeature(Base):
    """Configurable amenities catalogue (parking, garden, elevator...)."""

    __tablename__ = "property_features"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Owner(UUIDPk, Timestamps, Base):
    """Property owner / supplier. Confidential: visible only with properties.view_owner."""

    __tablename__ = "owners"
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    address: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Property(UUIDPk, Timestamps, Base):
    __tablename__ = "properties"
    reference: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    property_type: Mapped[str] = mapped_column(
        ForeignKey("property_categories.code", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    transaction_type: Mapped[TransactionType] = mapped_column(enum_column(TransactionType, "transaction_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    city_key: Mapped[str] = mapped_column(String(100), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    neighborhood_key: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(255))  # restricted visibility
    surface: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="MAD", nullable=False)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[int | None] = mapped_column(Integer)
    features: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list, nullable=False)
    status: Mapped[PropertyStatus] = mapped_column(
        enum_column(PropertyStatus, "property_status"), default=PropertyStatus.AVAILABLE, nullable=False
    )
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    internal_notes: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("owners.id", ondelete="SET NULL"), index=True)
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    owner: Mapped[Owner | None] = relationship(lazy="joined")
    responsible = relationship("User", foreign_keys=[responsible_id], lazy="joined")
    photos: Mapped[list["PropertyPhoto"]] = relationship(
        back_populates="property", order_by="PropertyPhoto.position", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="price_positive"),
        CheckConstraint("surface IS NULL OR surface > 0", name="surface_positive"),
        CheckConstraint("bedrooms IS NULL OR bedrooms >= 0", name="bedrooms_positive"),
        CheckConstraint("bathrooms IS NULL OR bathrooms >= 0", name="bathrooms_positive"),
        Index("ix_properties_match", "status", "transaction_type", "property_type", "city_key"),
        Index("ix_properties_features", "features", postgresql_using="gin"),
        Index("ix_properties_created_at", "created_at"),
    )


class PropertyPhoto(UUIDPk, Base):
    __tablename__ = "property_photos"
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    property: Mapped[Property] = relationship(back_populates="photos")


class PropertyDocument(UUIDPk, Base):
    __tablename__ = "property_documents"
    property_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String(160))
    is_confidential: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
