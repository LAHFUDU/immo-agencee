import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, extract, func, select
from sqlalchemy.orm import Session

from app.api.helpers import request_scope, visit_scope
from app.api.properties import day_start
from app.core.db import get_db, utcnow
from app.core.deps import Principal, require
from app.models import CustomerRequest, Deal, Match, Property, Task, User, Visit
from app.models.enums import (
    OPEN_REQUEST_STATUSES,
    DealStatus,
    PropertyStatus,
    RequestStatus,
    TaskStatus,
    VisitStatus,
)
from app.services import audit, matching
from app.services.exports import export_response

router = APIRouter(tags=["reports"])


def _month(col):
    return func.to_char(func.date_trunc("month", col), "YYYY-MM")


def _range(date_from: date | None, date_to: date | None) -> tuple[datetime, datetime]:
    end = day_start(date_to) + timedelta(days=1) if date_to else utcnow()
    start = day_start(date_from) if date_from else datetime(end.year - 1, end.month, 1, tzinfo=timezone.utc)
    if start >= end:
        raise HTTPException(422, "Période invalide.")
    return start, end


def agent_performance(db: Session, start: datetime | None = None, end: datetime | None = None, with_commission: bool = True) -> list[dict]:
    users = db.scalars(select(User).where(User.is_agent.is_(True)).order_by(User.full_name)).all()
    req_conds = [] if start is None else [CustomerRequest.created_at >= start, CustomerRequest.created_at < end]
    deal_conds = [] if start is None else [Deal.closed_at >= start, Deal.closed_at < end]
    req_rows = dict(
        (r[0], r[1:])
        for r in db.execute(
            select(
                CustomerRequest.assigned_agent_id,
                func.count(),
                func.count().filter(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES)),
                func.count().filter(CustomerRequest.status == RequestStatus.CONVERTED),
                func.count().filter(CustomerRequest.status == RequestStatus.CLOSED_LOST),
                func.avg(extract("epoch", CustomerRequest.first_contacted_at - CustomerRequest.created_at) / 3600),
            )
            .where(CustomerRequest.assigned_agent_id.is_not(None), *req_conds)
            .group_by(CustomerRequest.assigned_agent_id)
        ).all()
    )
    deal_rows = dict(
        (r[0], r[1:])
        for r in db.execute(
            select(
                Deal.agent_id,
                func.count().filter(Deal.status == DealStatus.WON),
                func.coalesce(func.sum(Deal.agreed_price).filter(Deal.status == DealStatus.WON), 0),
                func.coalesce(func.sum(Deal.commission_amount).filter(Deal.status == DealStatus.WON), 0),
                func.count().filter(Deal.status == DealStatus.LOST),
            )
            .where(Deal.agent_id.is_not(None), *deal_conds)
            .group_by(Deal.agent_id)
        ).all()
    )
    visits = dict(
        db.execute(
            select(Visit.agent_id, func.count())
            .where(Visit.status == VisitStatus.DONE, *([] if start is None else [Visit.scheduled_at >= start, Visit.scheduled_at < end]))
            .group_by(Visit.agent_id)
        ).all()
    )
    out = []
    for u in users:
        total, open_, converted, lost, avg_contact = req_rows.get(u.id, (0, 0, 0, 0, None))
        won, volume, commission, deals_lost = deal_rows.get(u.id, (0, 0, 0, 0))
        row = {
            "agent_id": str(u.id), "agent": u.full_name, "active": u.is_active,
            "requests_assigned": total, "requests_open": open_, "requests_converted": converted, "requests_lost": lost,
            "conversion_rate": round(converted / total * 100, 1) if total else None,
            "avg_first_contact_hours": round(float(avg_contact), 1) if avg_contact is not None else None,
            "visits_done": visits.get(u.id, 0), "deals_won": won, "deals_lost": deals_lost,
        }
        if with_commission:
            row["sales_volume"] = str(volume)
            row["commission"] = str(commission)
        out.append(row)
    return out


@router.get("/dashboard")
def dashboard(p: Principal = Depends(require("dashboard.view")), db: Session = Depends(get_db)):
    now = utcnow()
    out: dict = {"scope": "all" if p.can("requests.view_all") else "mine"}

    if p.can("properties.view"):
        rows = dict(db.execute(select(Property.status, func.count()).group_by(Property.status)).all())
        out["properties"] = {
            "total": sum(v for k, v in rows.items() if k != PropertyStatus.ARCHIVED),
            "by_status": {k.value: v for k, v in rows.items()},
            "available": rows.get(PropertyStatus.AVAILABLE, 0),
            "sold_or_rented": rows.get(PropertyStatus.SOLD, 0) + rows.get(PropertyStatus.RENTED, 0),
            "under_negotiation": rows.get(PropertyStatus.UNDER_NEGOTIATION, 0) + rows.get(PropertyStatus.RESERVED, 0),
        }

    if p.can("requests.view"):
        scope = request_scope(p)
        base = select(func.count()).select_from(CustomerRequest)
        if scope is not None:
            base = base.where(scope)
        has_match = matching.has_active_match()
        out["requests"] = {
            "total": db.scalar(base.where(CustomerRequest.status != RequestStatus.ARCHIVED)) or 0,
            "open": db.scalar(base.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES))) or 0,
            "awaiting_contact": db.scalar(base.where(CustomerRequest.status.in_([RequestStatus.NEW, RequestStatus.TO_CONTACT]))) or 0,
            "unassigned": db.scalar(base.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), CustomerRequest.assigned_agent_id.is_(None))) or 0,
            "waiting_no_match": db.scalar(base.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), ~has_match)) or 0,
            "with_matches": db.scalar(base.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), has_match)) or 0,
            "overdue_follow_up": db.scalar(base.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), CustomerRequest.next_follow_up_at < now)) or 0,
            "converted": db.scalar(base.where(CustomerRequest.status == RequestStatus.CONVERTED)) or 0,
        }
        months = select(_month(CustomerRequest.created_at).label("m"), func.count()).where(
            CustomerRequest.created_at >= datetime(now.year - 1, now.month, 1, tzinfo=timezone.utc)
        )
        if scope is not None:
            months = months.where(scope)
        out["requests_per_month"] = [{"month": m, "count": c} for m, c in db.execute(months.group_by("m").order_by("m")).all()]

    if p.can("visits.view"):
        vscope = visit_scope(p)
        vq = select(func.count()).select_from(Visit).where(Visit.status == VisitStatus.SCHEDULED, Visit.scheduled_at >= now)
        if vscope is not None:
            vq = vq.where(vscope)
        out["visits_scheduled"] = db.scalar(vq) or 0
        upcoming = select(Visit).where(Visit.status == VisitStatus.SCHEDULED, Visit.scheduled_at >= now).order_by(Visit.scheduled_at).limit(5)
        if vscope is not None:
            upcoming = upcoming.where(vscope)
        out["upcoming_visits"] = [
            {"id": v.id, "scheduled_at": v.scheduled_at, "property": v.property.reference, "customer": v.customer.full_name,
             "agent": v.agent.full_name if v.agent else None}
            for v in db.scalars(upcoming).unique().all()
        ]

    if p.can("deals.view"):
        dq = select(func.count()).select_from(Deal)
        if not p.can("deals.view_all"):
            dq = dq.where(Deal.agent_id == p.id)
        out["deals"] = {
            "won": db.scalar(dq.where(Deal.status == DealStatus.WON)) or 0,
            "active": db.scalar(dq.where(Deal.status.in_([DealStatus.NEGOTIATION, DealStatus.RESERVED]))) or 0,
        }
        if p.can("commissions.view"):
            year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
            row = db.execute(
                select(func.coalesce(func.sum(Deal.agreed_price), 0), func.coalesce(func.sum(Deal.commission_amount), 0))
                .where(Deal.status == DealStatus.WON, Deal.closed_at >= year_start)
            ).one()
            out["revenue"] = {"year": now.year, "volume": str(row[0]), "commission": str(row[1])}

    out["tasks"] = {
        "overdue": db.scalar(select(func.count()).select_from(Task).where(Task.assigned_to_id == p.id, Task.status == TaskStatus.OPEN, Task.due_at < now)) or 0,
        "today": db.scalar(select(func.count()).select_from(Task).where(
            Task.assigned_to_id == p.id, Task.status == TaskStatus.OPEN, Task.due_at >= now, Task.due_at < now + timedelta(days=1))) or 0,
    }
    if p.can("agents.view"):
        out["agents"] = agent_performance(db, with_commission=p.can("commissions.view"))
    return out


def _report_data(db: Session, p: Principal, start: datetime, end: datetime) -> dict:
    in_range_req = and_(CustomerRequest.created_at >= start, CustomerRequest.created_at < end)
    data: dict = {"period": {"from": start.date().isoformat(), "to": (end - timedelta(seconds=1)).date().isoformat()}}

    data["requests_per_month"] = [
        {"month": m, "count": c}
        for m, c in db.execute(select(_month(CustomerRequest.created_at).label("m"), func.count()).where(in_range_req).group_by("m").order_by("m")).all()
    ]
    data["inventory_available"] = [
        {"city": city, "property_type": t, "count": c}
        for city, t, c in db.execute(
            select(Property.city, Property.property_type, func.count())
            .where(Property.status == PropertyStatus.AVAILABLE)
            .group_by(Property.city, Property.property_type)
            .order_by(Property.city, Property.property_type)
        ).all()
    ]
    data["closed_per_month"] = [
        {"month": m, "sold": s, "rented": r}
        for m, s, r in db.execute(
            select(
                _month(Deal.closed_at).label("m"),
                func.count().filter(Deal.transaction_type == "sale"),
                func.count().filter(Deal.transaction_type == "rent"),
            )
            .where(Deal.status == DealStatus.WON, Deal.closed_at >= start, Deal.closed_at < end)
            .group_by("m").order_by("m")
        ).all()
    ]
    waiting_q = select(CustomerRequest).where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), ~matching.has_active_match())
    waiting = db.scalars(waiting_q.order_by(CustomerRequest.created_at).limit(50)).unique().all()
    data["waiting"] = {
        "count": db.scalar(select(func.count()).select_from(waiting_q.subquery())) or 0,
        "by_city": [
            {"city": c, "property_type": t, "count": n}
            for c, t, n in db.execute(
                select(CustomerRequest.city, CustomerRequest.property_type, func.count())
                .where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), ~matching.has_active_match())
                .group_by(CustomerRequest.city, CustomerRequest.property_type)
                .order_by(func.count().desc())
            ).all()
        ],
        "oldest": [
            {"id": r.id, "reference": r.reference, "customer": r.customer.full_name, "city": r.city, "neighborhood": r.neighborhood,
             "property_type": r.property_type, "budget_max": str(r.budget_max) if r.budget_max is not None else None,
             "created_at": r.created_at, "agent": r.assigned_agent.full_name if r.assigned_agent else None}
            for r in waiting[:15]
        ],
    }
    avg_contact = db.scalar(
        select(func.avg(extract("epoch", CustomerRequest.first_contacted_at - CustomerRequest.created_at) / 3600))
        .where(in_range_req, CustomerRequest.first_contacted_at.is_not(None))
    )
    data["avg_first_contact_hours"] = round(float(avg_contact), 1) if avg_contact is not None else None
    won_in_range = and_(Deal.status == DealStatus.WON, Deal.closed_at >= start, Deal.closed_at < end)
    avg_deal = db.scalar(select(func.avg(extract("epoch", Deal.closed_at - Deal.created_at) / 86400)).where(won_in_range))
    data["avg_deal_close_days"] = round(float(avg_deal), 1) if avg_deal is not None else None
    avg_req = db.scalar(
        select(func.avg(extract("epoch", Deal.closed_at - CustomerRequest.created_at) / 86400))
        .join(CustomerRequest, CustomerRequest.id == Deal.request_id)
        .where(won_in_range)
    )
    data["avg_request_to_close_days"] = round(float(avg_req), 1) if avg_req is not None else None
    total, converted = db.execute(
        select(func.count(), func.count().filter(CustomerRequest.status == RequestStatus.CONVERTED)).where(in_range_req)
    ).one()
    data["conversion"] = {"requests": total, "converted": converted, "rate": round(converted / total * 100, 1) if total else None}
    data["agents"] = agent_performance(db, start, end, with_commission=p.can("commissions.view"))
    if p.can("commissions.view"):
        data["revenue_per_month"] = [
            {"month": m, "volume": str(v), "commission": str(c)}
            for m, v, c in db.execute(
                select(_month(Deal.closed_at).label("m"), func.coalesce(func.sum(Deal.agreed_price), 0), func.coalesce(func.sum(Deal.commission_amount), 0))
                .where(won_in_range).group_by("m").order_by("m")
            ).all()
        ]
    data["lost_reasons"] = {
        "requests": [
            {"reason": r or "Non précisé", "count": c}
            for r, c in db.execute(
                select(CustomerRequest.close_reason, func.count())
                .where(CustomerRequest.status == RequestStatus.CLOSED_LOST, CustomerRequest.closed_at >= start, CustomerRequest.closed_at < end)
                .group_by(CustomerRequest.close_reason).order_by(func.count().desc())
            ).all()
        ],
        "deals": [
            {"reason": r or "Non précisé", "count": c}
            for r, c in db.execute(
                select(Deal.lost_reason, func.count())
                .where(Deal.status.in_([DealStatus.LOST, DealStatus.CANCELLED]), Deal.closed_at >= start, Deal.closed_at < end)
                .group_by(Deal.lost_reason).order_by(func.count().desc())
            ).all()
        ],
        "rejected_matches": [
            {"reason": r or "Non précisé", "count": c}
            for r, c in db.execute(
                select(Match.rejection_reason, func.count())
                .where(Match.status == "rejected", Match.updated_at >= start, Match.updated_at < end)
                .group_by(Match.rejection_reason).order_by(func.count().desc()).limit(15)
            ).all()
        ],
    }
    return data


@router.get("/reports")
def reports(date_from: date | None = None, date_to: date | None = None, p: Principal = Depends(require("reports.view")), db: Session = Depends(get_db)):
    start, end = _range(date_from, date_to)
    return _report_data(db, p, start, end)


EXPORTS = {
    "requests_per_month": (["Mois", "Demandes"], lambda d: [[r["month"], r["count"]] for r in d["requests_per_month"]]),
    "inventory_available": (["Ville", "Type", "Biens disponibles"], lambda d: [[r["city"], r["property_type"], r["count"]] for r in d["inventory_available"]]),
    "closed_per_month": (["Mois", "Ventes", "Locations"], lambda d: [[r["month"], r["sold"], r["rented"]] for r in d["closed_per_month"]]),
    "waiting": (["Ville", "Type", "Demandes en attente"], lambda d: [[r["city"], r["property_type"], r["count"]] for r in d["waiting"]["by_city"]]),
    "agents": (
        ["Agent", "Demandes assignées", "Ouvertes", "Converties", "Perdues", "Taux conversion %", "1er contact (h)", "Visites", "Transactions conclues", "Volume", "Commission"],
        lambda d: [[a["agent"], a["requests_assigned"], a["requests_open"], a["requests_converted"], a["requests_lost"], a["conversion_rate"],
                    a["avg_first_contact_hours"], a["visits_done"], a["deals_won"], a.get("sales_volume", ""), a.get("commission", "")] for a in d["agents"]],
    ),
    "lost_reasons": (["Origine", "Motif", "Nombre"], lambda d: [["Demande", r["reason"], r["count"]] for r in d["lost_reasons"]["requests"]]
                     + [["Transaction", r["reason"], r["count"]] for r in d["lost_reasons"]["deals"]]),
}


@router.get("/reports/export")
def export_report(
    report: Literal["requests_per_month", "inventory_available", "closed_per_month", "waiting", "agents", "lost_reasons"],
    fmt: Literal["csv", "xlsx"] = "csv",
    date_from: date | None = None,
    date_to: date | None = None,
    p: Principal = Depends(require("reports.view", "reports.export")),
    db: Session = Depends(get_db),
):
    start, end = _range(date_from, date_to)
    d = _report_data(db, p, start, end)
    headers, fn = EXPORTS[report]
    audit.log(db, user_id=p.id, action="export", entity_type="report", label=report)
    db.commit()
    return export_response(f"rapport_{report}", fmt, headers, fn(d))


@router.get("/agents")
def agents(date_from: date | None = None, date_to: date | None = None, p: Principal = Depends(require("agents.view")), db: Session = Depends(get_db)):
    start, end = (None, None) if not (date_from or date_to) else _range(date_from, date_to)
    rows = agent_performance(db, start, end, with_commission=p.can("commissions.view"))
    workload = dict(
        db.execute(
            select(CustomerRequest.assigned_agent_id, func.count())
            .where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), CustomerRequest.next_follow_up_at < utcnow())
            .group_by(CustomerRequest.assigned_agent_id)
        ).all()
    )
    for r in rows:
        r["overdue_follow_ups"] = workload.get(uuid.UUID(r["agent_id"]), 0)
    return rows

