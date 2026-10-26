"""Shared helpers: pagination, record scoping (row-level authorization) and serializers."""

import uuid
from typing import Any

from fastapi import HTTPException, Query, status
from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.models import (
    Customer,
    CustomerRequest,
    Deal,
    Match,
    Property,
    PropertyCategory,
    PropertyFeature,
    User,
    Visit,
)
from app.models.enums import CATEGORY_RANK, MatchCategory, RequestStatus
from app.schemas.common import UserRef
from app.schemas.crm import CustomerOut, MatchOut, MatchSummary, RequestOut, VisitOut
from app.schemas.deals import DealOut, OfferOut
from app.schemas.properties import OwnerOut, PhotoOut, PropertyOut


class Pagination:
    def __init__(self, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
        self.page = page
        self.page_size = page_size


def paginate(db: Session, stmt: Select, p: Pagination) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(stmt.limit(p.page_size).offset((p.page - 1) * p.page_size)).unique().all()
    return list(rows), total


def not_found(what: str = "Élément") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} introuvable.")


def parse_uuid(value: str | None):
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Identifiant invalide.") from exc


# ---------------------------------------------------------------- row-level scopes
# Out-of-scope records are reported as 404 (not 403) so their existence is not revealed.


def request_scope(p: Principal):
    if p.can("requests.view_all"):
        return None
    return or_(
        CustomerRequest.assigned_agent_id == p.id,
        CustomerRequest.created_by_id == p.id,
        and_(CustomerRequest.assigned_agent_id.is_(None), CustomerRequest.status == RequestStatus.NEW),
    )


def customer_scope(p: Principal):
    if p.can("customers.view_all"):
        return None
    req_cond = request_scope(p)
    sub = exists().where(CustomerRequest.customer_id == Customer.id)
    if req_cond is not None:
        sub = sub.where(req_cond)
    return or_(Customer.assigned_agent_id == p.id, Customer.created_by_id == p.id, sub)


def visit_scope(p: Principal):
    if p.can("visits.view_all"):
        return None
    return or_(Visit.agent_id == p.id, Visit.created_by_id == p.id)


def deal_scope(p: Principal):
    if p.can("deals.view_all"):
        return None
    return or_(Deal.agent_id == p.id, Deal.created_by_id == p.id)


def scoped_get(db: Session, model, obj_id, scope_cond, what: str):
    stmt = select(model).where(model.id == obj_id)
    if scope_cond is not None:
        stmt = stmt.where(scope_cond)
    obj = db.scalars(stmt).unique().first()
    if obj is None:
        raise not_found(what)
    return obj


def get_request_scoped(db: Session, p: Principal, request_id) -> CustomerRequest:
    return scoped_get(db, CustomerRequest, request_id, request_scope(p), "Demande")


def get_customer_scoped(db: Session, p: Principal, customer_id) -> Customer:
    return scoped_get(db, Customer, customer_id, customer_scope(p), "Client")


def ensure_user(db: Session, user_id, *, agent: bool = False) -> User:
    u = db.get(User, user_id)
    if u is None or not u.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Utilisateur inconnu ou désactivé.")
    return u


def validate_category(db: Session, code: str) -> None:
    c = db.get(PropertyCategory, code)
    if c is None or not c.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Type de bien inconnu : {code}")


def validate_features(db: Session, codes: list[str]) -> list[str]:
    known = set(db.scalars(select(PropertyFeature.code)).all())
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Équipement(s) inconnu(s) : {', '.join(unknown)}")
    return sorted(set(codes))


# ---------------------------------------------------------------- serializers


def user_ref(u) -> UserRef | None:
    return UserRef(id=u.id, full_name=u.full_name) if u else None


def photo_url(photo) -> str:
    return f"/api/files/photos/{photo.id}"


def property_out(prop: Property, p: Principal | None, match_count: int | None = None) -> PropertyOut:
    confidential = bool(p and p.can("properties.view_confidential"))
    return PropertyOut(
        id=prop.id,
        reference=prop.reference,
        property_type=prop.property_type,
        transaction_type=prop.transaction_type,
        title=prop.title,
        description=prop.description,
        city=prop.city,
        neighborhood=prop.neighborhood,
        surface=prop.surface,
        price=prop.price,
        currency=prop.currency,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        floor=prop.floor,
        features=prop.features or [],
        status=prop.status,
        status_changed_at=prop.status_changed_at,
        is_published=prop.is_published,
        responsible=user_ref(prop.responsible),
        photos=[PhotoOut(id=ph.id, filename=ph.filename, position=ph.position, url=photo_url(ph)) for ph in prop.photos],
        created_at=prop.created_at,
        updated_at=prop.updated_at,
        address=prop.address if confidential else None,
        latitude=prop.latitude if confidential else None,
        longitude=prop.longitude if confidential else None,
        internal_notes=prop.internal_notes if confidential else None,
        owner=OwnerOut.model_validate(prop.owner) if (confidential and prop.owner) else None,
        confidential_visible=confidential,
        active_match_count=match_count,
    )


def customer_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=c.id,
        reference=c.reference,
        full_name=c.full_name,
        phone=c.phone,
        email=c.email,
        preferred_contact=c.preferred_contact,
        source=c.source,
        preferences=c.preferences,
        internal_notes=c.internal_notes,
        assigned_agent=user_ref(c.assigned_agent),
        is_archived=c.is_archived,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def match_summaries(db: Session, request_ids: list) -> dict:
    if not request_ids:
        return {}
    rows = db.execute(
        select(Match.request_id, Match.score, Match.category).where(
            Match.request_id.in_(request_ids), Match.is_active.is_(True)
        )
    ).all()
    out: dict = {}
    for rid, score, cat in rows:
        s = out.setdefault(rid, {"active_count": 0, "best_score": None, "best_category": None})
        s["active_count"] += 1
        if s["best_score"] is None or score > s["best_score"]:
            s["best_score"] = score
        if s["best_category"] is None or CATEGORY_RANK[cat] > CATEGORY_RANK[MatchCategory(s["best_category"])]:
            s["best_category"] = cat
    return out


def request_out(r: CustomerRequest, summary: dict | None) -> RequestOut:
    s = summary or {"active_count": 0, "best_score": None, "best_category": None}
    return RequestOut(
        id=r.id,
        reference=r.reference,
        customer=customer_out(r.customer),
        property_type=r.property_type,
        transaction_type=r.transaction_type,
        budget_min=r.budget_min,
        budget_max=r.budget_max,
        currency=r.currency,
        city=r.city,
        neighborhood=r.neighborhood,
        surface_min=r.surface_min,
        surface_max=r.surface_max,
        bedrooms_min=r.bedrooms_min,
        bathrooms_min=r.bathrooms_min,
        required_features=r.required_features or [],
        preferred_features=r.preferred_features or [],
        comments=r.comments,
        internal_notes=r.internal_notes,
        priority=r.priority,
        status=r.status,
        source=r.source,
        assigned_agent=user_ref(r.assigned_agent),
        assigned_at=r.assigned_at,
        next_follow_up_at=r.next_follow_up_at,
        first_contacted_at=r.first_contacted_at,
        closed_at=r.closed_at,
        close_reason=r.close_reason,
        created_at=r.created_at,
        updated_at=r.updated_at,
        matches=MatchSummary(**s),
    )


def match_out(m: Match | None, *, req: CustomerRequest, prop: Property, score=None, category=None, explanation=None) -> MatchOut:
    photo = prop.photos[0] if prop.photos else None
    return MatchOut(
        id=m.id if m else None,
        request_id=req.id,
        property_id=prop.id,
        property_reference=prop.reference,
        property_title=prop.title,
        property_city=prop.city,
        property_neighborhood=prop.neighborhood,
        property_price=prop.price,
        property_currency=prop.currency,
        property_surface=prop.surface,
        property_bedrooms=prop.bedrooms,
        property_status=prop.status.value,
        property_photo=photo_url(photo) if photo else None,
        request_reference=req.reference,
        customer_name=req.customer.full_name,
        agent=user_ref(req.assigned_agent),
        score=m.score if m else score,
        category=m.category if m else category,
        explanation=m.explanation if m else explanation,
        is_active=m.is_active if m else False,
        status=m.status if m else None,
        customer_feedback=m.customer_feedback if m else None,
        rejection_reason=m.rejection_reason if m else None,
        computed_at=m.computed_at if m else None,
        notified_at=m.notified_at if m else None,
    )


def visit_out(v: Visit, p: Principal) -> VisitOut:
    # The agent in charge of a visit needs the address even without the confidential permission.
    show_address = p.can("properties.view_confidential") or v.agent_id == p.id
    return VisitOut(
        id=v.id,
        request_id=v.request_id,
        request_reference=v.request.reference if v.request else None,
        customer_id=v.customer_id,
        customer_name=v.customer.full_name,
        customer_phone=v.customer.phone,
        property_id=v.property_id,
        property_reference=v.property.reference,
        property_title=v.property.title,
        property_city=v.property.city,
        property_address=v.property.address if show_address else None,
        agent=user_ref(v.agent),
        scheduled_at=v.scheduled_at,
        duration_minutes=v.duration_minutes,
        status=v.status,
        notes=v.notes,
        customer_feedback=v.customer_feedback,
        created_at=v.created_at,
    )


def deal_out(d: Deal, p: Principal) -> DealOut:
    show_commission = p.can("commissions.view") or d.agent_id == p.id
    return DealOut(
        id=d.id,
        reference=d.reference,
        customer_id=d.customer_id,
        customer_name=d.customer.full_name,
        request_id=d.request_id,
        property_id=d.property_id,
        property_reference=d.property.reference,
        property_title=d.property.title,
        property_status=d.property.status.value,
        agent=user_ref(d.agent),
        transaction_type=d.transaction_type,
        status=d.status,
        asking_price=d.asking_price,
        agreed_price=d.agreed_price,
        currency=d.currency,
        commission_rate=d.commission_rate if show_commission else None,
        commission_amount=d.commission_amount if show_commission else None,
        commission_overridden=d.commission_overridden,
        expected_closing_date=d.expected_closing_date,
        actual_closing_date=d.actual_closing_date,
        lost_reason=d.lost_reason,
        notes=d.notes,
        holds_reservation=d.holds_reservation,
        reservation_override=d.reservation_override,
        offers=[OfferOut.model_validate(o) for o in d.offers],
        closed_at=d.closed_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )
