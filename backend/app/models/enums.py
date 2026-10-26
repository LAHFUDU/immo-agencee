import enum

from sqlalchemy import Enum as SAEnum


class StrEnum(str, enum.Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class TransactionType(StrEnum):
    SALE = "sale"
    RENT = "rent"


class ContactMethod(StrEnum):
    PHONE = "phone"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    ANY = "any"


class CustomerSource(StrEnum):
    WEBSITE = "website"
    REFERRAL = "referral"
    PHONE = "phone"
    WALK_IN = "walk_in"
    SOCIAL_MEDIA = "social_media"
    PORTAL = "portal"
    OTHER = "other"


class RequestStatus(StrEnum):
    NEW = "new"
    TO_CONTACT = "to_contact"
    CONTACTED = "contacted"
    PROPOSED = "proposed"
    VISIT_SCHEDULED = "visit_scheduled"
    NEGOTIATION = "negotiation"
    CONVERTED = "converted"
    CLOSED_LOST = "closed_lost"
    ARCHIVED = "archived"


CLOSED_REQUEST_STATUSES = {RequestStatus.CONVERTED, RequestStatus.CLOSED_LOST, RequestStatus.ARCHIVED}
OPEN_REQUEST_STATUSES = [s for s in RequestStatus if s not in CLOSED_REQUEST_STATUSES]


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class PropertyStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    UNDER_NEGOTIATION = "under_negotiation"
    SOLD = "sold"
    RENTED = "rented"
    UNAVAILABLE = "unavailable"
    ARCHIVED = "archived"


class MatchCategory(StrEnum):
    EXACT = "exact"
    STRONG = "strong"
    PARTIAL = "partial"
    INELIGIBLE = "ineligible"  # never stored as an active match; only shown as "non conforme"


CATEGORY_RANK = {MatchCategory.EXACT: 3, MatchCategory.STRONG: 2, MatchCategory.PARTIAL: 1, MatchCategory.INELIGIBLE: 0}


class MatchStatus(StrEnum):
    SUGGESTED = "suggested"
    PROPOSED = "proposed"
    INTERESTED = "interested"
    VISIT_SCHEDULED = "visit_scheduled"
    REJECTED = "rejected"


class ActivityType(StrEnum):
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    VISIT = "visit"
    OFFER = "offer"
    NOTE = "note"
    WEB_CONTACT = "web_contact"
    STATUS_CHANGE = "status_change"


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class VisitStatus(StrEnum):
    SCHEDULED = "scheduled"
    DONE = "done"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class DealStatus(StrEnum):
    NEGOTIATION = "negotiation"
    RESERVED = "reserved"
    WON = "won"
    LOST = "lost"
    CANCELLED = "cancelled"


ACTIVE_DEAL_STATUSES = [DealStatus.NEGOTIATION, DealStatus.RESERVED]


class OfferParty(StrEnum):
    CUSTOMER = "customer"
    OWNER = "owner"


class OfferStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"
    WITHDRAWN = "withdrawn"


class TokenPurpose(StrEnum):
    INVITE = "invite"
    RESET = "reset"


def enum_column(enum_cls: type[enum.Enum], name: str) -> SAEnum:
    """Store enums as VARCHAR + CHECK constraint (portable, painless to migrate)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
