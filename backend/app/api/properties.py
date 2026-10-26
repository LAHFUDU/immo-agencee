from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.helpers import (
    Pagination,
    ensure_user,
    not_found,
    paginate,
    parse_uuid,
    property_out,
    validate_category,
    validate_features,
)
from app.core.db import get_db
from app.core.deps import Principal, client_ip, require
from app.models import AuditLog, Match, Owner, Property, PropertyDocument, PropertyPhoto, User
from app.models.enums import PropertyStatus
from app.schemas.common import Page
from app.schemas.properties import (
    BulkStatusChange,
    DocumentOut,
    OwnerIn,
    OwnerOut,
    PropertyCreate,
    PropertyOut,
    PropertyUpdate,
    StatusChange,
)
from app.services import audit, imports, matching
from app.services.exports import export_response
from app.services.properties import change_status
from app.services.references import next_reference
from app.services.storage import DOCUMENT_TYPES, IMAGE_TYPES, get_storage, new_key, read_validated, safe_filename
from app.services.text import like_escape, normalize_key

router = APIRouter(tags=["properties"])

MATCH_FIELDS = {
    "property_type", "transaction_type", "city", "neighborhood", "surface", "price", "currency",
    "bedrooms", "bathrooms", "features",
}
AUDIT_FIELDS = [
    "property_type", "transaction_type", "title", "description", "city", "neighborhood", "address", "surface", "price",
    "currency", "bedrooms", "bathrooms", "floor", "features", "is_published", "latitude", "longitude",
    "internal_notes", "owner_id", "responsible_id",
]


def csv_list(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def form_bool(value: str | None, *, default: bool) -> bool:
    """Explicit form boolean parsing: an absent field keeps the (safe) default instead of becoming False."""
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "on", "yes", "oui")


def day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


class PropertyFilters:
    def __init__(
        self,
        q: str | None = None,
        reference: str | None = None,
        property_type: str | None = Query(None, description="Codes séparés par des virgules"),
        transaction_type: str | None = None,
        city: str | None = None,
        neighborhood: str | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        surface_min: Decimal | None = None,
        surface_max: Decimal | None = None,
        bedrooms_min: int | None = None,
        status: str | None = Query(None, description="Statuts séparés par des virgules"),
        responsible_id: str | None = None,
        features: str | None = None,
        is_published: bool | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort: Literal["created_at", "updated_at", "price", "surface", "reference", "city"] = "created_at",
        order: Literal["asc", "desc"] = "desc",
    ):
        self.__dict__.update(locals())
        del self.__dict__["self"]

    def apply(self, stmt, p: Principal):
        f = self
        if f.q:
            term = f"%{like_escape(f.q.strip())}%"
            conds = [Property.title.ilike(term), Property.reference.ilike(term), Property.city.ilike(term),
                     Property.neighborhood.ilike(term), Property.description.ilike(term)]
            if p.can("properties.view_confidential"):
                conds.append(Property.address.ilike(term))
            stmt = stmt.where(or_(*conds))
        if f.reference:
            stmt = stmt.where(Property.reference.ilike(f"%{like_escape(f.reference.strip())}%"))
        if types := csv_list(f.property_type):
            stmt = stmt.where(Property.property_type.in_(types))
        if f.transaction_type:
            stmt = stmt.where(Property.transaction_type == f.transaction_type)
        if f.city:
            stmt = stmt.where(Property.city_key == normalize_key(f.city))
        if f.neighborhood:
            stmt = stmt.where(Property.neighborhood_key.in_(matching.neighborhood_keys(f.neighborhood)))
        if f.price_min is not None:
            stmt = stmt.where(Property.price >= f.price_min)
        if f.price_max is not None:
            stmt = stmt.where(Property.price <= f.price_max)
        if f.surface_min is not None:
            stmt = stmt.where(Property.surface >= f.surface_min)
        if f.surface_max is not None:
            stmt = stmt.where(Property.surface <= f.surface_max)
        if f.bedrooms_min is not None:
            stmt = stmt.where(Property.bedrooms >= f.bedrooms_min)
        statuses = csv_list(f.status)
        if statuses:
            try:
                stmt = stmt.where(Property.status.in_([PropertyStatus(s) for s in statuses]))
            except ValueError as exc:
                raise HTTPException(422, "Statut inconnu.") from exc
        else:
            stmt = stmt.where(Property.status != PropertyStatus.ARCHIVED)
        if f.responsible_id:
            stmt = stmt.where(Property.responsible_id == parse_uuid(f.responsible_id))
        if feats := csv_list(f.features):
            stmt = stmt.where(Property.features.contains(feats))
        if f.is_published is not None:
            stmt = stmt.where(Property.is_published.is_(f.is_published))
        if f.date_from:
            stmt = stmt.where(Property.created_at >= day_start(f.date_from))
        if f.date_to:
            stmt = stmt.where(Property.created_at < day_start(f.date_to) + timedelta(days=1))
        col = getattr(Property, f.sort)
        stmt = stmt.order_by(col.asc() if f.order == "asc" else col.desc(), Property.id)
        return stmt


def _active_match_counts(db: Session, ids: list) -> dict:
    if not ids:
        return {}
    rows = db.execute(
        select(Match.property_id, func.count()).where(Match.property_id.in_(ids), Match.is_active.is_(True)).group_by(Match.property_id)
    ).all()
    return dict(rows)


def _get(db: Session, property_id: str) -> Property:
    prop = db.get(Property, parse_uuid(property_id))
    if prop is None:
        raise not_found("Bien")
    return prop


@router.get("/properties", response_model=Page[PropertyOut])
def list_properties(
    filters: PropertyFilters = Depends(),
    pg: Pagination = Depends(),
    p: Principal = Depends(require("properties.view")),
    db: Session = Depends(get_db),
):
    items, total = paginate(db, filters.apply(select(Property), p), pg)
    counts = _active_match_counts(db, [i.id for i in items])
    return Page(items=[property_out(i, p, counts.get(i.id, 0)) for i in items], total=total, page=pg.page, page_size=pg.page_size)


@router.get("/properties/export")
def export_properties(
    fmt: Literal["csv", "xlsx"] = "csv",
    filters: PropertyFilters = Depends(),
    p: Principal = Depends(require("properties.view", "properties.export")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(filters.apply(select(Property), p)).unique().all()
    conf = p.can("properties.view_confidential")
    headers = ["Référence", "Type", "Transaction", "Titre", "Ville", "Quartier", "Surface m²", "Prix", "Devise",
               "Chambres", "SDB", "Étage", "Équipements", "Statut", "Publié", "Responsable", "Créé le"]
    if conf:
        headers += ["Adresse", "Propriétaire", "Tél. propriétaire"]
    data = []
    for r in rows:
        line = [r.reference, r.property_type, r.transaction_type, r.title, r.city, r.neighborhood, r.surface, r.price,
                r.currency, r.bedrooms, r.bathrooms, r.floor, r.features, matching.STATUS_LABELS[r.status.value],
                "oui" if r.is_published else "non", r.responsible.full_name if r.responsible else "", r.created_at]
        if conf:
            line += [r.address, r.owner.full_name if r.owner else "", r.owner.phone if r.owner else ""]
        data.append(line)
    audit.log(db, user_id=p.id, action="export", entity_type="property", changes={"rows": len(data)})
    db.commit()
    return export_response("biens", fmt, headers, data)


@router.get("/properties/import/template")
def import_template(p: Principal = Depends(require("properties.import"))):
    return Response(
        "﻿" + imports.template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modele_import_biens.csv"'},
    )


@router.post("/properties/import")
async def import_properties(
    file: UploadFile = File(...),
    dry_run: str | None = Form(None),
    allow_duplicates: bool = Form(False),
    p: Principal = Depends(require("properties.import", "properties.create")),
    db: Session = Depends(get_db),
):
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (max 10 Mo).")
    dry_run = form_bool(dry_run, default=True)
    try:
        report = imports.run_import(db, file.filename or "", data, user_id=p.id, dry_run=dry_run, skip_duplicates=not allow_duplicates)
    except imports.ImportFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return report


@router.post("/properties/bulk-status")
def bulk_status(data: BulkStatusChange, request: Request, p: Principal = Depends(require("properties.edit")), db: Session = Depends(get_db)):
    if data.status == PropertyStatus.ARCHIVED and not p.can("properties.archive"):
        raise HTTPException(403, "Accès refusé : permission insuffisante.")
    props = db.scalars(select(Property).where(Property.id.in_(data.ids)).with_for_update(of=Property)).all()
    changed = 0
    for prop in props:
        if change_status(db, prop, data.status, user_id=p.id, ip=client_ip(request), reason=data.reason):
            changed += 1
    db.commit()
    return {"updated": changed, "requested": len(data.ids), "found": len(props)}


@router.post("/properties", response_model=PropertyOut, status_code=201)
def create_property(data: PropertyCreate, request: Request, p: Principal = Depends(require("properties.create")), db: Session = Depends(get_db)):
    validate_category(db, data.property_type)
    features = validate_features(db, data.features)
    if data.is_published and not p.can("properties.publish"):
        raise HTTPException(403, "Vous n'êtes pas autorisé à publier des biens.")
    if data.responsible_id:
        ensure_user(db, data.responsible_id)
    owner_id = data.owner_id
    if data.owner:
        owner = Owner(**data.owner.model_dump(), created_by_id=p.id)
        db.add(owner)
        db.flush()
        owner_id = owner.id
    elif owner_id and not db.get(Owner, owner_id):
        raise HTTPException(422, "Propriétaire inconnu.")
    if not p.can("properties.view_confidential"):
        # Users who cannot see confidential fields cannot set them either (avoid blind overwrites).
        owner_id = None
    payload = data.model_dump(exclude={"owner", "owner_id", "features", "status"})
    if not p.can("properties.view_confidential"):
        for f in ("address", "internal_notes", "latitude", "longitude"):
            payload[f] = None
    prop = Property(
        **payload,
        features=features,
        status=data.status,
        owner_id=owner_id,
        reference=next_reference(db, "BIEN"),
        city_key=normalize_key(data.city),
        neighborhood_key=normalize_key(data.neighborhood),
        created_by_id=p.id,
    )
    if prop.responsible_id is None:
        prop.responsible_id = p.id
    db.add(prop)
    db.flush()
    audit.log(db, user_id=p.id, action="create", entity_type="property", entity_id=prop.id, label=prop.reference, ip=client_ip(request))
    stats = matching.refresh_for_property(db, prop)
    db.commit()
    db.refresh(prop)
    return property_out(prop, p, stats["active"])


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_property(property_id: str, p: Principal = Depends(require("properties.view")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    return property_out(prop, p, _active_match_counts(db, [prop.id]).get(prop.id, 0))


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def update_property(property_id: str, data: PropertyUpdate, request: Request, p: Principal = Depends(require("properties.edit")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    fields = data.model_dump(exclude_unset=True)
    conf_fields = {"address", "internal_notes", "latitude", "longitude", "owner_id"}
    if not p.can("properties.view_confidential") and conf_fields & set(fields):
        raise HTTPException(403, "Vous n'êtes pas autorisé à modifier les informations confidentielles.")
    if "is_published" in fields and fields["is_published"] != prop.is_published and not p.can("properties.publish"):
        raise HTTPException(403, "Vous n'êtes pas autorisé à publier des biens.")
    if fields.get("property_type"):
        validate_category(db, fields["property_type"])
    if "features" in fields:
        fields["features"] = validate_features(db, fields["features"] or [])
    if fields.get("responsible_id"):
        ensure_user(db, fields["responsible_id"])
    if fields.get("owner_id") and not db.get(Owner, fields["owner_id"]):
        raise HTTPException(422, "Propriétaire inconnu.")
    for required in ("property_type", "transaction_type", "title", "city", "price", "currency"):
        if required in fields and fields[required] is None:
            raise HTTPException(422, f"Le champ {required} est obligatoire.")
    before = audit.snapshot(prop, AUDIT_FIELDS)
    for k, v in fields.items():
        setattr(prop, k, v)
    prop.city_key = normalize_key(prop.city)
    prop.neighborhood_key = normalize_key(prop.neighborhood)
    changes = audit.diff(before, audit.snapshot(prop, AUDIT_FIELDS))
    if changes:
        audit.log(db, user_id=p.id, action="update", entity_type="property", entity_id=prop.id, label=prop.reference,
                  changes=changes, ip=client_ip(request))
    if MATCH_FIELDS & set(changes):
        matching.refresh_for_property(db, prop)
    db.commit()
    db.refresh(prop)
    return property_out(prop, p, _active_match_counts(db, [prop.id]).get(prop.id, 0))


@router.post("/properties/{property_id}/status", response_model=PropertyOut)
def set_status(property_id: str, data: StatusChange, request: Request, p: Principal = Depends(require("properties.edit")), db: Session = Depends(get_db)):
    if data.status == PropertyStatus.ARCHIVED and not p.can("properties.archive"):
        raise HTTPException(403, "Accès refusé : permission insuffisante.")
    prop = db.scalar(select(Property).where(Property.id == parse_uuid(property_id)).with_for_update(of=Property))
    if prop is None:
        raise not_found("Bien")
    change_status(db, prop, data.status, user_id=p.id, ip=client_ip(request), reason=data.reason)
    db.commit()
    db.refresh(prop)
    return property_out(prop, p, _active_match_counts(db, [prop.id]).get(prop.id, 0))


@router.get("/properties/{property_id}/history")
def property_history(property_id: str, p: Principal = Depends(require("properties.view")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    rows = db.execute(
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.entity_type == "property", AuditLog.entity_id == str(prop.id))
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    ).all()
    hidden = set() if p.can("properties.view_confidential") else {"address", "internal_notes", "latitude", "longitude", "owner_id"}
    return [
        {
            "id": a.id,
            "action": a.action,
            "user": name,
            "created_at": a.created_at,
            "changes": {k: v for k, v in (a.changes or {}).items() if k not in hidden},
        }
        for a, name in rows
    ]


# ------------------------------------------------------------------ photos & documents


@router.post("/properties/{property_id}/photos", response_model=PropertyOut, status_code=201)
async def upload_photos(
    property_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    p: Principal = Depends(require("properties.edit")),
    db: Session = Depends(get_db),
):
    prop = _get(db, property_id)
    if len(prop.photos) + len(files) > 40:
        raise HTTPException(422, "40 photos maximum par bien.")
    storage = get_storage()
    pos = max([ph.position for ph in prop.photos], default=-1) + 1
    for f in files:
        data, ctype = await read_validated(f, IMAGE_TYPES)
        key = new_key(f"properties/{prop.id}/photos", IMAGE_TYPES[ctype])
        storage.save(key, data, ctype)
        db.add(PropertyPhoto(property_id=prop.id, storage_key=key, filename=safe_filename(f.filename), content_type=ctype,
                             size=len(data), position=pos, uploaded_by_id=p.id))
        pos += 1
    audit.log(db, user_id=p.id, action="photos_upload", entity_type="property", entity_id=prop.id, label=prop.reference,
              changes={"count": len(files)}, ip=client_ip(request))
    db.commit()
    db.refresh(prop)
    return property_out(prop, p)


@router.put("/properties/{property_id}/photos/order", response_model=PropertyOut)
def reorder_photos(property_id: str, ids: list[str], p: Principal = Depends(require("properties.edit")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    by_id = {str(ph.id): ph for ph in prop.photos}
    for i, pid in enumerate(ids):
        if pid in by_id:
            by_id[pid].position = i
    db.commit()
    db.refresh(prop)
    return property_out(prop, p)


@router.delete("/properties/{property_id}/photos/{photo_id}", status_code=204)
def delete_photo(property_id: str, photo_id: str, request: Request, p: Principal = Depends(require("properties.edit")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    ph = db.get(PropertyPhoto, parse_uuid(photo_id))
    if ph is None or ph.property_id != prop.id:
        raise not_found("Photo")
    get_storage().delete(ph.storage_key)
    db.delete(ph)
    audit.log(db, user_id=p.id, action="photo_delete", entity_type="property", entity_id=prop.id, label=prop.reference,
              changes={"filename": ph.filename}, ip=client_ip(request))
    db.commit()


@router.get("/properties/{property_id}/documents", response_model=list[DocumentOut])
def list_documents(property_id: str, p: Principal = Depends(require("properties.view")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    stmt = select(PropertyDocument).where(PropertyDocument.property_id == prop.id).order_by(PropertyDocument.created_at.desc())
    if not p.can("properties.view_confidential"):
        stmt = stmt.where(PropertyDocument.is_confidential.is_(False))
    return db.scalars(stmt).all()


@router.post("/properties/{property_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    property_id: str,
    request: Request,
    file: UploadFile = File(...),
    label: str | None = Form(None),
    is_confidential: str | None = Form(None),
    p: Principal = Depends(require("properties.edit", "properties.view_confidential")),
    db: Session = Depends(get_db),
):
    prop = _get(db, property_id)
    data, ctype = await read_validated(file, DOCUMENT_TYPES)
    key = new_key(f"properties/{prop.id}/documents", DOCUMENT_TYPES[ctype])
    get_storage().save(key, data, ctype)
    doc = PropertyDocument(property_id=prop.id, storage_key=key, filename=safe_filename(file.filename), content_type=ctype,
                           size=len(data), label=(label or None) and label[:160], is_confidential=form_bool(is_confidential, default=True), uploaded_by_id=p.id)
    db.add(doc)
    audit.log(db, user_id=p.id, action="document_upload", entity_type="property", entity_id=prop.id, label=prop.reference,
              changes={"filename": doc.filename}, ip=client_ip(request))
    db.commit()
    return doc


@router.delete("/properties/{property_id}/documents/{doc_id}", status_code=204)
def delete_document(property_id: str, doc_id: str, request: Request, p: Principal = Depends(require("properties.edit", "properties.view_confidential")), db: Session = Depends(get_db)):
    prop = _get(db, property_id)
    doc = db.get(PropertyDocument, parse_uuid(doc_id))
    if doc is None or doc.property_id != prop.id:
        raise not_found("Document")
    get_storage().delete(doc.storage_key)
    db.delete(doc)
    audit.log(db, user_id=p.id, action="document_delete", entity_type="property", entity_id=prop.id, label=prop.reference,
              changes={"filename": doc.filename}, ip=client_ip(request))
    db.commit()


# ------------------------------------------------------------------ owners


@router.get("/owners", response_model=list[OwnerOut])
def search_owners(q: str = "", p: Principal = Depends(require("properties.view_confidential")), db: Session = Depends(get_db)):
    stmt = select(Owner).order_by(Owner.full_name).limit(30)
    if q.strip():
        term = f"%{like_escape(q.strip())}%"
        stmt = stmt.where(or_(Owner.full_name.ilike(term), Owner.phone.ilike(term), Owner.email.ilike(term)))
    return db.scalars(stmt).all()


@router.post("/owners", response_model=OwnerOut, status_code=201)
def create_owner(data: OwnerIn, p: Principal = Depends(require("properties.edit", "properties.view_confidential")), db: Session = Depends(get_db)):
    o = Owner(**data.model_dump(), created_by_id=p.id)
    db.add(o)
    db.flush()
    audit.log(db, user_id=p.id, action="create", entity_type="owner", entity_id=o.id, label=o.full_name)
    db.commit()
    return o


@router.patch("/owners/{owner_id}", response_model=OwnerOut)
def update_owner(owner_id: str, data: OwnerIn, p: Principal = Depends(require("properties.edit", "properties.view_confidential")), db: Session = Depends(get_db)):
    o = db.get(Owner, parse_uuid(owner_id))
    if o is None:
        raise not_found("Propriétaire")
    before = audit.snapshot(o, list(OwnerIn.model_fields))
    for k, v in data.model_dump().items():
        setattr(o, k, v)
    audit.log(db, user_id=p.id, action="update", entity_type="owner", entity_id=o.id, label=o.full_name,
              changes=audit.diff(before, audit.snapshot(o, list(OwnerIn.model_fields))))
    db.commit()
    return o
