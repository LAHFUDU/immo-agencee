from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.helpers import (
    Pagination,
    customer_scope,
    ensure_user,
    get_request_scoped,
    match_out,
    match_summaries,
    paginate,
    parse_uuid,
    request_out,
    request_scope,
    validate_category,
    validate_features,
)
from app.api.properties import csv_list, day_start
from app.core.db import get_db, utcnow
from app.core.deps import Principal, client_ip, require
from app.models import Activity, Customer, CustomerRequest, Match, Property
from app.models.enums import (
    CLOSED_REQUEST_STATUSES,
    OPEN_REQUEST_STATUSES,
    ActivityType,
    MatchCategory,
    Priority,
    RequestStatus,
)
from app.schemas.common import Page
from app.schemas.crm import (
    ActivityIn,
    ActivityOut,
    AssignIn,
    DuplicateCandidate,
    MatchOut,
    RequestCreate,
    RequestCreated,
    RequestOut,
    RequestUpdate,
)
from app.services import audit, matching
from app.services.exports import export_response
from app.services.notifications import notify, users_with_permission
from app.services.references import next_reference
from app.services.text import like_escape, normalize_key, phone_key

router = APIRouter(tags=["requests"])

REQUEST_STATUS_LABELS = {
    "new": "Nouvelle demande", "to_contact": "À contacter", "contacted": "Contacté", "proposed": "Biens proposés",
    "visit_scheduled": "Visite planifiée", "negotiation": "Négociation", "converted": "Convertie avec succès",
    "closed_lost": "Clôturée sans succès", "archived": "Archivée",
}
CONTACT_ACTIVITIES = {ActivityType.CALL, ActivityType.MEETING, ActivityType.EMAIL, ActivityType.WHATSAPP, ActivityType.SMS, ActivityType.VISIT}
EARLY_STATUSES = {RequestStatus.NEW, RequestStatus.TO_CONTACT}
CRITERIA_FIELDS = {
    "property_type", "transaction_type", "budget_min", "budget_max", "currency", "city", "neighborhood",
    "surface_min", "surface_max", "bedrooms_min", "bathrooms_min", "required_features", "preferred_features",
}
AUDIT_FIELDS = sorted(CRITERIA_FIELDS | {"comments", "priority", "status", "close_reason", "next_follow_up_at", "internal_notes", "assigned_agent_id"})


class RequestFilters:
    def __init__(
        self,
        q: str | None = Query(None, description="Nom, téléphone, e-mail du client ou référence"),
        reference: str | None = None,
        status: str | None = Query(None, description="Statuts séparés par des virgules ; 'open' = tous les statuts ouverts"),
        priority: str | None = None,
        assigned_agent_id: str | None = Query(None, description="uuid, 'me' ou 'none'"),
        property_type: str | None = None,
        transaction_type: str | None = None,
        city: str | None = None,
        neighborhood: str | None = None,
        budget_min: Decimal | None = Query(None, description="Budget maximum du client >= cette valeur"),
        budget_max: Decimal | None = Query(None, description="Budget maximum du client <= cette valeur"),
        date_from: date | None = None,
        date_to: date | None = None,
        waiting: bool | None = Query(None, description="true = demandes ouvertes sans aucun bien correspondant"),
        min_score: int | None = Query(None, ge=0, le=100),
        overdue: bool | None = None,
        source: str | None = None,
        customer_id: str | None = None,
        sort: Literal["created_at", "updated_at", "priority", "next_follow_up_at", "budget_max", "reference"] = "created_at",
        order: Literal["asc", "desc"] = "desc",
    ):
        self.__dict__.update(locals())
        del self.__dict__["self"]

    def apply(self, stmt, p: Principal):
        f = self
        stmt = stmt.join(Customer, Customer.id == CustomerRequest.customer_id)
        scope = request_scope(p)
        if scope is not None:
            stmt = stmt.where(scope)
        if f.q:
            raw = f.q.strip()
            term = f"%{like_escape(raw)}%"
            conds = [Customer.full_name.ilike(term), Customer.email.ilike(term), CustomerRequest.reference.ilike(term)]
            pk = phone_key(raw)
            if pk and len(pk) >= 4:
                conds.append(Customer.phone_key.like(f"%{pk}%"))
            stmt = stmt.where(or_(*conds))
        if f.reference:
            stmt = stmt.where(CustomerRequest.reference.ilike(f"%{like_escape(f.reference.strip())}%"))
        statuses = csv_list(f.status)
        if statuses == ["open"]:
            stmt = stmt.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES))
        elif statuses:
            try:
                stmt = stmt.where(CustomerRequest.status.in_([RequestStatus(s) for s in statuses]))
            except ValueError as exc:
                raise HTTPException(422, "Statut inconnu.") from exc
        else:
            stmt = stmt.where(CustomerRequest.status != RequestStatus.ARCHIVED)
        if prios := csv_list(f.priority):
            stmt = stmt.where(CustomerRequest.priority.in_([Priority(x) for x in prios]))
        if f.assigned_agent_id == "me":
            stmt = stmt.where(CustomerRequest.assigned_agent_id == p.id)
        elif f.assigned_agent_id == "none":
            stmt = stmt.where(CustomerRequest.assigned_agent_id.is_(None))
        elif f.assigned_agent_id:
            stmt = stmt.where(CustomerRequest.assigned_agent_id == parse_uuid(f.assigned_agent_id))
        if types := csv_list(f.property_type):
            stmt = stmt.where(CustomerRequest.property_type.in_(types))
        if f.transaction_type:
            stmt = stmt.where(CustomerRequest.transaction_type == f.transaction_type)
        if f.city:
            stmt = stmt.where(CustomerRequest.city_key == normalize_key(f.city))
        if f.neighborhood:
            stmt = stmt.where(CustomerRequest.neighborhood.ilike(f"%{like_escape(f.neighborhood.strip())}%"))
        if f.budget_min is not None:
            stmt = stmt.where(CustomerRequest.budget_max >= f.budget_min)
        if f.budget_max is not None:
            stmt = stmt.where(CustomerRequest.budget_max <= f.budget_max)
        if f.date_from:
            stmt = stmt.where(CustomerRequest.created_at >= day_start(f.date_from))
        if f.date_to:
            stmt = stmt.where(CustomerRequest.created_at < day_start(f.date_to) + timedelta(days=1))
        if f.waiting is True:
            stmt = stmt.where(CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), ~matching.has_active_match())
        elif f.waiting is False:
            stmt = stmt.where(matching.has_active_match())
        if f.min_score is not None:
            best = (
                select(func.max(Match.score))
                .where(Match.request_id == CustomerRequest.id, Match.is_active.is_(True))
                .correlate(CustomerRequest)
                .scalar_subquery()
            )
            stmt = stmt.where(best >= f.min_score)
        if f.overdue:
            stmt = stmt.where(
                CustomerRequest.next_follow_up_at < utcnow(), CustomerRequest.status.in_(OPEN_REQUEST_STATUSES)
            )
        if f.source:
            stmt = stmt.where(CustomerRequest.source == f.source)
        if f.customer_id:
            stmt = stmt.where(CustomerRequest.customer_id == parse_uuid(f.customer_id))
        if f.sort == "priority":
            rank = case(
                {Priority.URGENT: 4, Priority.HIGH: 3, Priority.NORMAL: 2, Priority.LOW: 1},
                value=CustomerRequest.priority,
            )
            stmt = stmt.order_by(rank.desc() if f.order == "desc" else rank.asc(), CustomerRequest.created_at.desc())
        else:
            col = getattr(CustomerRequest, f.sort)
            stmt = stmt.order_by(col.asc().nulls_last() if f.order == "asc" else col.desc().nulls_last(), CustomerRequest.id)
        return stmt


def _duplicates(db: Session, p: Principal, phone: str | None, email: str | None, exclude_id=None) -> list[DuplicateCandidate]:
    conds = []
    pk = phone_key(phone)
    if pk:
        conds.append(Customer.phone_key == pk)
    if email:
        conds.append(func.lower(Customer.email) == email.lower())
    if not conds:
        return []
    stmt = select(Customer).where(or_(*conds), Customer.is_archived.is_(False)).limit(5)
    if exclude_id:
        stmt = stmt.where(Customer.id != exclude_id)
    visible_scope = customer_scope(p)
    visible_ids = set()
    if visible_scope is not None:
        visible_ids = set(db.scalars(select(Customer.id).where(or_(*conds), visible_scope)).all())
    out = []
    for c in db.scalars(stmt).all():
        visible = visible_scope is None or c.id in visible_ids
        reason = "Même téléphone" if pk and c.phone_key == pk else "Même e-mail"
        out.append(
            DuplicateCandidate(
                id=c.id, reference=c.reference, reason=reason,
                full_name=c.full_name if visible else c.full_name.split(" ")[0] + " …",
                phone=c.phone if visible else None, email=c.email if visible else None,
            )
        )
    return out


def _add_activity(db: Session, req: CustomerRequest, user_id, type_: ActivityType, summary: str, property_id=None) -> Activity:
    a = Activity(type=type_, summary=summary, customer_id=req.customer_id, request_id=req.id, property_id=property_id, created_by_id=user_id)
    db.add(a)
    return a


def _summary(db: Session, req: CustomerRequest) -> dict | None:
    return match_summaries(db, [req.id]).get(req.id)


@router.get("/requests", response_model=Page[RequestOut])
def list_requests(filters: RequestFilters = Depends(), pg: Pagination = Depends(), p: Principal = Depends(require("requests.view")), db: Session = Depends(get_db)):
    items, total = paginate(db, filters.apply(select(CustomerRequest), p), pg)
    sums = match_summaries(db, [i.id for i in items])
    return Page(items=[request_out(i, sums.get(i.id)) for i in items], total=total, page=pg.page, page_size=pg.page_size)


@router.get("/requests/export")
def export_requests(
    fmt: Literal["csv", "xlsx"] = "csv",
    filters: RequestFilters = Depends(),
    p: Principal = Depends(require("requests.view", "requests.export")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(filters.apply(select(CustomerRequest), p)).unique().all()
    sums = match_summaries(db, [r.id for r in rows])
    headers = ["Référence", "Client", "Téléphone", "E-mail", "Type", "Transaction", "Ville", "Quartier", "Budget min",
               "Budget max", "Surface min", "Chambres min", "Priorité", "Statut", "Agent", "Biens correspondants",
               "Meilleur score", "Prochaine relance", "Créée le"]
    data = []
    for r in rows:
        s = sums.get(r.id) or {}
        data.append([r.reference, r.customer.full_name, r.customer.phone, r.customer.email, r.property_type, r.transaction_type,
                     r.city, r.neighborhood, r.budget_min, r.budget_max, r.surface_min, r.bedrooms_min, r.priority,
                     REQUEST_STATUS_LABELS[r.status.value], r.assigned_agent.full_name if r.assigned_agent else "",
                     s.get("active_count", 0), s.get("best_score"), r.next_follow_up_at, r.created_at])
    audit.log(db, user_id=p.id, action="export", entity_type="request", changes={"rows": len(data)})
    db.commit()
    return export_response("demandes", fmt, headers, data)


@router.post("/requests", response_model=RequestCreated, status_code=201)
def create_request(
    data: RequestCreate,
    request: Request,
    allow_duplicate_customer: bool = False,
    p: Principal = Depends(require("requests.create")),
    db: Session = Depends(get_db),
):
    validate_category(db, data.property_type)
    required = validate_features(db, data.required_features)
    preferred = validate_features(db, data.preferred_features)
    ip = client_ip(request)

    dups: list[DuplicateCandidate] = []
    if data.customer_id:
        customer = db.scalars(select(Customer).where(Customer.id == data.customer_id)).first()
        scope = customer_scope(p)
        if customer is None or (scope is not None and not db.scalar(select(Customer.id).where(Customer.id == customer.id, scope))):
            raise HTTPException(404, "Client introuvable.")
    else:
        if not p.can("customers.create"):
            raise HTTPException(403, "Vous n'êtes pas autorisé à créer des clients.")
        dups = _duplicates(db, p, data.customer.phone, data.customer.email)
        if dups and not allow_duplicate_customer:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"message": "Un client existe déjà avec ces coordonnées.", "duplicates": [d.model_dump(mode="json") for d in dups]},
            )
        c = data.customer
        customer = Customer(
            reference=next_reference(db, "CLI"), full_name=c.full_name.strip(), phone=c.phone, phone_key=phone_key(c.phone),
            email=c.email, preferred_contact=c.preferred_contact, source=c.source or data.source, preferences=c.preferences,
            internal_notes=c.internal_notes, created_by_id=p.id,
        )
        db.add(customer)
        db.flush()
        audit.log(db, user_id=p.id, action="create", entity_type="customer", entity_id=customer.id, label=customer.reference, ip=ip)

    agent_id = data.assigned_agent_id
    if agent_id and agent_id != p.id and not p.can("requests.assign"):
        raise HTTPException(403, "Vous n'êtes pas autorisé à assigner des demandes.")
    if agent_id:
        ensure_user(db, agent_id)
    elif not p.can("requests.assign") and p.user.is_agent:
        agent_id = p.id  # an agent creating a request for their own customer keeps it

    req = CustomerRequest(
        reference=next_reference(db, "DEM"),
        customer_id=customer.id,
        property_type=data.property_type,
        transaction_type=data.transaction_type,
        budget_min=data.budget_min,
        budget_max=data.budget_max,
        currency=data.currency,
        city=data.city.strip(),
        city_key=normalize_key(data.city),
        neighborhood=(data.neighborhood or "").strip() or None,
        neighborhood_key=normalize_key(data.neighborhood),
        surface_min=data.surface_min,
        surface_max=data.surface_max,
        bedrooms_min=data.bedrooms_min,
        bathrooms_min=data.bathrooms_min,
        required_features=required,
        preferred_features=preferred,
        comments=data.comments,
        internal_notes=data.internal_notes,
        priority=data.priority,
        source=data.source,
        status=RequestStatus.NEW,
        assigned_agent_id=agent_id,
        assigned_at=utcnow() if agent_id else None,
        next_follow_up_at=data.next_follow_up_at,
        created_by_id=p.id,
    )
    if customer.assigned_agent_id is None and agent_id:
        customer.assigned_agent_id = agent_id
    db.add(req)
    db.flush()  # the request is persisted regardless of whether any property matches
    stats = matching.refresh_for_request(db, req)
    _add_activity(db, req, p.id, ActivityType.NOTE, f"Demande {req.reference} enregistrée — {stats['active']} bien(s) correspondant(s).")
    audit.log(db, user_id=p.id, action="create", entity_type="request", entity_id=req.id, label=req.reference, ip=ip)

    notify(
        db, users_with_permission(db, "requests.assign"), type="request_new",
        title=f"Nouvelle demande {req.reference} — {customer.full_name}",
        body=f"{req.property_type} · {req.city}{' / ' + req.neighborhood if req.neighborhood else ''} · {stats['active']} bien(s) correspondant(s)",
        link=f"/app/requests/{req.id}", entity_type="request", entity_id=req.id, dedupe_key=f"request_new:{req.id}",
        exclude_user_id=p.id,
    )
    if agent_id and agent_id != p.id:
        _notify_assignment(db, req, p.id)
    db.commit()
    db.refresh(req)

    if stats["active"] == 0:
        message = ("Demande enregistrée. Aucun bien correspondant n'est disponible actuellement : le client est placé en "
                   "liste d'attente et l'agent sera notifié automatiquement dès qu'un bien correspondant sera ajouté.")
    else:
        message = f"Demande enregistrée. {stats['active']} bien(s) correspondant(s) trouvé(s)."
    return RequestCreated(request=request_out(req, _summary(db, req)), match_count=stats["active"], message=message, duplicate_customers=dups)


def _notify_assignment(db: Session, req: CustomerRequest, actor_id) -> None:
    notify(
        db, [req.assigned_agent_id], type="request_assigned",
        title=f"Demande {req.reference} vous a été assignée",
        body=f"{req.customer.full_name} · {req.property_type} · {req.city}",
        link=f"/app/requests/{req.id}", entity_type="request", entity_id=req.id,
        dedupe_key=f"assigned:{req.id}:{req.assigned_agent_id}:{req.assigned_at.isoformat() if req.assigned_at else ''}",
        exclude_user_id=actor_id,
    )


@router.get("/requests/{request_id}", response_model=RequestOut)
def get_request(request_id: str, p: Principal = Depends(require("requests.view")), db: Session = Depends(get_db)):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    return request_out(req, _summary(db, req))


def apply_status_change(db: Session, req: CustomerRequest, new_status: RequestStatus, user_id, reason: str | None = None) -> None:
    old = req.status
    if old == new_status:
        return
    req.status = new_status
    if new_status in CLOSED_REQUEST_STATUSES:
        req.closed_at = utcnow()
        req.close_reason = reason or req.close_reason
    elif old in CLOSED_REQUEST_STATUSES:
        req.closed_at = None
    if new_status not in EARLY_STATUSES and new_status not in CLOSED_REQUEST_STATUSES and req.first_contacted_at is None:
        req.first_contacted_at = utcnow()
    _add_activity(db, req, user_id, ActivityType.STATUS_CHANGE,
                  f"Statut : {REQUEST_STATUS_LABELS[old.value]} → {REQUEST_STATUS_LABELS[new_status.value]}" + (f" ({reason})" if reason else ""))


@router.patch("/requests/{request_id}", response_model=RequestOut)
def update_request(request_id: str, data: RequestUpdate, request: Request, p: Principal = Depends(require("requests.edit")), db: Session = Depends(get_db)):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    fields = data.model_dump(exclude_unset=True)
    if fields.get("property_type"):
        validate_category(db, fields["property_type"])
    for k in ("required_features", "preferred_features"):
        if k in fields:
            fields[k] = validate_features(db, fields[k] or [])
    for required in ("property_type", "transaction_type", "city", "currency"):
        if required in fields and fields[required] is None:
            raise HTTPException(422, f"Le champ {required} est obligatoire.")
    new_status = fields.pop("status", None)
    reason = fields.pop("close_reason", None)
    if new_status in (RequestStatus.ARCHIVED,) and not p.can("requests.archive"):
        raise HTTPException(403, "Vous n'êtes pas autorisé à archiver des demandes.")
    if new_status == RequestStatus.CLOSED_LOST and not (reason or "").strip():
        raise HTTPException(422, "Indiquez le motif de clôture sans succès.")
    if req.status == RequestStatus.ARCHIVED and new_status not in (None, RequestStatus.ARCHIVED) and not p.can("requests.archive"):
        raise HTTPException(403, "Vous n'êtes pas autorisé à réactiver une demande archivée.")

    before = audit.snapshot(req, AUDIT_FIELDS)
    for k, v in fields.items():
        setattr(req, k, v)
    if req.budget_min is not None and req.budget_max is not None and req.budget_min > req.budget_max:
        raise HTTPException(422, "Le budget minimum doit être inférieur au budget maximum.")
    if req.surface_min is not None and req.surface_max is not None and req.surface_min > req.surface_max:
        raise HTTPException(422, "La surface minimum doit être inférieure à la surface maximum.")
    req.city_key = normalize_key(req.city)
    req.neighborhood_key = normalize_key(req.neighborhood)
    if new_status is not None:
        apply_status_change(db, req, new_status, p.id, reason)
    elif reason is not None:
        req.close_reason = reason
    changes = audit.diff(before, audit.snapshot(req, AUDIT_FIELDS))
    if changes:
        audit.log(db, user_id=p.id, action="update", entity_type="request", entity_id=req.id, label=req.reference, changes=changes, ip=client_ip(request))
    if CRITERIA_FIELDS & set(changes) or "status" in changes:
        matching.refresh_for_request(db, req)
    db.commit()
    db.refresh(req)
    return request_out(req, _summary(db, req))


@router.post("/requests/{request_id}/assign", response_model=RequestOut)
def assign_request(request_id: str, data: AssignIn, request: Request, p: Principal = Depends(require("requests.assign")), db: Session = Depends(get_db)):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    if data.agent_id:
        agent = ensure_user(db, data.agent_id)
        if not agent.is_agent:
            raise HTTPException(422, "Cet utilisateur n'est pas un agent commercial.")
    old = req.assigned_agent_id
    req.assigned_agent_id = data.agent_id
    req.assigned_at = utcnow() if data.agent_id else None
    if data.agent_id and req.status == RequestStatus.NEW:
        req.status = RequestStatus.TO_CONTACT
    if data.agent_id and req.customer.assigned_agent_id is None:
        req.customer.assigned_agent_id = data.agent_id
    audit.log(db, user_id=p.id, action="assign", entity_type="request", entity_id=req.id, label=req.reference,
              changes={"assigned_agent_id": {"old": str(old) if old else None, "new": str(data.agent_id) if data.agent_id else None}},
              ip=client_ip(request))
    db.flush()
    db.refresh(req)
    _add_activity(db, req, p.id, ActivityType.NOTE, f"Demande assignée à {req.assigned_agent.full_name if req.assigned_agent else 'personne'}.")
    if data.agent_id:
        _notify_assignment(db, req, p.id)
    db.commit()
    db.refresh(req)
    return request_out(req, _summary(db, req))


@router.post("/requests/{request_id}/claim", response_model=RequestOut)
def claim_request(request_id: str, request: Request, p: Principal = Depends(require("requests.edit")), db: Session = Depends(get_db)):
    """An agent takes an unassigned request for themself."""
    req = get_request_scoped(db, p, parse_uuid(request_id))
    if req.assigned_agent_id is not None:
        raise HTTPException(409, "Cette demande est déjà assignée.")
    if not p.user.is_agent:
        raise HTTPException(403, "Seuls les agents commerciaux peuvent prendre en charge une demande.")
    req.assigned_agent_id = p.id
    req.assigned_at = utcnow()
    if req.status == RequestStatus.NEW:
        req.status = RequestStatus.TO_CONTACT
    if req.customer.assigned_agent_id is None:
        req.customer.assigned_agent_id = p.id
    _add_activity(db, req, p.id, ActivityType.NOTE, f"Demande prise en charge par {p.user.full_name}.")
    audit.log(db, user_id=p.id, action="claim", entity_type="request", entity_id=req.id, label=req.reference, ip=client_ip(request))
    db.commit()
    db.refresh(req)
    return request_out(req, _summary(db, req))


@router.get("/requests/{request_id}/matches", response_model=list[MatchOut])
def request_matches(
    request_id: str,
    include_inactive: bool = False,
    include_near_misses: bool = False,
    p: Principal = Depends(require("requests.view", "matches.view")),
    db: Session = Depends(get_db),
):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    stmt = select(Match).where(Match.request_id == req.id)
    if not include_inactive:
        stmt = stmt.where(Match.is_active.is_(True))
    ms = db.scalars(stmt.order_by(Match.is_active.desc(), Match.score.desc())).unique().all()
    out = [match_out(m, req=req, prop=m.property) for m in ms]
    if include_near_misses:
        known = {m.property_id for m in ms}
        for prop, ev in matching.near_misses(db, req):
            if prop.id not in known:
                out.append(match_out(None, req=req, prop=prop, score=ev.score, category=MatchCategory.INELIGIBLE, explanation=ev.explanation()))
    return out


@router.post("/requests/{request_id}/rematch", response_model=list[MatchOut])
def rematch(request_id: str, p: Principal = Depends(require("requests.view", "matches.view")), db: Session = Depends(get_db)):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    matching.refresh_for_request(db, req)
    db.commit()
    ms = db.scalars(select(Match).where(Match.request_id == req.id, Match.is_active.is_(True)).order_by(Match.score.desc())).unique().all()
    return [match_out(m, req=req, prop=m.property) for m in ms]


@router.get("/requests/{request_id}/activities", response_model=list[ActivityOut])
def request_activities(request_id: str, p: Principal = Depends(require("requests.view")), db: Session = Depends(get_db)):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    return db.scalars(select(Activity).where(Activity.request_id == req.id).order_by(Activity.occurred_at.desc())).unique().all()


@router.post("/requests/{request_id}/activities", response_model=ActivityOut, status_code=201)
def add_request_activity(request_id: str, data: ActivityIn, p: Principal = Depends(require("requests.edit")), db: Session = Depends(get_db)):
    req = get_request_scoped(db, p, parse_uuid(request_id))
    if data.type == ActivityType.STATUS_CHANGE:
        raise HTTPException(422, "Type d'activité réservé au système.")
    if data.property_id and not db.get(Property, data.property_id):
        raise HTTPException(422, "Bien inconnu.")
    a = _add_activity(db, req, p.id, data.type, data.summary, data.property_id)
    if data.occurred_at:
        a.occurred_at = data.occurred_at
    if data.type in CONTACT_ACTIVITIES:
        if req.first_contacted_at is None:
            req.first_contacted_at = a.occurred_at or utcnow()
        if req.status in EARLY_STATUSES:
            apply_status_change(db, req, RequestStatus.CONTACTED, p.id)
    db.commit()
    db.refresh(a)
    return a


def waiting_stats(db: Session, p: Principal) -> dict:
    stmt = select(func.count()).select_from(CustomerRequest).where(
        CustomerRequest.status.in_(OPEN_REQUEST_STATUSES), ~matching.has_active_match()
    )
    scope = request_scope(p)
    if scope is not None:
        stmt = stmt.where(scope)
    unassigned = stmt.where(CustomerRequest.assigned_agent_id.is_(None))
    return {"waiting": db.scalar(stmt) or 0, "waiting_unassigned": db.scalar(unassigned) or 0}


@router.get("/requests-waiting/stats")
def waiting_list_stats(p: Principal = Depends(require("requests.view")), db: Session = Depends(get_db)):
    return waiting_stats(db, p)

