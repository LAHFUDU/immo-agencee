from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import CustomerRequest, Match, Property
from app.models.enums import MatchStatus, PropertyStatus
from app.services import audit, matching
from app.services.matching import STATUS_LABELS
from app.services.notifications import notify


def interested_agents(db: Session, prop: Property) -> set:
    """Agents of requests to which this property has been proposed (or is under discussion)."""
    rows = db.scalars(
        select(CustomerRequest.assigned_agent_id)
        .join(Match, Match.request_id == CustomerRequest.id)
        .where(
            Match.property_id == prop.id,
            Match.is_active.is_(True),
            Match.status.in_([MatchStatus.PROPOSED, MatchStatus.INTERESTED, MatchStatus.VISIT_SCHEDULED]),
        )
    ).all()
    return {r for r in rows if r}


def change_status(
    db: Session,
    prop: Property,
    new_status: PropertyStatus,
    *,
    user_id=None,
    ip: str | None = None,
    reason: str | None = None,
    refresh: bool = True,
) -> bool:
    """Single entry point for property status changes: audit, notifications and re-matching.
    Returns False if the status did not change."""
    old = prop.status
    if old == new_status:
        return False
    recipients = interested_agents(db, prop) | ({prop.responsible_id} if prop.responsible_id else set())
    prop.status = new_status
    prop.status_changed_at = utcnow()
    audit.log(
        db,
        user_id=user_id,
        action="status_change",
        entity_type="property",
        entity_id=prop.id,
        label=prop.reference,
        changes={"status": {"old": old.value, "new": new_status.value}, **({"reason": reason} if reason else {})},
        ip=ip,
    )
    notify(
        db,
        recipients,
        type="property_status",
        title=f"{prop.reference} : {STATUS_LABELS[old.value]} → {STATUS_LABELS[new_status.value]}",
        body=f"{prop.title}" + (f" — {reason}" if reason else ""),
        link=f"/app/properties/{prop.id}",
        entity_type="property",
        entity_id=prop.id,
        dedupe_key=f"prop_status:{prop.id}:{new_status.value}:{prop.status_changed_at.isoformat()}",
        exclude_user_id=user_id,
    )
    if refresh:
        matching.refresh_for_property(db, prop)
    return True
