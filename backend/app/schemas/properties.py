import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import PropertyStatus, TransactionType
from app.schemas.common import ORM, UserRef


class OwnerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=255)
    company: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=5000)


class OwnerOut(ORM):
    id: uuid.UUID
    full_name: str
    phone: str | None
    email: str | None
    address: str | None
    company: str | None
    notes: str | None


class PropertyBase(BaseModel):
    property_type: str = Field(min_length=1, max_length=32)
    transaction_type: TransactionType
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    city: str = Field(min_length=2, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    surface: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="MAD", pattern=r"^[A-Z]{3}$")
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    floor: int | None = Field(default=None, ge=-5, le=200)
    features: list[str] = []
    is_published: bool = False
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    internal_notes: str | None = Field(default=None, max_length=20000)
    owner_id: uuid.UUID | None = None
    responsible_id: uuid.UUID | None = None

    @field_validator("city", "title")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class PropertyCreate(PropertyBase):
    status: PropertyStatus = PropertyStatus.AVAILABLE
    owner: OwnerIn | None = None  # create a new owner inline


class PropertyUpdate(BaseModel):
    property_type: str | None = Field(default=None, max_length=32)
    transaction_type: TransactionType | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=255)
    surface: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    floor: int | None = Field(default=None, ge=-5, le=200)
    features: list[str] | None = None
    is_published: bool | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    internal_notes: str | None = Field(default=None, max_length=20000)
    owner_id: uuid.UUID | None = None
    responsible_id: uuid.UUID | None = None


class StatusChange(BaseModel):
    status: PropertyStatus
    reason: str | None = Field(default=None, max_length=255)


class BulkStatusChange(StatusChange):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class PhotoOut(ORM):
    id: uuid.UUID
    filename: str
    position: int
    url: str = ""


class DocumentOut(ORM):
    id: uuid.UUID
    filename: str
    label: str | None
    content_type: str
    size: int
    is_confidential: bool
    created_at: datetime


class PropertyOut(BaseModel):
    id: uuid.UUID
    reference: str
    property_type: str
    transaction_type: TransactionType
    title: str
    description: str | None
    city: str
    neighborhood: str | None
    surface: Decimal | None
    price: Decimal
    currency: str
    bedrooms: int | None
    bathrooms: int | None
    floor: int | None
    features: list[str]
    status: PropertyStatus
    status_changed_at: datetime
    is_published: bool
    responsible: UserRef | None
    photos: list[PhotoOut]
    created_at: datetime
    updated_at: datetime
    # Confidential: null unless the user holds properties.view_confidential
    address: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    internal_notes: str | None = None
    owner: OwnerOut | None = None
    confidential_visible: bool = False
    active_match_count: int | None = None
