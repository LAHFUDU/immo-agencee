"""Deal (sale / rental transaction) lifecycle with property-status consistency.

Every transition locks the property row (SELECT ... FOR UPDATE) so two concurrent requests
cannot both reserve or close the same property; a partial unique index on deals backs this up.
"""

from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import Activity, CustomerRequest, Deal, Property
from app.models.enums import (
    ACTIVE_DEAL_STATUSES,
    ActivityType,
    DealStatus,
    PropertyStatus,
    RequestStatus,
    TransactionType,
)
from app.services import audit, commissions
from app.services.app_settings import get_setting
from app.services.notifications import notify, users_with_permission
from app.services.properties import change_status

DEAL_STATUS_LABELS = {
    "negotiation": "Négociation",
    "reserved": "Réservé",
    "won": "Conclue",
    "lost": "Perdue",
    "cancelled": "Annulée",
}

CLOSED_PROPERTY = {PropertyStatus.SOLD, PropertyStatus.RENTED, PropertyStatus.ARCHIVED}


def lock_property(db: Session, property_id) -> Property:
    prop = db.scalar(select(Property).where(Property.id == property_id).with_for_update(of=Property))
    if prop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bien introuvable.")
    return prop


def _other_active(db: Session, deal: Deal) -> list[Deal]:
    return list(
        db.scalars(
            select(Deal).where(
                Deal.property_id == deal.property_id, Deal.id != deal.id, Deal.status.in_(ACTIVE_DEAL_STATUSES)
            )
        ).all()
    )


def _log_activity(db: Session, deal: Deal, user_id, summary: str) -> None:
    db.add(
        Activity(
            type=ActivityType.STATUS_CHANGE,
            summary=summary,
            customer_id=deal.customer_id,
            request_id=deal.request_id,
            property_id=deal.property_id,
            deal_id=deal.id,
            created_by_id=user_id,
        )
    )


def _notify_change(db: Session, deal: Deal, user_id, title: str) -> None:
    recipients = set(users_with_permission(db, "deals.view_all"))
    if deal.agent_id:
        recipients.add(deal.agent_id)
    notify(
        db,
        recipients,
        type="deal_status",
        title=title,
        body=f"{deal.property.reference} · {deal.customer.full_name}",
        link=f"/app/deals/{deal.id}",
        entity_type="deal",
        entity_id=deal.id,
        dedupe_key=f"deal:{deal.id}:{deal.status.value}:{utcnow().isoformat()}",
        exclude_user_id=user_id,
    )


def recompute_commission(db: Session, deal: Deal, prop: Property) -> None:
    if deal.commission_overridden:
        return
    price = deal.agreed_price if deal.agreed_price is not None else deal.asking_price
    rule = commissions.find_rule(db, deal.transaction_type, prop.property_type, price)
    rate, amount = commissions.compute(rule, price)
    deal.commission_rule_id = rule.id if rule else None
    deal.commission_rate = rate
    deal.commission_amount = amount


def open_deal(db: Session, deal: Deal, *, user_id, ip=None) -> Deal:
    prop = lock_property(db, deal.property_id)
    if prop.status in CLOSED_PROPERTY or prop.status == PropertyStatus.UNAVAILABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce bien n'est pas disponible pour une nouvelle transaction.")
    if prop.transaction_type != deal.transaction_type:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Le type de transaction ne correspond pas au bien.")
    deal.asking_price = deal.asking_price if deal.asking_price is not None else prop.price
    deal.currency = prop.currency
    db.add(deal)
    db.flush()
    recompute_commission(db, deal, prop)
    if deal.request_id:
        req = db.get(CustomerRequest, deal.request_id)
        if req and req.status not in (RequestStatus.CONVERTED, RequestStatus.ARCHIVED):
            req.status = RequestStatus.NEGOTIATION
    if prop.status == PropertyStatus.AVAILABLE and get_setting(db, "deals")["mark_under_negotiation"]:
        change_status(db, prop, PropertyStatus.UNDER_NEGOTIATION, user_id=user_id, ip=ip, reason=f"Transaction {deal.reference}")
    _log_activity(db, deal, user_id, f"Transaction {deal.reference} ouverte (négociation).")
    audit.log(db, user_id=user_id, action="create", entity_type="deal", entity_id=deal.id, label=deal.reference, ip=ip)
    return deal


def reserve(db: Session, deal: Deal, *, user_id, can_override: bool, override: bool, ip=None) -> Deal:
    if deal.status != DealStatus.NEGOTIATION:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seule une transaction en négociation peut être réservée.")
    prop = lock_property(db, deal.property_id)
    if prop.status in CLOSED_PROPERTY or prop.status == PropertyStatus.UNAVAILABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce bien n'est plus disponible.")
    holders = [d for d in _other_active(db, deal) if d.holds_reservation]
    if holders:
        if not override:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Ce bien est déjà réservé par la transaction {holders[0].reference}. "
                "Une autorisation administrative explicite est requise.",
            )
        if not can_override:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul un administrateur autorisé peut forcer une double réservation.")
        deal.reservation_override = True
        deal.reservation_override_by_id = user_id
    deal.status = DealStatus.RESERVED
    deal.holds_reservation = True
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce bien vient d'être réservé par une autre transaction.") from exc
    change_status(db, prop, PropertyStatus.RESERVED, user_id=user_id, ip=ip, reason=f"Réservation {deal.reference}")
    _log_activity(db, deal, user_id, f"Bien réservé pour la transaction {deal.reference}" + (" (double réservation autorisée)" if deal.reservation_override else ""))
    audit.log(db, user_id=user_id, action="reserve", entity_type="deal", entity_id=deal.id, label=deal.reference,
              changes={"override": deal.reservation_override}, ip=ip)
    _notify_change(db, deal, user_id, f"Transaction {deal.reference} : bien réservé")
    return deal


def win(db: Session, deal: Deal, *, user_id, agreed_price: Decimal | None, closing_date: date | None, ip=None) -> Deal:
    if deal.status not in ACTIVE_DEAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette transaction est déjà clôturée.")
    prop = lock_property(db, deal.property_id)
    if prop.status in CLOSED_PROPERTY:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce bien est déjà vendu, loué ou archivé.")
    if agreed_price is not None:
        deal.agreed_price = agreed_price
    if deal.agreed_price is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Le prix convenu est requis pour conclure.")
    deal.status = DealStatus.WON
    deal.holds_reservation = False
    deal.actual_closing_date = closing_date or utcnow().date()
    deal.closed_at = utcnow()
    recompute_commission(db, deal, prop)

    if deal.request_id:
        req = db.get(CustomerRequest, deal.request_id)
        if req:
            req.status = RequestStatus.CONVERTED
            req.closed_at = utcnow()
    competing = _other_active(db, deal)
    if competing and get_setting(db, "deals")["close_competing_deals"]:
        for other in competing:
            other.status = DealStatus.LOST
            other.holds_reservation = False
            other.closed_at = utcnow()
            other.lost_reason = f"Bien conclu avec un autre client ({deal.reference})"
            _log_activity(db, other, user_id, other.lost_reason)
            _notify_change(db, other, user_id, f"Transaction {other.reference} perdue : bien conclu ailleurs")
    db.flush()
    new_status = PropertyStatus.SOLD if deal.transaction_type == TransactionType.SALE else PropertyStatus.RENTED
    change_status(db, prop, new_status, user_id=user_id, ip=ip, reason=f"Transaction {deal.reference} conclue")
    if deal.request_id:
        from app.services import matching

        matching.refresh_for_request(db, db.get(CustomerRequest, deal.request_id))
    _log_activity(db, deal, user_id, f"Transaction {deal.reference} conclue au prix de {deal.agreed_price} {deal.currency}.")
    audit.log(db, user_id=user_id, action="win", entity_type="deal", entity_id=deal.id, label=deal.reference,
              changes={"agreed_price": str(deal.agreed_price), "commission": str(deal.commission_amount)}, ip=ip)
    _notify_change(db, deal, user_id, f"Transaction {deal.reference} conclue")
    return deal


def close_unsuccessful(db: Session, deal: Deal, *, user_id, new_status: DealStatus, reason: str, ip=None) -> Deal:
    if deal.status not in ACTIVE_DEAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette transaction est déjà clôturée.")
    prop = lock_property(db, deal.property_id)
    deal.status = new_status
    deal.holds_reservation = False
    deal.lost_reason = reason
    deal.closed_at = utcnow()
    db.flush()
    remaining = _other_active(db, deal)
    if prop.status in (PropertyStatus.RESERVED, PropertyStatus.UNDER_NEGOTIATION):
        if any(d.holds_reservation for d in remaining):
            target = PropertyStatus.RESERVED
        elif remaining:
            target = PropertyStatus.UNDER_NEGOTIATION
        else:
            # Back on the market: this re-runs matching and notifies waiting customers' agents.
            target = PropertyStatus.AVAILABLE
        change_status(db, prop, target, user_id=user_id, ip=ip, reason=f"Transaction {deal.reference} {DEAL_STATUS_LABELS[new_status.value].lower()}")
    _log_activity(db, deal, user_id, f"Transaction {deal.reference} {DEAL_STATUS_LABELS[new_status.value].lower()} : {reason}")
    audit.log(db, user_id=user_id, action=new_status.value, entity_type="deal", entity_id=deal.id, label=deal.reference,
              changes={"reason": reason}, ip=ip)
    _notify_change(db, deal, user_id, f"Transaction {deal.reference} {DEAL_STATUS_LABELS[new_status.value].lower()}")
    return deal
