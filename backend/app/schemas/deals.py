import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import DealStatus, OfferParty, OfferStatus, TransactionType
from app.schemas.common import ORM, UserRef


class DealCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None
    property_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    expected_closing_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)


class DealUpdate(BaseModel):
    agent_id: uuid.UUID | None = None
    agreed_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    expected_closing_date: date | None = None
    notes: str | None = Field(default=None, max_length=10000)


class CommissionOverride(BaseModel):
    commission_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=3)
    commission_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    reset: bool = False


class ReserveIn(BaseModel):
    override: bool = False


class WinIn(BaseModel):
    agreed_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    closing_date: date | None = None


class CloseIn(BaseModel):
    reason: str = Field(min_length=2, max_length=255)


class OfferIn(BaseModel):
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    party: OfferParty
    notes: str | None = Field(default=None, max_length=5000)
    offered_at: datetime | None = None


class OfferStatusIn(BaseModel):
    status: OfferStatus


class OfferOut(ORM):
    id: uuid.UUID
    amount: Decimal
    party: OfferParty
    status: OfferStatus
    notes: str | None
    offered_at: datetime


class DealOut(BaseModel):
    id: uuid.UUID
    reference: str
    customer_id: uuid.UUID
    customer_name: str
    request_id: uuid.UUID | None
    property_id: uuid.UUID
    property_reference: str
    property_title: str
    property_status: str
    agent: UserRef | None
    transaction_type: TransactionType
    status: DealStatus
    asking_price: Decimal | None
    agreed_price: Decimal | None
    currency: str
    commission_rate: Decimal | None = None
    commission_amount: Decimal | None = None
    commission_overridden: bool = False
    expected_closing_date: date | None
    actual_closing_date: date | None
    lost_reason: str | None
    notes: str | None
    holds_reservation: bool
    reservation_override: bool
    offers: list[OfferOut]
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CommissionRuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    transaction_type: TransactionType
    property_type: str | None = None
    min_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    max_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    rate_percent: Decimal = Field(ge=0, le=100, max_digits=6, decimal_places=3)
    fixed_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    priority: int = 0
    is_active: bool = True


class CommissionRuleOut(ORM):
    id: uuid.UUID
    name: str
    transaction_type: TransactionType
    property_type: str | None
    min_price: Decimal | None
    max_price: Decimal | None
    rate_percent: Decimal
    fixed_amount: Decimal
    priority: int
    is_active: bool
