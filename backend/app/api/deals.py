from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.helpers import (
    Pagination,
    deal_out,
    deal_scope,
    ensure_user,
    get_customer_scoped,
    get_request_scoped,
    paginate,
    parse_uuid,
)
from app.api.properties import csv_list, day_start
from app.core.db import get_db
from app.core.deps import Principal, client_ip, require
from app.models import Activity, Customer, Deal, Offer, Property
from app.models.enums import ActivityType, DealStatus, OfferStatus
from app.schemas.common import Page
from app.schemas.crm import ActivityOut
from app.schemas.deals import (
    CloseIn,
    CommissionOverride,
    DealCreate,
    DealOut,
    DealUpdate,
    OfferIn,
    OfferStatusIn,
    ReserveIn,
    WinIn,
)
from app.services import audit
from app.services import deals as svc
from app.services.exports import export_response
from app.services.references import next_reference
from app.services.text import like_escape

router = APIRouter(tags=["deals"])


def _query(p: Principal, q, status, agent_id, transaction_type, date_from, date_to):
    stmt = select(Deal).join(Customer, Customer.id == Deal.customer_id).join(Property, Property.id == Deal.property_id)
    scope = deal_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    if q and q.strip():
        term = f"%{like_escape(q.strip())}%"
        stmt = stmt.where(or_(Deal.reference.ilike(term), Customer.full_name.ilike(term), Property.reference.ilike(term), Property.title.ilike(term)))
    if sts := csv_list(status):
        stmt = stmt.where(Deal.status.in_([DealStatus(s) for s in sts]))
    if agent_id == "me":
        stmt = stmt.where(Deal.agent_id == p.id)
    elif agent_id:
        stmt = stmt.where(Deal.agent_id == parse_uuid(agent_id))
    if transaction_type:
        stmt = stmt.where(Deal.transaction_type == transaction_type)
    if date_from:
        stmt = stmt.where(Deal.created_at >= day_start(date_from))
    if date_to:
        stmt = stmt.where(Deal.created_at < day_start(date_to) + timedelta(days=1))
    return stmt.order_by(Deal.created_at.desc(), Deal.id)


@router.get("/deals", response_model=Page[DealOut])
def list_deals(
    q: str | None = None, status: str | None = None, agent_id: str | None = None, transaction_type: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    pg: Pagination = Depends(), p: Principal = Depends(require("deals.view")), db: Session = Depends(get_db),
):
    items, total = paginate(db, _query(p, q, status, agent_id, transaction_type, date_from, date_to), pg)
    return Page(items=[deal_out(d, p) for d in items], total=total, page=pg.page, page_size=pg.page_size)


@router.get("/deals/export")
def export_deals(
    fmt: Literal["csv", "xlsx"] = "csv", q: str | None = None, status: str | None = None, agent_id: str | None = None,
    transaction_type: str | None = None, date_from: date | None = None, date_to: date | None = None,
    p: Principal = Depends(require("deals.view", "reports.export")), db: Session = Depends(get_db),
):
    rows = db.scalars(_query(p, q, status, agent_id, transaction_type, date_from, date_to)).unique().all()
    show_comm = p.can("commissions.view")
    headers = ["Référence", "Client", "Bien", "Transaction", "Statut", "Prix demandé", "Prix convenu", "Devise", "Agent",
               "Clôture prévue", "Clôture réelle", "Motif perte"] + (["Taux %", "Commission"] if show_comm else [])
    data = []
    for d in rows:
        line = [d.reference, d.customer.full_name, d.property.reference, d.transaction_type, svc.DEAL_STATUS_LABELS[d.status.value],
                d.asking_price, d.agreed_price, d.currency, d.agent.full_name if d.agent else "", d.expected_closing_date,
                d.actual_closing_date, d.lost_reason]
        if show_comm:
            line += [d.commission_rate, d.commission_amount]
        data.append(line)
    audit.log(db, user_id=p.id, action="export", entity_type="deal", changes={"rows": len(data)})
    db.commit()
    return export_response("transactions", fmt, headers, data)


def _get(db: Session, p: Principal, deal_id: str) -> Deal:
    stmt = select(Deal).where(Deal.id == parse_uuid(deal_id))
    scope = deal_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    d = db.scalars(stmt).unique().first()
    if d is None:
        raise HTTPException(404, "Transaction introuvable.")
    return d


@router.post("/deals", response_model=DealOut, status_code=201)
def create_deal(data: DealCreate, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    prop = db.get(Property, data.property_id)
    if prop is None:
        raise HTTPException(422, "Bien inconnu.")
    req = None
    if data.request_id:
        req = get_request_scoped(db, p, data.request_id)
        customer_id = req.customer_id
    elif data.customer_id:
        customer_id = get_customer_scoped(db, p, data.customer_id).id
    else:
        raise HTTPException(422, "Indiquez la demande ou le client.")
    agent_id = data.agent_id or (req.assigned_agent_id if req and req.assigned_agent_id else p.id)
    if agent_id != p.id and not p.can("requests.assign") and not (req and req.assigned_agent_id == agent_id):
        raise HTTPException(403, "Vous ne pouvez pas attribuer cette transaction à un autre agent.")
    ensure_user(db, agent_id)
    deal = Deal(
        reference=next_reference(db, "TRX"), customer_id=customer_id, request_id=req.id if req else None,
        property_id=prop.id, agent_id=agent_id, transaction_type=prop.transaction_type,
        expected_closing_date=data.expected_closing_date, notes=data.notes, created_by_id=p.id,
    )
    svc.open_deal(db, deal, user_id=p.id, ip=client_ip(request))
    db.commit()
    db.refresh(deal)
    return deal_out(deal, p)


@router.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(deal_id: str, p: Principal = Depends(require("deals.view")), db: Session = Depends(get_db)):
    return deal_out(_get(db, p, deal_id), p)


@router.get("/deals/{deal_id}/activities")
def deal_activities(deal_id: str, p: Principal = Depends(require("deals.view")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    rows = db.scalars(select(Activity).where(Activity.deal_id == d.id).order_by(Activity.occurred_at.desc())).unique().all()
    return [ActivityOut.model_validate(a) for a in rows]


@router.patch("/deals/{deal_id}", response_model=DealOut)
def update_deal(deal_id: str, data: DealUpdate, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    if d.status not in (DealStatus.NEGOTIATION, DealStatus.RESERVED):
        raise HTTPException(409, "Une transaction clôturée ne peut plus être modifiée (historique préservé).")
    fields = data.model_dump(exclude_unset=True)
    if "agent_id" in fields and fields["agent_id"] != d.agent_id:
        if not p.can("requests.assign"):
            raise HTTPException(403, "Vous ne pouvez pas réassigner cette transaction.")
        ensure_user(db, fields["agent_id"])
    before = audit.snapshot(d, list(fields))
    for k, v in fields.items():
        setattr(d, k, v)
    if "agreed_price" in fields:
        svc.recompute_commission(db, d, d.property)
    audit.log(db, user_id=p.id, action="update", entity_type="deal", entity_id=d.id, label=d.reference,
              changes=audit.diff(before, audit.snapshot(d, list(fields))), ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.post("/deals/{deal_id}/commission", response_model=DealOut)
def override_commission(deal_id: str, data: CommissionOverride, request: Request, p: Principal = Depends(require("commissions.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    before = {"rate": str(d.commission_rate), "amount": str(d.commission_amount)}
    if data.reset:
        d.commission_overridden = False
        svc.recompute_commission(db, d, d.property)
    else:
        d.commission_overridden = True
        d.commission_rate = data.commission_rate
        price = d.agreed_price if d.agreed_price is not None else d.asking_price
        if data.commission_amount is not None:
            d.commission_amount = data.commission_amount
        elif data.commission_rate is not None and price is not None:
            d.commission_amount = (Decimal(price) * data.commission_rate / 100).quantize(Decimal("0.01"))
    audit.log(db, user_id=p.id, action="commission_override", entity_type="deal", entity_id=d.id, label=d.reference,
              changes={"before": before, "after": {"rate": str(d.commission_rate), "amount": str(d.commission_amount)}}, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.post("/deals/{deal_id}/reserve", response_model=DealOut)
def reserve_deal(deal_id: str, data: ReserveIn, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    svc.reserve(db, d, user_id=p.id, can_override=p.can("deals.override_reservation"), override=data.override, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.post("/deals/{deal_id}/win", response_model=DealOut)
def win_deal(deal_id: str, data: WinIn, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    svc.win(db, d, user_id=p.id, agreed_price=data.agreed_price, closing_date=data.closing_date, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.post("/deals/{deal_id}/lose", response_model=DealOut)
def lose_deal(deal_id: str, data: CloseIn, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    svc.close_unsuccessful(db, d, user_id=p.id, new_status=DealStatus.LOST, reason=data.reason, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.post("/deals/{deal_id}/cancel", response_model=DealOut)
def cancel_deal(deal_id: str, data: CloseIn, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    svc.close_unsuccessful(db, d, user_id=p.id, new_status=DealStatus.CANCELLED, reason=data.reason, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.post("/deals/{deal_id}/offers", response_model=DealOut, status_code=201)
def add_offer(deal_id: str, data: OfferIn, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    if d.status not in (DealStatus.NEGOTIATION, DealStatus.RESERVED):
        raise HTTPException(409, "Transaction clôturée.")
    o = Offer(deal_id=d.id, amount=data.amount, party=data.party, notes=data.notes, created_by_id=p.id)
    if data.offered_at:
        o.offered_at = data.offered_at
    db.add(o)
    who = "client" if data.party.value == "customer" else "propriétaire"
    db.add(Activity(type=ActivityType.OFFER, summary=f"Offre du {who} : {data.amount} {d.currency}" + (f" — {data.notes}" if data.notes else ""),
                    customer_id=d.customer_id, request_id=d.request_id, property_id=d.property_id, deal_id=d.id, created_by_id=p.id))
    audit.log(db, user_id=p.id, action="offer", entity_type="deal", entity_id=d.id, label=d.reference,
              changes={"amount": str(data.amount), "party": data.party.value}, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)


@router.patch("/deals/{deal_id}/offers/{offer_id}", response_model=DealOut)
def update_offer(deal_id: str, offer_id: str, data: OfferStatusIn, request: Request, p: Principal = Depends(require("deals.manage")), db: Session = Depends(get_db)):
    d = _get(db, p, deal_id)
    o = db.get(Offer, parse_uuid(offer_id))
    if o is None or o.deal_id != d.id:
        raise HTTPException(404, "Offre introuvable.")
    if d.status not in (DealStatus.NEGOTIATION, DealStatus.RESERVED):
        raise HTTPException(409, "Transaction clôturée.")
    o.status = data.status
    if data.status == OfferStatus.ACCEPTED:
        d.agreed_price = o.amount
        svc.recompute_commission(db, d, d.property)
    audit.log(db, user_id=p.id, action="offer_status", entity_type="deal", entity_id=d.id, label=d.reference,
              changes={"offer": str(o.id), "status": data.status.value}, ip=client_ip(request))
    db.commit()
    db.refresh(d)
    return deal_out(d, p)

