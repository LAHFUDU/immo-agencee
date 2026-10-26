import uuid
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.api.helpers import (
    Pagination,
    customer_scope,
    deal_scope,
    paginate,
    parse_uuid,
    request_scope,
)
from app.api.properties import day_start
from app.core.db import get_db, utcnow
from app.core.deps import Principal, client_ip, get_active_principal, load_session, require
from app.models import (
    AuditLog,
    CommissionRule,
    Customer,
    CustomerRequest,
    Deal,
    Notification,
    Property,
    PropertyCategory,
    PropertyDocument,
    PropertyFeature,
    PropertyPhoto,
    SavedFilter,
    User,
)
from app.models.enums import PropertyStatus
from app.schemas.common import Page
from app.schemas.deals import CommissionRuleIn, CommissionRuleOut
from app.services import audit, matching
from app.services.app_settings import DEFAULTS, get_setting, set_setting
from app.services.storage import get_storage
from app.services.text import like_escape, phone_key

router = APIRouter(tags=["system"])


# ------------------------------------------------------------------ notifications


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    is_read: bool
    email_status: str | None
    created_at: datetime


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(unread: bool = False, pg: Pagination = Depends(), p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == p.id)
    if unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    items, total = paginate(db, stmt.order_by(Notification.created_at.desc()), pg)
    return Page(items=[NotificationOut.model_validate(n, from_attributes=True) for n in items], total=total, page=pg.page, page_size=pg.page_size)


@router.get("/notifications/unread-count")
def unread_count(p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).where(Notification.user_id == p.id, Notification.is_read.is_(False))) or 0
    return {"count": n}


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: str, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    db.execute(
        update(Notification)
        .where(Notification.id == parse_uuid(notification_id), Notification.user_id == p.id)
        .values(is_read=True, read_at=utcnow())
    )
    db.commit()


@router.post("/notifications/read-all", status_code=204)
def mark_all_read(p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == p.id, Notification.is_read.is_(False)).values(is_read=True, read_at=utcnow()))
    db.commit()


# ------------------------------------------------------------------ catalogue (types & features), readable by all staff


class CategoryIn(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    label: str = Field(min_length=2, max_length=80)
    has_rooms: bool = True
    is_active: bool = True
    sort_order: int = 0


class FeatureIn(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    label: str = Field(min_length=2, max_length=80)
    is_active: bool = True
    sort_order: int = 0


@router.get("/catalog")
def catalog(p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    cats = db.scalars(select(PropertyCategory).order_by(PropertyCategory.sort_order, PropertyCategory.label)).all()
    feats = db.scalars(select(PropertyFeature).order_by(PropertyFeature.sort_order, PropertyFeature.label)).all()
    cities = db.scalars(select(Property.city).distinct().order_by(Property.city)).all()
    return {
        "property_types": [CategoryIn.model_validate(c, from_attributes=True).model_dump() for c in cats],
        "features": [FeatureIn.model_validate(f, from_attributes=True).model_dump() for f in feats],
        "cities": cities,
        "currency": get_setting(db, "agency")["default_currency"],
    }


@router.put("/settings/property-types", status_code=204)
def upsert_category(data: CategoryIn, p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    c = db.get(PropertyCategory, data.code)
    if c is None:
        db.add(PropertyCategory(**data.model_dump()))
    else:
        for k, v in data.model_dump().items():
            setattr(c, k, v)
    audit.log(db, user_id=p.id, action="upsert", entity_type="property_type", entity_id=data.code, label=data.label)
    db.commit()


@router.put("/settings/features", status_code=204)
def upsert_feature(data: FeatureIn, p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    f = db.get(PropertyFeature, data.code)
    if f is None:
        db.add(PropertyFeature(**data.model_dump()))
    else:
        for k, v in data.model_dump().items():
            setattr(f, k, v)
    audit.log(db, user_id=p.id, action="upsert", entity_type="feature", entity_id=data.code, label=data.label)
    db.commit()


# ------------------------------------------------------------------ business settings


class SettingIn(BaseModel):
    value: Any


def _validate_matching(v: dict) -> dict:
    merged = {**DEFAULTS["matching"], **v, "weights": {**DEFAULTS["matching"]["weights"], **(v.get("weights") or {})}}
    if not set(merged["eligible_statuses"]) <= {s.value for s in PropertyStatus} or not merged["eligible_statuses"]:
        raise HTTPException(422, "Statuts éligibles invalides.")
    if merged["notify_min_category"] not in ("exact", "strong", "partial"):
        raise HTTPException(422, "Catégorie de notification invalide.")
    for k in ("budget_tolerance_percent", "surface_tolerance_percent"):
        if not (0 <= float(merged[k]) <= 50):
            raise HTTPException(422, "Les tolérances doivent être comprises entre 0 et 50 %.")
    if not (50 <= int(merged["strong_threshold"]) <= 100):
        raise HTTPException(422, "Le seuil de forte correspondance doit être compris entre 50 et 100.")
    if sum(int(x) for x in merged["weights"].values()) != 50 or any(int(x) < 0 for x in merged["weights"].values()):
        raise HTTPException(422, "La somme des poids des critères optionnels doit être égale à 50.")
    return merged


@router.get("/settings")
def get_settings(p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    from app.core.config import settings as env

    return {
        **{k: get_setting(db, k) for k in DEFAULTS},
        "integrations": {
            "smtp_configured": env.smtp_configured,
            "storage_backend": env.STORAGE_BACKEND,
            "whatsapp_configured": False,
        },
    }


@router.put("/settings/{key}")
def put_setting(key: str, data: SettingIn, request: Request, p: Principal = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    if key not in DEFAULTS:
        raise HTTPException(404, "Paramètre inconnu.")
    if not isinstance(data.value, dict):
        raise HTTPException(422, "Valeur invalide.")
    value = _validate_matching(data.value) if key == "matching" else {**DEFAULTS[key], **{k: v for k, v in data.value.items() if k in DEFAULTS[key]}}
    before = get_setting(db, key)
    set_setting(db, key, value, p.id)
    audit.log(db, user_id=p.id, action="update", entity_type="setting", entity_id=key, label=key,
              changes=audit.diff(before, value), ip=client_ip(request))
    db.commit()
    if key == "matching":
        # Matching rules changed: recompute every eligible property so lists reflect the new rules.
        for prop in db.scalars(select(Property).where(Property.status != PropertyStatus.ARCHIVED)).all():
            matching.refresh_for_property(db, prop, notify_agents=False)
        db.commit()
    return get_setting(db, key)


# ------------------------------------------------------------------ commission rules


@router.get("/commission-rules", response_model=list[CommissionRuleOut])
def list_rules(p: Principal = Depends(require("commissions.view")), db: Session = Depends(get_db)):
    return db.scalars(select(CommissionRule).order_by(CommissionRule.transaction_type, CommissionRule.priority.desc())).all()


def _check_rule(db: Session, data: CommissionRuleIn):
    if data.property_type and not db.get(PropertyCategory, data.property_type):
        raise HTTPException(422, "Type de bien inconnu.")
    if data.min_price is not None and data.max_price is not None and data.min_price > data.max_price:
        raise HTTPException(422, "Prix minimum supérieur au prix maximum.")


@router.post("/commission-rules", response_model=CommissionRuleOut, status_code=201)
def create_rule(data: CommissionRuleIn, request: Request, p: Principal = Depends(require("commissions.manage")), db: Session = Depends(get_db)):
    _check_rule(db, data)
    r = CommissionRule(**data.model_dump())
    db.add(r)
    db.flush()
    audit.log(db, user_id=p.id, action="create", entity_type="commission_rule", entity_id=r.id, label=r.name,
              changes=audit.snapshot(r, list(CommissionRuleIn.model_fields)), ip=client_ip(request))
    db.commit()
    return r


@router.put("/commission-rules/{rule_id}", response_model=CommissionRuleOut)
def update_rule(rule_id: str, data: CommissionRuleIn, request: Request, p: Principal = Depends(require("commissions.manage")), db: Session = Depends(get_db)):
    _check_rule(db, data)
    r = db.get(CommissionRule, parse_uuid(rule_id))
    if r is None:
        raise HTTPException(404, "Règle introuvable.")
    before = audit.snapshot(r, list(CommissionRuleIn.model_fields))
    for k, v in data.model_dump().items():
        setattr(r, k, v)
    audit.log(db, user_id=p.id, action="update", entity_type="commission_rule", entity_id=r.id, label=r.name,
              changes=audit.diff(before, audit.snapshot(r, list(CommissionRuleIn.model_fields))), ip=client_ip(request))
    db.commit()
    return r


# ------------------------------------------------------------------ audit log


@router.get("/audit-logs")
def list_audit(
    entity_type: str | None = None, action: str | None = None, user_id: str | None = None, q: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    pg: Pagination = Depends(), p: Principal = Depends(require("audit.view")), db: Session = Depends(get_db),
):
    stmt = select(AuditLog, User.full_name).outerjoin(User, User.id == AuditLog.user_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == parse_uuid(user_id))
    if q:
        stmt = stmt.where(AuditLog.entity_label.ilike(f"%{like_escape(q)}%"))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= day_start(date_from))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < day_start(date_to) + timedelta(days=1))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(pg.page_size).offset((pg.page - 1) * pg.page_size)).all()
    return {
        "items": [
            {"id": a.id, "user": name, "user_id": a.user_id, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id,
             "entity_label": a.entity_label, "changes": a.changes, "ip": a.ip, "created_at": a.created_at}
            for a, name in rows
        ],
        "total": total, "page": pg.page, "page_size": pg.page_size,
    }


# ------------------------------------------------------------------ saved filter presets


class SavedFilterIn(BaseModel):
    page: str = Field(pattern=r"^[a-z_]{2,48}$")
    name: str = Field(min_length=1, max_length=80)
    filters: dict


@router.get("/saved-filters")
def list_saved(page: str, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavedFilter).where(SavedFilter.user_id == p.id, SavedFilter.page == page).order_by(SavedFilter.name)).all()
    return [{"id": r.id, "name": r.name, "filters": r.filters} for r in rows]


@router.post("/saved-filters", status_code=201)
def create_saved(data: SavedFilterIn, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    r = SavedFilter(user_id=p.id, page=data.page, name=data.name, filters={k: v for k, v in data.filters.items() if v not in (None, "")})
    db.add(r)
    db.commit()
    return {"id": r.id, "name": r.name, "filters": r.filters}


@router.delete("/saved-filters/{filter_id}", status_code=204)
def delete_saved(filter_id: str, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    r = db.get(SavedFilter, parse_uuid(filter_id))
    if r is None or r.user_id != p.id:
        raise HTTPException(404, "Filtre introuvable.")
    db.delete(r)
    db.commit()


# ------------------------------------------------------------------ global search


@router.get("/search")
def global_search(q: str, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return {"customers": [], "requests": [], "properties": [], "deals": []}
    term = f"%{like_escape(q)}%"
    pk = phone_key(q)
    out: dict[str, list] = {"customers": [], "requests": [], "properties": [], "deals": []}

    if p.can("customers.view"):
        conds = [Customer.full_name.ilike(term), Customer.reference.ilike(term), Customer.email.ilike(term)]
        if pk and len(pk) >= 4:
            conds.append(Customer.phone_key.like(f"%{pk}%"))
        stmt = select(Customer).where(or_(*conds))
        if (s := customer_scope(p)) is not None:
            stmt = stmt.where(s)
        out["customers"] = [{"id": c.id, "label": c.full_name, "sub": f"{c.reference} · {c.phone or c.email or ''}"}
                            for c in db.scalars(stmt.limit(8)).unique().all()]
    if p.can("requests.view"):
        conds = [CustomerRequest.reference.ilike(term), Customer.full_name.ilike(term)]
        if pk and len(pk) >= 4:
            conds.append(Customer.phone_key.like(f"%{pk}%"))
        stmt = select(CustomerRequest).join(Customer, Customer.id == CustomerRequest.customer_id).where(or_(*conds))
        if (s := request_scope(p)) is not None:
            stmt = stmt.where(s)
        out["requests"] = [{"id": r.id, "label": f"{r.reference} — {r.customer.full_name}", "sub": f"{r.property_type} · {r.city}"}
                           for r in db.scalars(stmt.order_by(CustomerRequest.created_at.desc()).limit(8)).unique().all()]
    if p.can("properties.view"):
        conds = [Property.reference.ilike(term), Property.title.ilike(term), Property.neighborhood.ilike(term)]
        if p.can("properties.view_confidential"):
            conds.append(Property.address.ilike(term))
        stmt = select(Property).where(or_(*conds))
        out["properties"] = [{"id": x.id, "label": f"{x.reference} — {x.title}", "sub": f"{x.city} · {matching.STATUS_LABELS[x.status.value]}"}
                             for x in db.scalars(stmt.order_by(Property.created_at.desc()).limit(8)).unique().all()]
    if p.can("deals.view"):
        stmt = select(Deal).where(Deal.reference.ilike(term))
        if (s := deal_scope(p)) is not None:
            stmt = stmt.where(s)
        out["deals"] = [{"id": d.id, "label": d.reference, "sub": d.customer.full_name} for d in db.scalars(stmt.limit(5)).unique().all()]
    return out


# ------------------------------------------------------------------ protected files


@router.get("/files/photos/{photo_id}")
def get_photo(photo_id: str, request: Request, db: Session = Depends(get_db)):
    ph = db.get(PropertyPhoto, parse_uuid(photo_id))
    if ph is None:
        raise HTTPException(404, "Photo introuvable.")
    prop = ph.property
    public = prop.is_published and prop.status == PropertyStatus.AVAILABLE and get_setting(db, "public_site")["enabled"]
    if not public:
        sess = load_session(request, db)
        if sess is None or "properties.view" not in sess.user.permission_codes():
            raise HTTPException(404, "Photo introuvable.")
    data = get_storage().load(ph.storage_key)
    return Response(data, media_type=ph.content_type, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})


@router.get("/files/documents/{doc_id}")
def get_document(doc_id: str, p: Principal = Depends(require("properties.view")), db: Session = Depends(get_db)):
    doc = db.get(PropertyDocument, parse_uuid(doc_id))
    if doc is None or (doc.is_confidential and not p.can("properties.view_confidential")):
        raise HTTPException(404, "Document introuvable.")
    data = get_storage().load(doc.storage_key)
    return Response(
        data, media_type=doc.content_type,
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


# ------------------------------------------------------------------ health


@router.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, "database unavailable") from exc
    return {"status": "ok", "database": "ok"}
