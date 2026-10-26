"""Property <-> customer request matching engine.

Rules
-----
Mandatory criteria (any failure => category "ineligible", never stored as an active match):
  availability status, transaction type, property type, city, maximum budget (+ optional
  tolerance), minimum surface (+ optional tolerance), minimum bedrooms (configurable),
  required features, currency, and neighbourhood when configured as mandatory.

Optional preferences add up to 50 points on top of the 50 points granted when every
mandatory criterion passes: neighbourhood, price within [min, max], surface within
[min, max], bathrooms, preferred features (weights configurable).

Categories
  exact   : score 100 and nothing unmet
  strong  : score >= strong_threshold (default 75), at most one kind of minor gap
  partial : everything else that passes the mandatory criteria
A property is never "exact" if any preference is unmet or any value is unknown, and a property
over budget can never be better than "partial" (and is excluded entirely when tolerance is 0).
"""

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import CustomerRequest, Match, Property, PropertyFeature
from app.models.enums import (
    CATEGORY_RANK,
    CLOSED_REQUEST_STATUSES,
    OPEN_REQUEST_STATUSES,
    MatchCategory,
    PropertyStatus,
)
from app.services.app_settings import get_setting
from app.services.notifications import notify, users_with_permission
from app.services.text import normalize_key

STATUS_LABELS = {
    "available": "Disponible",
    "reserved": "Réservé",
    "under_negotiation": "En négociation",
    "sold": "Vendu",
    "rented": "Loué",
    "unavailable": "Indisponible",
    "archived": "Archivé",
}


def fmt_money(v: Decimal | None, currency: str = "MAD") -> str:
    if v is None:
        return "—"
    return f"{int(v):,}".replace(",", " ") + f" {currency}"


def neighborhood_keys(value: str | None) -> list[str]:
    """A request may list several acceptable neighbourhoods: 'Agdal, Hay Riad / Souissi'."""
    if not value:
        return []
    return [k for k in (normalize_key(p) for p in re.split(r"[,;/|]", value)) if k]


@dataclass
class Evaluation:
    eligible: bool
    score: int
    category: MatchCategory
    met: list[str] = field(default_factory=list)
    unmet: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def explanation(self) -> dict:
        return {"met": self.met, "unmet": self.unmet, "failed": self.failed}


def _cap(current: MatchCategory, cap: MatchCategory) -> MatchCategory:
    return current if CATEGORY_RANK[current] <= CATEGORY_RANK[cap] else cap


def evaluate(req: CustomerRequest, prop: Property, rules: dict, feature_labels: dict[str, str] | None = None) -> Evaluation:
    labels = feature_labels or {}
    w = rules["weights"]
    met: list[str] = []
    unmet: list[str] = []
    failed: list[str] = []
    cap = MatchCategory.EXACT
    points = 0

    # --- Mandatory criteria -------------------------------------------------------------
    status = prop.status.value if hasattr(prop.status, "value") else prop.status
    if status not in rules["eligible_statuses"]:
        failed.append(f"Bien non disponible (statut : {STATUS_LABELS.get(status, status)})")
    if prop.transaction_type != req.transaction_type:
        failed.append("Type de transaction différent (vente / location)")
    if prop.property_type != req.property_type:
        failed.append(f"Type de bien différent ({prop.property_type} au lieu de {req.property_type})")
    else:
        met.append("Type de bien conforme")
    if prop.city_key != req.city_key:
        failed.append(f"Ville différente ({prop.city})")
    else:
        met.append(f"Ville : {prop.city}")
    if (prop.currency or "MAD") != (req.currency or "MAD"):
        failed.append(f"Devise différente ({prop.currency} / {req.currency})")

    # Neighbourhood
    wanted = neighborhood_keys(req.neighborhood)
    if wanted:
        if prop.neighborhood_key and prop.neighborhood_key in wanted:
            met.append(f"Quartier : {prop.neighborhood}")
            points += w["neighborhood"]
        elif rules["neighborhood_mandatory"]:
            failed.append(f"Quartier différent ({prop.neighborhood or 'non renseigné'})")
        else:
            unmet.append(f"Quartier différent : {prop.neighborhood or 'non renseigné'} (souhaité : {req.neighborhood})")
            cap = _cap(cap, MatchCategory.PARTIAL)
    else:
        points += w["neighborhood"]

    # Budget
    price = Decimal(prop.price)
    if req.budget_max is not None and price > req.budget_max:
        tol = Decimal(str(rules["budget_tolerance_percent"])) / 100
        over_pct = (price - req.budget_max) / req.budget_max * 100 if req.budget_max > 0 else Decimal(100)
        if tol > 0 and price <= req.budget_max * (1 + tol):
            unmet.append(f"Dépasse le budget de {over_pct:.1f} % ({fmt_money(price, prop.currency)} > {fmt_money(req.budget_max, req.currency)})")
            cap = _cap(cap, MatchCategory.PARTIAL)
        else:
            failed.append(f"Prix {fmt_money(price, prop.currency)} au-dessus du budget maximum {fmt_money(req.budget_max, req.currency)}")
    elif req.budget_min is not None and price < req.budget_min:
        unmet.append(f"Prix inférieur au budget minimum ({fmt_money(price, prop.currency)})")
        points += w["price_fit"] // 2
    else:
        met.append(f"Prix dans le budget : {fmt_money(price, prop.currency)}")
        points += w["price_fit"]

    # Surface
    surface = Decimal(prop.surface) if prop.surface is not None else None
    surface_ok = True
    if req.surface_min is not None:
        if surface is None:
            unmet.append("Surface non renseignée")
            cap = _cap(cap, MatchCategory.STRONG)
            surface_ok = False
        elif surface < req.surface_min:
            tol = Decimal(str(rules["surface_tolerance_percent"])) / 100
            if tol > 0 and surface >= req.surface_min * (1 - tol):
                unmet.append(f"Surface légèrement inférieure : {surface:g} m² (min. {req.surface_min:g} m²)")
                cap = _cap(cap, MatchCategory.PARTIAL)
                surface_ok = False
            else:
                failed.append(f"Surface {surface:g} m² inférieure au minimum {req.surface_min:g} m²")
                surface_ok = False
    if req.surface_max is not None and surface is not None and surface > req.surface_max:
        unmet.append(f"Surface supérieure au maximum souhaité ({surface:g} m²)")
        surface_ok = False
    if surface_ok:
        if surface is not None and (req.surface_min is not None or req.surface_max is not None):
            met.append(f"Surface : {surface:g} m²")
        points += w["surface_fit"]

    # Bedrooms
    if req.bedrooms_min:
        if prop.bedrooms is None:
            unmet.append("Nombre de chambres non renseigné")
            cap = _cap(cap, MatchCategory.STRONG)
        elif prop.bedrooms < req.bedrooms_min:
            msg = f"{prop.bedrooms} chambre(s) au lieu de {req.bedrooms_min} minimum"
            if rules["bedrooms_mandatory"]:
                failed.append(msg)
            else:
                unmet.append(msg)
                cap = _cap(cap, MatchCategory.PARTIAL)
        else:
            met.append(f"{prop.bedrooms} chambre(s)")

    # Bathrooms (preference)
    if req.bathrooms_min:
        if prop.bathrooms is not None and prop.bathrooms >= req.bathrooms_min:
            met.append(f"{prop.bathrooms} salle(s) de bain")
            points += w["bathrooms"]
        else:
            unmet.append(f"Salles de bain : {prop.bathrooms if prop.bathrooms is not None else 'non renseigné'} (souhaité : {req.bathrooms_min})")
    else:
        points += w["bathrooms"]

    # Features
    have = set(prop.features or [])
    for f in req.required_features or []:
        if f in have:
            met.append(f"Équipement requis : {labels.get(f, f)}")
        else:
            failed.append(f"Équipement obligatoire manquant : {labels.get(f, f)}")
    preferred = [f for f in (req.preferred_features or []) if f not in (req.required_features or [])]
    if preferred:
        present = [f for f in preferred if f in have]
        missing = [f for f in preferred if f not in have]
        points += round(w["preferred_features"] * len(present) / len(preferred))
        if present:
            met.append("Souhaits satisfaits : " + ", ".join(labels.get(f, f) for f in present))
        if missing:
            unmet.append("Souhaits non satisfaits : " + ", ".join(labels.get(f, f) for f in missing))
    else:
        points += w["preferred_features"]

    score = max(0, min(100, 50 + points))
    if failed:
        return Evaluation(False, min(score, 49), MatchCategory.INELIGIBLE, met, unmet, failed)

    if score >= 100 and not unmet:
        category = MatchCategory.EXACT
    elif score >= int(rules["strong_threshold"]):
        category = MatchCategory.STRONG
    else:
        category = MatchCategory.PARTIAL
    if unmet:
        cap = _cap(cap, MatchCategory.STRONG)
    return Evaluation(True, score, _cap(category, cap), met, unmet, failed)


def signature(ev: Evaluation, prop: Property) -> str:
    """Material state of a match. Re-notification only happens when this changes."""
    return f"{ev.category.value}|{Decimal(prop.price):.2f}"


def feature_labels(db: Session) -> dict[str, str]:
    return {f.code: f.label for f in db.scalars(select(PropertyFeature)).all()}


def _upsert(db: Session, req: CustomerRequest, prop: Property, ev: Evaluation, existing: Match | None) -> Match | None:
    now = utcnow()
    if not ev.eligible:
        if existing is not None:
            existing.is_active = False
            existing.score = ev.score
            existing.category = ev.category
            existing.explanation = ev.explanation()
            existing.computed_at = now
        return existing
    if existing is None:
        existing = Match(
            id=uuid.uuid4(),
            request_id=req.id,
            property_id=prop.id,
            score=ev.score,
            category=ev.category,
            explanation=ev.explanation(),
            is_active=True,
            computed_at=now,
        )
        db.add(existing)
    else:
        existing.score = ev.score
        existing.category = ev.category
        existing.explanation = ev.explanation()
        existing.is_active = True
        existing.computed_at = now
    return existing


def _should_notify(ev: Evaluation, rules: dict) -> bool:
    threshold = MatchCategory(rules["notify_min_category"])
    return ev.eligible and CATEGORY_RANK[ev.category] >= CATEGORY_RANK[threshold]


def notify_match(db: Session, match: Match, req: CustomerRequest, prop: Property, force: bool = False) -> bool:
    """Notify the request's agent (or the assigners if unassigned). Deduplicated by signature."""
    sig = f"{match.category.value}|{Decimal(prop.price):.2f}"
    if not force and match.notified_signature == sig:
        return False
    recipients = [req.assigned_agent_id] if req.assigned_agent_id else users_with_permission(db, "requests.assign")
    label = {"exact": "Correspondance exacte", "strong": "Forte correspondance", "partial": "Correspondance partielle"}[
        match.category.value
    ]
    key = f"match:{match.id}:{sig}" + (f":manual:{utcnow().timestamp()}" if force else "")
    notify(
        db,
        recipients,
        type="match_found",
        title=f"{label} ({match.score}/100) pour {req.reference} — {req.customer.full_name}",
        body=f"{prop.reference} · {prop.title} · {prop.city}{' / ' + prop.neighborhood if prop.neighborhood else ''} · {fmt_money(prop.price, prop.currency)}",
        link=f"/app/requests/{req.id}",
        entity_type="match",
        entity_id=match.id,
        dedupe_key=key,
    )
    match.notified_signature = sig
    match.notified_at = utcnow()
    return True


def refresh_for_property(db: Session, prop: Property, *, notify_agents: bool = True) -> dict:
    """Re-evaluate one property against every open request that could match it.
    Called whenever a property is created or any of its details/status change."""
    db.flush()
    rules = get_setting(db, "matching")
    labels = feature_labels(db)
    existing = {m.request_id: m for m in db.scalars(select(Match).where(Match.property_id == prop.id)).all()}
    stats = {"evaluated": 0, "active": 0, "notified": 0}

    status = prop.status.value if hasattr(prop.status, "value") else prop.status
    if status not in rules["eligible_statuses"]:
        for m in existing.values():
            if m.is_active:
                m.is_active = False
                m.computed_at = utcnow()
        db.flush()
        return stats

    candidates = db.scalars(
        select(CustomerRequest).where(
            CustomerRequest.status.in_(OPEN_REQUEST_STATUSES),
            CustomerRequest.transaction_type == prop.transaction_type,
            CustomerRequest.property_type == prop.property_type,
            CustomerRequest.city_key == prop.city_key,
        )
    ).all()
    seen = set()
    for req in candidates:
        seen.add(req.id)
        ev = evaluate(req, prop, rules, labels)
        stats["evaluated"] += 1
        m = _upsert(db, req, prop, ev, existing.get(req.id))
        if ev.eligible:
            stats["active"] += 1
            if notify_agents and _should_notify(ev, rules):
                db.flush()
                if notify_match(db, m, req, prop):
                    stats["notified"] += 1
    # Requests that matched before but are no longer candidates (criteria changed, closed...).
    for req_id, m in existing.items():
        if req_id not in seen and m.is_active:
            m.is_active = False
            m.computed_at = utcnow()
    db.flush()
    return stats


def refresh_for_request(db: Session, req: CustomerRequest) -> dict:
    """Re-evaluate one request against the inventory. Matches found here are visible to the
    user who is working on the request, so they are marked as surfaced without a notification."""
    db.flush()
    rules = get_setting(db, "matching")
    labels = feature_labels(db)
    existing = {m.property_id: m for m in db.scalars(select(Match).where(Match.request_id == req.id)).all()}
    stats = {"evaluated": 0, "active": 0}

    if req.status in CLOSED_REQUEST_STATUSES:
        for m in existing.values():
            m.is_active = False
        db.flush()
        return stats

    candidates = db.scalars(
        select(Property).where(
            Property.status.in_([PropertyStatus(s) for s in rules["eligible_statuses"]]),
            Property.transaction_type == req.transaction_type,
            Property.property_type == req.property_type,
            Property.city_key == req.city_key,
        )
    ).all()
    seen = set()
    for prop in candidates:
        seen.add(prop.id)
        ev = evaluate(req, prop, rules, labels)
        stats["evaluated"] += 1
        m = _upsert(db, req, prop, ev, existing.get(prop.id))
        if ev.eligible:
            stats["active"] += 1
            if _should_notify(ev, rules):
                m.notified_signature = signature(ev, prop)
    for prop_id, m in existing.items():
        if prop_id not in seen and m.is_active:
            m.is_active = False
    db.flush()
    return stats


def near_misses(db: Session, req: CustomerRequest, limit: int = 10) -> list[tuple[Property, Evaluation]]:
    """Properties of the same type/transaction/city that fail a mandatory criterion
    (e.g. over budget) — shown separately and clearly labelled as non-conforming."""
    rules = get_setting(db, "matching")
    labels = feature_labels(db)
    props = db.scalars(
        select(Property).where(
            Property.status.in_([PropertyStatus(s) for s in rules["eligible_statuses"]]),
            Property.transaction_type == req.transaction_type,
            Property.property_type == req.property_type,
            Property.city_key == req.city_key,
        )
    ).all()
    out = []
    for p in props:
        ev = evaluate(req, p, rules, labels)
        if not ev.eligible:
            out.append((p, ev))
    out.sort(key=lambda t: (len(t[1].failed), -t[1].score))
    return out[:limit]


def has_active_match():
    return exists().where(Match.request_id == CustomerRequest.id, Match.is_active.is_(True))
