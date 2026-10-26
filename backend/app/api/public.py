"""Optional public website API. Exposes only properties explicitly published AND available,
with a strict whitelist of fields (no address, owner, internal notes or staff information)."""

import uuid
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.helpers import Pagination, paginate, photo_url, validate_category, validate_features
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import client_ip
from app.models import Activity, Customer, CustomerRequest, Property, PropertyCategory, PropertyFeature
from app.models.enums import ActivityType, ContactMethod, CustomerSource, RequestStatus, TransactionType
from app.schemas.common import Page
from app.services import audit, matching, rate_limit
from app.services.app_settings import get_setting
from app.services.notifications import notify, users_with_permission
from app.services.references import next_reference
from app.services.text import normalize_key, phone_key

router = APIRouter(prefix="/public", tags=["public"])


def site_enabled(db: Session = Depends(get_db)) -> dict:
    cfg = get_setting(db, "public_site")
    if not cfg["enabled"]:
        raise HTTPException(404, "Site public désactivé.")
    return cfg


def _visible():
    return [Property.is_published.is_(True), Property.status == "available"]


class PublicProperty(BaseModel):
    reference: str
    property_type: str
    transaction_type: TransactionType
    title: str
    description: str | None
    city: str
    neighborhood: str | None
    surface: Decimal | None
    price: Decimal | None
    currency: str
    bedrooms: int | None
    bathrooms: int | None
    floor: int | None
    features: list[str]
    photos: list[str]


def _out(p: Property, show_price: bool) -> PublicProperty:
    return PublicProperty(
        reference=p.reference, property_type=p.property_type, transaction_type=p.transaction_type, title=p.title,
        description=p.description, city=p.city, neighborhood=p.neighborhood, surface=p.surface,
        price=p.price if show_price else None, currency=p.currency, bedrooms=p.bedrooms, bathrooms=p.bathrooms,
        floor=p.floor, features=p.features or [], photos=[photo_url(ph) for ph in p.photos],
    )


@router.get("/config")
def public_config(cfg: dict = Depends(site_enabled), db: Session = Depends(get_db)):
    agency = get_setting(db, "agency")
    return {"agency": {k: agency[k] for k in ("name", "phone", "email", "address")}, "show_price": cfg["show_price"]}


@router.get("/catalog")
def public_catalog(cfg: dict = Depends(site_enabled), db: Session = Depends(get_db)):
    return {
        "property_types": [{"code": c.code, "label": c.label} for c in db.scalars(
            select(PropertyCategory).where(PropertyCategory.is_active.is_(True)).order_by(PropertyCategory.sort_order)).all()],
        "features": [{"code": f.code, "label": f.label} for f in db.scalars(
            select(PropertyFeature).where(PropertyFeature.is_active.is_(True)).order_by(PropertyFeature.sort_order)).all()],
        "cities": db.scalars(select(Property.city).where(*_visible()).distinct().order_by(Property.city)).all(),
    }


@router.get("/properties", response_model=Page[PublicProperty])
def public_properties(
    city: str | None = None, neighborhood: str | None = None, property_type: str | None = None,
    transaction_type: TransactionType | None = None, price_min: Decimal | None = None, price_max: Decimal | None = None,
    surface_min: Decimal | None = None, surface_max: Decimal | None = None, bedrooms_min: int | None = Query(None, ge=0),
    sort: str = "recent", pg: Pagination = Depends(), cfg: dict = Depends(site_enabled), db: Session = Depends(get_db),
):
    stmt = select(Property).where(*_visible())
    if city:
        stmt = stmt.where(Property.city_key == normalize_key(city))
    if neighborhood:
        stmt = stmt.where(Property.neighborhood_key.in_(matching.neighborhood_keys(neighborhood)))
    if property_type:
        stmt = stmt.where(Property.property_type == property_type)
    if transaction_type:
        stmt = stmt.where(Property.transaction_type == transaction_type)
    if price_min is not None:
        stmt = stmt.where(Property.price >= price_min)
    if price_max is not None:
        stmt = stmt.where(Property.price <= price_max)
    if surface_min is not None:
        stmt = stmt.where(Property.surface >= surface_min)
    if surface_max is not None:
        stmt = stmt.where(Property.surface <= surface_max)
    if bedrooms_min is not None:
        stmt = stmt.where(Property.bedrooms >= bedrooms_min)
    order = {"price_asc": Property.price.asc(), "price_desc": Property.price.desc()}.get(sort, Property.created_at.desc())
    items, total = paginate(db, stmt.order_by(order, Property.id), pg)
    return Page(items=[_out(i, cfg["show_price"]) for i in items], total=total, page=pg.page, page_size=pg.page_size)


@router.get("/properties/{reference}", response_model=PublicProperty)
def public_property(reference: str, cfg: dict = Depends(site_enabled), db: Session = Depends(get_db)):
    p = db.scalars(select(Property).where(Property.reference == reference, *_visible())).first()
    if p is None:
        raise HTTPException(404, "Bien introuvable ou plus disponible.")
    return _out(p, cfg["show_price"])


class AntiSpam(BaseModel):
    website: str = Field(default="", max_length=200)  # honeypot: must stay empty
    consent: bool

    @model_validator(mode="after")
    def _consent(self):
        if not self.consent:
            raise ValueError("Votre consentement est requis pour traiter votre demande.")
        return self


class PublicRequestIn(AntiSpam):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(pattern=r"^[0-9+()\-.\s]{6,32}$")
    email: EmailStr | None = None
    preferred_contact: ContactMethod = ContactMethod.PHONE
    property_type: str = Field(max_length=32)
    transaction_type: TransactionType
    city: str = Field(min_length=2, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=120)
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    surface_min: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    bedrooms_min: int | None = Field(default=None, ge=0, le=20)
    features: list[str] = Field(default=[], max_length=20)
    comments: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _ranges(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("Le budget minimum doit être inférieur au budget maximum.")
        return self


class PublicContactIn(AntiSpam):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, pattern=r"^[0-9+()\-.\s]{6,32}$")
    email: EmailStr | None = None
    message: str = Field(min_length=5, max_length=3000)
    property_reference: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _contact(self):
        if not self.phone and not self.email:
            raise ValueError("Un téléphone ou un e-mail est requis.")
        return self


def _guard(db: Session, request: Request, data: AntiSpam) -> None:
    ip = client_ip(request)
    rate_limit.check(db, f"public:{ip}", settings.PUBLIC_FORM_MAX_PER_HOUR, timedelta(hours=1))
    rate_limit.hit(db, f"public:{ip}")
    if data.website.strip():
        # Bot filled the hidden field: pretend success, store nothing.
        raise _Silent()


class _Silent(Exception):
    pass


def _find_or_create_customer(db: Session, full_name: str, phone: str | None, email: str | None, contact: ContactMethod) -> tuple[Customer, bool]:
    conds = []
    pk = phone_key(phone)
    if pk:
        conds.append(Customer.phone_key == pk)
    if email:
        conds.append(func.lower(Customer.email) == email.lower())
    existing = db.scalars(select(Customer).where(or_(*conds), Customer.is_archived.is_(False)).order_by(Customer.created_at)).first() if conds else None
    if existing:
        return existing, False
    c = Customer(reference=next_reference(db, "CLI"), full_name=full_name.strip(), phone=phone, phone_key=pk, email=email,
                 preferred_contact=contact, source=CustomerSource.WEBSITE)
    db.add(c)
    db.flush()
    return c, True


@router.post("/requests", status_code=201)
def public_request(data: PublicRequestIn, request: Request, cfg: dict = Depends(site_enabled), db: Session = Depends(get_db)):
    try:
        _guard(db, request, data)
    except _Silent:
        return {"detail": "Merci ! Votre demande a bien été enregistrée.", "reference": None}
    validate_category(db, data.property_type)
    feats = validate_features(db, data.features)
    customer, created = _find_or_create_customer(db, data.full_name, data.phone, data.email, data.preferred_contact)
    req = CustomerRequest(
        reference=next_reference(db, "DEM"), customer_id=customer.id, property_type=data.property_type,
        transaction_type=data.transaction_type, budget_min=data.budget_min, budget_max=data.budget_max,
        city=data.city.strip(), city_key=normalize_key(data.city), neighborhood=(data.neighborhood or "").strip() or None,
        neighborhood_key=normalize_key(data.neighborhood), surface_min=data.surface_min, bedrooms_min=data.bedrooms_min,
        preferred_features=feats, comments=data.comments, source=CustomerSource.WEBSITE, status=RequestStatus.NEW,
        currency=get_setting(db, "agency")["default_currency"],
    )
    db.add(req)
    db.flush()
    stats = matching.refresh_for_request(db, req)
    note = "Demande reçue via le site web." + ("" if created else f" Client existant reconnu ({customer.reference}) : vérifier les coordonnées saisies.")
    db.add(Activity(type=ActivityType.WEB_CONTACT, summary=note, customer_id=customer.id, request_id=req.id))
    notify(
        db, users_with_permission(db, "requests.assign"), type="request_new",
        title=f"Nouvelle demande web {req.reference} — {data.full_name}",
        body=f"{req.property_type} · {req.city} · {stats['active']} bien(s) correspondant(s)",
        link=f"/app/requests/{req.id}", entity_type="request", entity_id=req.id, dedupe_key=f"request_new:{req.id}",
    )
    audit.log(db, user_id=None, action="public_request", entity_type="request", entity_id=req.id, label=req.reference, ip=client_ip(request))
    db.commit()
    return {"detail": "Merci ! Votre demande a bien été enregistrée. Un conseiller vous contactera rapidement.", "reference": req.reference}


@router.post("/contact", status_code=201)
def public_contact(data: PublicContactIn, request: Request, cfg: dict = Depends(site_enabled), db: Session = Depends(get_db)):
    try:
        _guard(db, request, data)
    except _Silent:
        return {"detail": "Merci, votre message a bien été envoyé."}
    prop = None
    if data.property_reference:
        prop = db.scalars(select(Property).where(Property.reference == data.property_reference, *_visible())).first()
    customer, _ = _find_or_create_customer(db, data.full_name, data.phone, data.email,
                                           ContactMethod.PHONE if data.phone else ContactMethod.EMAIL)
    summary = f"Message du site web ({data.full_name}, {data.phone or ''} {data.email or ''}) : {data.message}"
    a = Activity(id=uuid.uuid4(), type=ActivityType.WEB_CONTACT, summary=summary, customer_id=customer.id, property_id=prop.id if prop else None)
    db.add(a)
    recipients = set(users_with_permission(db, "requests.assign"))
    if prop and prop.responsible_id:
        recipients.add(prop.responsible_id)
    notify(
        db, recipients, type="web_contact",
        title=f"Message du site web — {data.full_name}" + (f" ({prop.reference})" if prop else ""),
        body=data.message[:200], link=f"/app/customers/{customer.id}", entity_type="customer", entity_id=customer.id,
        dedupe_key=f"web_contact:{a.id}",
    )
    audit.log(db, user_id=None, action="public_contact", entity_type="customer", entity_id=customer.id, label=customer.reference, ip=client_ip(request))
    db.commit()
    return {"detail": "Merci, votre message a bien été envoyé. Nous vous répondrons rapidement."}
