import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.enums import (
    ActivityType,
    ContactMethod,
    CustomerSource,
    MatchCategory,
    MatchStatus,
    Priority,
    RequestStatus,
    TaskStatus,
    TransactionType,
    VisitStatus,
)
from app.schemas.common import ORM, UserRef


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32, pattern=r"^[0-9+()\-.\s]{6,32}$")
    email: EmailStr | None = None
    preferred_contact: ContactMethod = ContactMethod.PHONE
    source: CustomerSource = CustomerSource.OTHER
    preferences: str | None = Field(default=None, max_length=5000)
    internal_notes: str | None = Field(default=None, max_length=20000)
    assigned_agent_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _contact(self):
        if not self.phone and not self.email:
            raise ValueError("Un téléphone ou un e-mail est requis.")
        return self


class CustomerUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32, pattern=r"^[0-9+()\-.\s]{6,32}$")
    email: EmailStr | None = None
    preferred_contact: ContactMethod | None = None
    source: CustomerSource | None = None
    preferences: str | None = Field(default=None, max_length=5000)
    internal_notes: str | None = Field(default=None, max_length=20000)
    assigned_agent_id: uuid.UUID | None = None


class CustomerOut(ORM):
    id: uuid.UUID
    reference: str
    full_name: str
    phone: str | None
    email: str | None
    preferred_contact: ContactMethod
    source: CustomerSource
    preferences: str | None
    internal_notes: str | None
    assigned_agent: UserRef | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class DuplicateCandidate(BaseModel):
    id: uuid.UUID
    reference: str
    full_name: str
    phone: str | None
    email: str | None
    reason: str


class RequestCriteria(BaseModel):
    property_type: str = Field(min_length=1, max_length=32)
    transaction_type: TransactionType
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="MAD", pattern=r"^[A-Z]{3}$")
    city: str = Field(min_length=2, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=120)
    surface_min: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    surface_max: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    bedrooms_min: int | None = Field(default=None, ge=0, le=50)
    bathrooms_min: int | None = Field(default=None, ge=0, le=50)
    required_features: list[str] = []
    preferred_features: list[str] = []
    comments: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _ranges(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("Le budget minimum doit être inférieur au budget maximum.")
        if self.surface_min is not None and self.surface_max is not None and self.surface_min > self.surface_max:
            raise ValueError("La surface minimum doit être inférieure à la surface maximum.")
        return self


class RequestCreate(RequestCriteria):
    customer_id: uuid.UUID | None = None
    customer: CustomerIn | None = None  # create the customer inline
    priority: Priority = Priority.NORMAL
    source: CustomerSource = CustomerSource.OTHER
    assigned_agent_id: uuid.UUID | None = None
    next_follow_up_at: datetime | None = None
    internal_notes: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def _customer(self):
        if not self.customer_id and not self.customer:
            raise ValueError("Sélectionnez un client existant ou saisissez un nouveau client.")
        return self


class RequestUpdate(BaseModel):
    property_type: str | None = Field(default=None, max_length=32)
    transaction_type: TransactionType | None = None
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    city: str | None = Field(default=None, min_length=2, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=120)
    surface_min: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    surface_max: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    bedrooms_min: int | None = Field(default=None, ge=0, le=50)
    bathrooms_min: int | None = Field(default=None, ge=0, le=50)
    required_features: list[str] | None = None
    preferred_features: list[str] | None = None
    comments: str | None = Field(default=None, max_length=5000)
    priority: Priority | None = None
    status: RequestStatus | None = None
    close_reason: str | None = Field(default=None, max_length=255)
    next_follow_up_at: datetime | None = None
    internal_notes: str | None = Field(default=None, max_length=20000)


class AssignIn(BaseModel):
    agent_id: uuid.UUID | None


class MatchSummary(BaseModel):
    active_count: int
    best_score: int | None
    best_category: MatchCategory | None


class RequestOut(BaseModel):
    id: uuid.UUID
    reference: str
    customer: CustomerOut
    property_type: str
    transaction_type: TransactionType
    budget_min: Decimal | None
    budget_max: Decimal | None
    currency: str
    city: str
    neighborhood: str | None
    surface_min: Decimal | None
    surface_max: Decimal | None
    bedrooms_min: int | None
    bathrooms_min: int | None
    required_features: list[str]
    preferred_features: list[str]
    comments: str | None
    internal_notes: str | None
    priority: Priority
    status: RequestStatus
    source: CustomerSource
    assigned_agent: UserRef | None
    assigned_at: datetime | None
    next_follow_up_at: datetime | None
    first_contacted_at: datetime | None
    closed_at: datetime | None
    close_reason: str | None
    created_at: datetime
    updated_at: datetime
    matches: MatchSummary


class RequestCreated(BaseModel):
    request: RequestOut
    match_count: int
    message: str
    duplicate_customers: list[DuplicateCandidate] = []


class MatchOut(BaseModel):
    id: uuid.UUID | None
    request_id: uuid.UUID
    property_id: uuid.UUID
    property_reference: str
    property_title: str
    property_city: str
    property_neighborhood: str | None
    property_price: Decimal
    property_currency: str
    property_surface: Decimal | None
    property_bedrooms: int | None
    property_status: str
    property_photo: str | None = None
    request_reference: str | None = None
    customer_name: str | None = None
    agent: UserRef | None = None
    score: int
    category: MatchCategory
    explanation: dict
    is_active: bool
    status: MatchStatus | None
    customer_feedback: str | None = None
    rejection_reason: str | None = None
    computed_at: datetime | None = None
    notified_at: datetime | None = None


class MatchAction(BaseModel):
    status: MatchStatus
    customer_feedback: str | None = Field(default=None, max_length=2000)
    rejection_reason: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _reason(self):
        if self.status == MatchStatus.REJECTED and not (self.rejection_reason or "").strip():
            raise ValueError("Un motif de rejet est requis.")
        return self


class ActivityIn(BaseModel):
    type: ActivityType
    summary: str = Field(min_length=1, max_length=5000)
    occurred_at: datetime | None = None
    property_id: uuid.UUID | None = None


class ActivityOut(ORM):
    id: uuid.UUID
    type: ActivityType
    summary: str
    occurred_at: datetime
    customer_id: uuid.UUID | None
    request_id: uuid.UUID | None
    property_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    created_by: UserRef | None
    created_at: datetime


class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime
    assigned_to_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_at: datetime | None = None
    status: TaskStatus | None = None
    assigned_to_id: uuid.UUID | None = None


class TaskOut(ORM):
    id: uuid.UUID
    title: str
    description: str | None
    due_at: datetime
    status: TaskStatus
    assigned_to: UserRef
    customer_id: uuid.UUID | None
    request_id: uuid.UUID | None
    completed_at: datetime | None
    created_at: datetime


class VisitIn(BaseModel):
    property_id: uuid.UUID
    request_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    match_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    scheduled_at: datetime
    duration_minutes: int = Field(default=45, ge=10, le=600)
    notes: str | None = Field(default=None, max_length=5000)


class VisitUpdate(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=10, le=600)
    status: VisitStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)
    customer_feedback: str | None = Field(default=None, max_length=5000)
    agent_id: uuid.UUID | None = None


class VisitOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID | None
    request_reference: str | None
    customer_id: uuid.UUID
    customer_name: str
    customer_phone: str | None
    property_id: uuid.UUID
    property_reference: str
    property_title: str
    property_city: str
    property_address: str | None
    agent: UserRef | None
    scheduled_at: datetime
    duration_minutes: int
    status: VisitStatus
    notes: str | None
    customer_feedback: str | None
    created_at: datetime
