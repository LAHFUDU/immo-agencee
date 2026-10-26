from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.helpers import (
    Pagination,
    customer_out,
    customer_scope,
    deal_out,
    deal_scope,
    ensure_user,
    get_customer_scoped,
    get_request_scoped,
    match_out,
    match_summaries,
    paginate,
    parse_uuid,
    request_out,
    request_scope,
    visit_out,
    visit_scope,
)
from app.api.properties import csv_list, day_start
from app.api.requests import _duplicates, apply_status_change
from app.core.db import get_db, utcnow
from app.core.deps import Principal, client_ip, get_active_principal, require
from app.models import Activity, Customer, CustomerRequest, Deal, Match, Property, Task, Visit
from app.models.enums import (
    ActivityType,
    MatchCategory,
    MatchStatus,
    PropertyStatus,
    RequestStatus,
    TaskStatus,
    VisitStatus,
)
from app.schemas.common import Page
from app.schemas.crm import (
    ActivityIn,
    ActivityOut,
    CustomerIn,
    CustomerOut,
    CustomerUpdate,
    DuplicateCandidate,
    MatchAction,
    MatchOut,
    TaskIn,
    TaskOut,
    TaskUpdate,
    VisitIn,
    VisitOut,
    VisitUpdate,
)
from app.services import audit, matching
from app.services.exports import export_response
from app.services.notifications import notify
from app.services.references import next_reference
from app.services.text import like_escape, normalize_key, phone_key

router = APIRouter(tags=["crm"])

CUSTOMER_FIELDS = ["full_name", "phone", "email", "preferred_contact", "source", "preferences", "internal_notes", "assigned_agent_id"]


# ------------------------------------------------------------------ customers


def _customer_query(p: Principal, q: str | None, source: str | None, agent: str | None, archived: bool):
    stmt = select(Customer).where(Customer.is_archived.is_(archived))
    scope = customer_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    if q and q.strip():
        term = f"%{like_escape(q.strip())}%"
        conds = [Customer.full_name.ilike(term), Customer.email.ilike(term), Customer.reference.ilike(term)]
        pk = phone_key(q)
        if pk and len(pk) >= 4:
            conds.append(Customer.phone_key.like(f"%{pk}%"))
        stmt = stmt.where(or_(*conds))
    if source:
        stmt = stmt.where(Customer.source == source)
    if agent == "me":
        stmt = stmt.where(Customer.assigned_agent_id == p.id)
    elif agent:
        stmt = stmt.where(Customer.assigned_agent_id == parse_uuid(agent))
    return stmt.order_by(Customer.created_at.desc(), Customer.id)


@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(
    q: str | None = None, source: str | None = None, assigned_agent_id: str | None = None, archived: bool = False,
    pg: Pagination = Depends(), p: Principal = Depends(require("customers.view")), db: Session = Depends(get_db),
):
    items, total = paginate(db, _customer_query(p, q, source, assigned_agent_id, archived), pg)
    return Page(items=[customer_out(c) for c in items], total=total, page=pg.page, page_size=pg.page_size)


@router.get("/customers/export")
def export_customers(
    fmt: Literal["csv", "xlsx"] = "csv", q: str | None = None, source: str | None = None, assigned_agent_id: str | None = None,
    archived: bool = False, p: Principal = Depends(require("customers.view", "customers.export")), db: Session = Depends(get_db),
):
    rows = db.scalars(_customer_query(p, q, source, assigned_agent_id, archived)).unique().all()
    data = [[c.reference, c.full_name, c.phone, c.email, c.preferred_contact, c.source,
             c.assigned_agent.full_name if c.assigned_agent else "", c.created_at] for c in rows]
    audit.log(db, user_id=p.id, action="export", entity_type="customer", changes={"rows": len(data)})
    db.commit()
    return export_response("clients", fmt, ["Référence", "Nom", "Téléphone", "E-mail", "Contact préféré", "Source", "Agent", "Créé le"], data)


@router.get("/customers/duplicates", response_model=list[DuplicateCandidate])
def find_duplicates(phone: str | None = None, email: str | None = None, exclude_id: str | None = None,
                    p: Principal = Depends(require("customers.view")), db: Session = Depends(get_db)):
    return _duplicates(db, p, phone, email, parse_uuid(exclude_id) if exclude_id else None)


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(data: CustomerIn, request: Request, allow_duplicate: bool = False,
                    p: Principal = Depends(require("customers.create")), db: Session = Depends(get_db)):
    dups = _duplicates(db, p, data.phone, data.email)
    if dups and not allow_duplicate:
        raise HTTPException(409, {"message": "Un client existe déjà avec ces coordonnées.", "duplicates": [d.model_dump(mode="json") for d in dups]})
    if data.assigned_agent_id:
        if data.assigned_agent_id != p.id and not p.can("requests.assign"):
            raise HTTPException(403, "Vous n'êtes pas autorisé à assigner des clients.")
        ensure_user(db, data.assigned_agent_id)
    c = Customer(reference=next_reference(db, "CLI"), **data.model_dump(), phone_key=phone_key(data.phone), created_by_id=p.id)
    if c.assigned_agent_id is None and p.user.is_agent and not p.can("customers.view_all"):
        c.assigned_agent_id = p.id
    db.add(c)
    db.flush()
    audit.log(db, user_id=p.id, action="create", entity_type="customer", entity_id=c.id, label=c.reference, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return customer_out(c)


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str, p: Principal = Depends(require("customers.view")), db: Session = Depends(get_db)):
    c = get_customer_scoped(db, p, parse_uuid(customer_id))
    req_stmt = select(CustomerRequest).where(CustomerRequest.customer_id == c.id).order_by(CustomerRequest.created_at.desc())
    rscope = request_scope(p)
    if rscope is not None:
        req_stmt = req_stmt.where(rscope)
    reqs = db.scalars(req_stmt).unique().all()
    sums = match_summaries(db, [r.id for r in reqs])
    deals = []
    if p.can("deals.view"):
        dstmt = select(Deal).where(Deal.customer_id == c.id).order_by(Deal.created_at.desc())
        dscope = deal_scope(p)
        if dscope is not None:
            dstmt = dstmt.where(dscope)
        deals = [deal_out(d, p) for d in db.scalars(dstmt).unique().all()]
    return {
        "customer": customer_out(c),
        "requests": [request_out(r, sums.get(r.id)) for r in reqs],
        "deals": deals,
    }


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, data: CustomerUpdate, request: Request, p: Principal = Depends(require("customers.edit")), db: Session = Depends(get_db)):
    c = get_customer_scoped(db, p, parse_uuid(customer_id))
    fields = data.model_dump(exclude_unset=True)
    if "full_name" in fields and not fields["full_name"]:
        raise HTTPException(422, "Le nom est obligatoire.")
    if "assigned_agent_id" in fields and fields["assigned_agent_id"] != c.assigned_agent_id:
        if not p.can("requests.assign"):
            raise HTTPException(403, "Vous n'êtes pas autorisé à réassigner des clients.")
        if fields["assigned_agent_id"]:
            ensure_user(db, fields["assigned_agent_id"])
    before = audit.snapshot(c, CUSTOMER_FIELDS)
    for k, v in fields.items():
        setattr(c, k, v)
    if not c.phone and not c.email:
        raise HTTPException(422, "Un téléphone ou un e-mail est requis.")
    c.phone_key = phone_key(c.phone)
    changes = audit.diff(before, audit.snapshot(c, CUSTOMER_FIELDS))
    if changes:
        audit.log(db, user_id=p.id, action="update", entity_type="customer", entity_id=c.id, label=c.reference, changes=changes, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return customer_out(c)


@router.post("/customers/{customer_id}/archive", response_model=CustomerOut)
def archive_customer(customer_id: str, request: Request, archived: bool = True, p: Principal = Depends(require("customers.archive")), db: Session = Depends(get_db)):
    c = get_customer_scoped(db, p, parse_uuid(customer_id))
    c.is_archived = archived
    audit.log(db, user_id=p.id, action="archive" if archived else "unarchive", entity_type="customer", entity_id=c.id, label=c.reference, ip=client_ip(request))
    db.commit()
    db.refresh(c)
    return customer_out(c)


@router.get("/customers/{customer_id}/activities", response_model=list[ActivityOut])
def customer_activities(customer_id: str, p: Principal = Depends(require("customers.view")), db: Session = Depends(get_db)):
    c = get_customer_scoped(db, p, parse_uuid(customer_id))
    return db.scalars(select(Activity).where(Activity.customer_id == c.id).order_by(Activity.occurred_at.desc()).limit(300)).unique().all()


@router.post("/customers/{customer_id}/activities", response_model=ActivityOut, status_code=201)
def add_customer_activity(customer_id: str, data: ActivityIn, p: Principal = Depends(require("customers.edit")), db: Session = Depends(get_db)):
    c = get_customer_scoped(db, p, parse_uuid(customer_id))
    if data.type == ActivityType.STATUS_CHANGE:
        raise HTTPException(422, "Type d'activité réservé au système.")
    a = Activity(type=data.type, summary=data.summary, customer_id=c.id, property_id=data.property_id, created_by_id=p.id)
    if data.occurred_at:
        a.occurred_at = data.occurred_at
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ------------------------------------------------------------------ matches


@router.get("/matches", response_model=Page[MatchOut])
def list_matches(
    category: str | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    status: str | None = None,
    assigned_agent_id: str | None = None,
    city: str | None = None,
    property_id: str | None = None,
    request_id: str | None = None,
    include_inactive: bool = False,
    pg: Pagination = Depends(),
    p: Principal = Depends(require("matches.view", "requests.view")),
    db: Session = Depends(get_db),
):
    stmt = select(Match).join(CustomerRequest, CustomerRequest.id == Match.request_id).join(Property, Property.id == Match.property_id)
    scope = request_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    if not include_inactive:
        stmt = stmt.where(Match.is_active.is_(True))
    if cats := csv_list(category):
        stmt = stmt.where(Match.category.in_([MatchCategory(c) for c in cats]))
    if min_score is not None:
        stmt = stmt.where(Match.score >= min_score)
    if sts := csv_list(status):
        stmt = stmt.where(Match.status.in_([MatchStatus(s) for s in sts]))
    if assigned_agent_id == "me":
        stmt = stmt.where(CustomerRequest.assigned_agent_id == p.id)
    elif assigned_agent_id == "none":
        stmt = stmt.where(CustomerRequest.assigned_agent_id.is_(None))
    elif assigned_agent_id:
        stmt = stmt.where(CustomerRequest.assigned_agent_id == parse_uuid(assigned_agent_id))
    if city:
        stmt = stmt.where(Property.city_key == normalize_key(city))
    if property_id:
        stmt = stmt.where(Match.property_id == parse_uuid(property_id))
    if request_id:
        stmt = stmt.where(Match.request_id == parse_uuid(request_id))
    stmt = stmt.order_by(Match.computed_at.desc(), Match.score.desc())
    items, total = paginate(db, stmt, pg)
    return Page(items=[match_out(m, req=m.request, prop=m.property) for m in items], total=total, page=pg.page, page_size=pg.page_size)


def _get_match(db: Session, p: Principal, match_id: str) -> Match:
    m = db.get(Match, parse_uuid(match_id))
    if m is None:
        raise HTTPException(404, "Correspondance introuvable.")
    get_request_scoped(db, p, m.request_id)  # row-level check through the request
    return m


@router.patch("/matches/{match_id}", response_model=MatchOut)
def update_match(match_id: str, data: MatchAction, request: Request, p: Principal = Depends(require("matches.manage")), db: Session = Depends(get_db)):
    m = _get_match(db, p, match_id)
    req, prop = m.request, m.property
    if data.status in (MatchStatus.PROPOSED, MatchStatus.INTERESTED, MatchStatus.VISIT_SCHEDULED) and not m.is_active:
        raise HTTPException(409, "Ce bien n'est plus disponible pour cette demande.")
    old = m.status
    m.status = data.status
    if data.customer_feedback is not None:
        m.customer_feedback = data.customer_feedback
    if data.status == MatchStatus.REJECTED:
        m.rejection_reason = data.rejection_reason
    if data.status == MatchStatus.PROPOSED and m.proposed_at is None:
        m.proposed_at = utcnow()
        if req.status in (RequestStatus.NEW, RequestStatus.TO_CONTACT, RequestStatus.CONTACTED):
            apply_status_change(db, req, RequestStatus.PROPOSED, p.id)
    labels = {"suggested": "suggéré", "proposed": "proposé au client", "interested": "intéresse le client",
              "visit_scheduled": "visite planifiée", "rejected": "rejeté"}
    summary = f"Bien {prop.reference} {labels[data.status.value]}"
    if data.rejection_reason and data.status == MatchStatus.REJECTED:
        summary += f" — motif : {data.rejection_reason}"
    if data.customer_feedback:
        summary += f" — retour client : {data.customer_feedback}"
    db.add(Activity(type=ActivityType.NOTE, summary=summary, customer_id=req.customer_id, request_id=req.id, property_id=prop.id, created_by_id=p.id))
    audit.log(db, user_id=p.id, action="match_update", entity_type="request", entity_id=req.id, label=req.reference,
              changes={"property": prop.reference, "status": {"old": old.value, "new": data.status.value}}, ip=client_ip(request))
    db.commit()
    db.refresh(m)
    return match_out(m, req=m.request, prop=m.property)


@router.post("/matches/{match_id}/renotify")
def renotify(match_id: str, p: Principal = Depends(require("matches.manage")), db: Session = Depends(get_db)):
    """Explicit re-notification requested by an agent (bypasses the de-duplication)."""
    m = _get_match(db, p, match_id)
    if not m.is_active:
        raise HTTPException(409, "Correspondance inactive.")
    matching.notify_match(db, m, m.request, m.property, force=True)
    db.commit()
    return {"detail": "Notification envoyée."}


# ------------------------------------------------------------------ tasks & reminders


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    status: str | None = "open",
    scope: Literal["mine", "all"] = "mine",
    request_id: str | None = None,
    customer_id: str | None = None,
    due_before: datetime | None = None,
    p: Principal = Depends(get_active_principal),
    db: Session = Depends(get_db),
):
    stmt = select(Task).order_by(Task.due_at)
    if scope == "all" and p.can("requests.view_all"):
        pass
    else:
        stmt = stmt.where(or_(Task.assigned_to_id == p.id, Task.created_by_id == p.id))
    if sts := csv_list(status):
        stmt = stmt.where(Task.status.in_([TaskStatus(s) for s in sts]))
    if request_id:
        get_request_scoped(db, p, parse_uuid(request_id))
        stmt = stmt.where(Task.request_id == parse_uuid(request_id))
    if customer_id:
        get_customer_scoped(db, p, parse_uuid(customer_id))
        stmt = stmt.where(Task.customer_id == parse_uuid(customer_id))
    if due_before:
        stmt = stmt.where(Task.due_at <= due_before)
    return db.scalars(stmt.limit(500)).unique().all()


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(data: TaskIn, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    assignee = data.assigned_to_id or p.id
    if assignee != p.id:
        if not p.can("requests.assign"):
            raise HTTPException(403, "Vous ne pouvez créer des tâches que pour vous-même.")
        ensure_user(db, assignee)
    customer_id = data.customer_id
    if data.request_id:
        req = get_request_scoped(db, p, data.request_id)
        customer_id = req.customer_id
    elif customer_id:
        get_customer_scoped(db, p, customer_id)
    t = Task(title=data.title, description=data.description, due_at=data.due_at, assigned_to_id=assignee,
             customer_id=customer_id, request_id=data.request_id, created_by_id=p.id)
    db.add(t)
    db.flush()
    if assignee != p.id:
        notify(db, [assignee], type="task_assigned", title=f"Nouvelle tâche : {t.title}", body=f"Échéance : {t.due_at:%d/%m/%Y %H:%M}",
               link="/app/visits?tab=tasks", entity_type="task", entity_id=t.id, dedupe_key=f"task:{t.id}")
    db.commit()
    db.refresh(t)
    return t


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: str, data: TaskUpdate, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    t = db.get(Task, parse_uuid(task_id))
    if t is None or (t.assigned_to_id != p.id and t.created_by_id != p.id and not p.can("requests.view_all")):
        raise HTTPException(404, "Tâche introuvable.")
    fields = data.model_dump(exclude_unset=True)
    if "assigned_to_id" in fields and fields["assigned_to_id"] and fields["assigned_to_id"] != t.assigned_to_id:
        if not p.can("requests.assign"):
            raise HTTPException(403, "Vous ne pouvez pas réassigner cette tâche.")
        ensure_user(db, fields["assigned_to_id"])
    for k, v in fields.items():
        if v is not None:
            setattr(t, k, v)
    if "due_at" in fields:
        t.reminded_at = None
    if t.status == TaskStatus.DONE and t.completed_at is None:
        t.completed_at = utcnow()
    elif t.status != TaskStatus.DONE:
        t.completed_at = None
    db.commit()
    db.refresh(t)
    return t


# ------------------------------------------------------------------ visits & appointments


@router.get("/visits", response_model=Page[VisitOut])
def list_visits(
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    agent_id: str | None = None,
    property_id: str | None = None,
    request_id: str | None = None,
    order: Literal["asc", "desc"] = "asc",
    pg: Pagination = Depends(),
    p: Principal = Depends(require("visits.view")),
    db: Session = Depends(get_db),
):
    stmt = select(Visit)
    scope = visit_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    if date_from:
        stmt = stmt.where(Visit.scheduled_at >= day_start(date_from))
    if date_to:
        stmt = stmt.where(Visit.scheduled_at < day_start(date_to) + timedelta(days=1))
    if sts := csv_list(status):
        stmt = stmt.where(Visit.status.in_([VisitStatus(s) for s in sts]))
    if agent_id == "me":
        stmt = stmt.where(Visit.agent_id == p.id)
    elif agent_id:
        stmt = stmt.where(Visit.agent_id == parse_uuid(agent_id))
    if property_id:
        stmt = stmt.where(Visit.property_id == parse_uuid(property_id))
    if request_id:
        stmt = stmt.where(Visit.request_id == parse_uuid(request_id))
    stmt = stmt.order_by(Visit.scheduled_at.asc() if order == "asc" else Visit.scheduled_at.desc())
    items, total = paginate(db, stmt, pg)
    return Page(items=[visit_out(v, p) for v in items], total=total, page=pg.page, page_size=pg.page_size)


@router.post("/visits", response_model=VisitOut, status_code=201)
def create_visit(data: VisitIn, request: Request, p: Principal = Depends(require("visits.manage")), db: Session = Depends(get_db)):
    prop = db.get(Property, data.property_id)
    if prop is None:
        raise HTTPException(422, "Bien inconnu.")
    if prop.status in (PropertyStatus.SOLD, PropertyStatus.RENTED, PropertyStatus.ARCHIVED, PropertyStatus.UNAVAILABLE):
        raise HTTPException(409, "Ce bien n'est pas disponible à la visite.")
    req = None
    if data.request_id:
        req = get_request_scoped(db, p, data.request_id)
        customer_id = req.customer_id
    elif data.customer_id:
        customer_id = get_customer_scoped(db, p, data.customer_id).id
    else:
        raise HTTPException(422, "Indiquez la demande ou le client concerné.")
    agent_id = data.agent_id or (req.assigned_agent_id if req and req.assigned_agent_id else p.id)
    if agent_id != p.id and not p.can("requests.assign") and not (req and req.assigned_agent_id == agent_id):
        raise HTTPException(403, "Vous ne pouvez pas planifier une visite pour un autre agent.")
    ensure_user(db, agent_id)
    # Avoid double-booking the same agent.
    end = data.scheduled_at + timedelta(minutes=data.duration_minutes)
    clash = db.scalar(
        select(Visit).where(
            Visit.agent_id == agent_id, Visit.status == VisitStatus.SCHEDULED,
            Visit.scheduled_at < end,
            Visit.scheduled_at + func.make_interval(0, 0, 0, 0, 0, Visit.duration_minutes) > data.scheduled_at,
        )
    )
    if clash:
        raise HTTPException(409, f"L'agent a déjà une visite à {clash.scheduled_at:%H:%M} sur ce créneau.")
    v = Visit(request_id=req.id if req else None, customer_id=customer_id, property_id=prop.id, match_id=data.match_id,
              agent_id=agent_id, scheduled_at=data.scheduled_at, duration_minutes=data.duration_minutes, notes=data.notes, created_by_id=p.id)
    db.add(v)
    db.flush()
    if req:
        m = db.scalar(select(Match).where(Match.request_id == req.id, Match.property_id == prop.id))
        if m and m.status != MatchStatus.REJECTED:
            m.status = MatchStatus.VISIT_SCHEDULED
            v.match_id = m.id
        if req.status in (RequestStatus.NEW, RequestStatus.TO_CONTACT, RequestStatus.CONTACTED, RequestStatus.PROPOSED):
            apply_status_change(db, req, RequestStatus.VISIT_SCHEDULED, p.id)
    db.add(Activity(type=ActivityType.VISIT, summary=f"Visite planifiée le {v.scheduled_at:%d/%m/%Y à %H:%M} — {prop.reference}",
                    customer_id=customer_id, request_id=v.request_id, property_id=prop.id, created_by_id=p.id))
    notify(db, [agent_id], type="visit_scheduled", title=f"Visite planifiée : {prop.reference}",
           body=f"{v.scheduled_at:%d/%m/%Y %H:%M}", link="/app/visits", entity_type="visit", entity_id=v.id,
           dedupe_key=f"visit_scheduled:{v.id}", exclude_user_id=p.id)
    audit.log(db, user_id=p.id, action="create", entity_type="visit", entity_id=v.id, label=prop.reference, ip=client_ip(request))
    db.commit()
    db.refresh(v)
    return visit_out(v, p)


@router.patch("/visits/{visit_id}", response_model=VisitOut)
def update_visit(visit_id: str, data: VisitUpdate, request: Request, p: Principal = Depends(require("visits.manage")), db: Session = Depends(get_db)):
    stmt = select(Visit).where(Visit.id == parse_uuid(visit_id))
    scope = visit_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    v = db.scalars(stmt).unique().first()
    if v is None:
        raise HTTPException(404, "Visite introuvable.")
    fields = data.model_dump(exclude_unset=True)
    if "agent_id" in fields and fields["agent_id"] != v.agent_id:
        if not p.can("requests.assign"):
            raise HTTPException(403, "Vous ne pouvez pas réassigner cette visite.")
        ensure_user(db, fields["agent_id"])
    old_status = v.status
    for k, val in fields.items():
        if val is not None:
            setattr(v, k, val)
    if "scheduled_at" in fields:
        v.reminder_sent_at = None
    if v.status != old_status:
        labels = {"scheduled": "planifiée", "done": "effectuée", "cancelled": "annulée", "no_show": "client absent"}
        summary = f"Visite {v.property.reference} : {labels[v.status.value]}"
        if v.customer_feedback:
            summary += f" — retour : {v.customer_feedback}"
        db.add(Activity(type=ActivityType.VISIT, summary=summary, customer_id=v.customer_id, request_id=v.request_id,
                        property_id=v.property_id, created_by_id=p.id))
    audit.log(db, user_id=p.id, action="update", entity_type="visit", entity_id=v.id, label=v.property.reference,
              changes={k: str(val) for k, val in fields.items()}, ip=client_ip(request))
    db.commit()
    db.refresh(v)
    return visit_out(v, p)

