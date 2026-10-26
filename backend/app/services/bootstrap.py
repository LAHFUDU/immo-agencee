"""Idempotent reference data: permissions, default roles, property types, features, commission rules.

Safe to run on every deployment (`python -m app.cli init`). Never creates users or passwords.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import DEFAULT_ROLES, PERMISSIONS
from app.models import CommissionRule, Permission, PropertyCategory, PropertyFeature, Role
from app.models.enums import TransactionType

PROPERTY_TYPES = [
    ("apartment", "Appartement", True),
    ("house", "Maison", True),
    ("villa", "Villa", True),
    ("land", "Terrain", False),
    ("commercial", "Local commercial", False),
    ("office", "Bureau", False),
    ("other", "Autre", True),
]

FEATURES = [
    ("parking", "Parking"),
    ("garage", "Garage"),
    ("garden", "Jardin"),
    ("terrace", "Terrasse"),
    ("balcony", "Balcon"),
    ("elevator", "Ascenseur"),
    ("pool", "Piscine"),
    ("furnished", "Meublé"),
    ("air_conditioning", "Climatisation"),
    ("central_heating", "Chauffage central"),
    ("concierge", "Gardiennage / concierge"),
    ("sea_view", "Vue mer"),
    ("equipped_kitchen", "Cuisine équipée"),
    ("storage", "Cave / débarras"),
]


def seed_reference_data(db: Session, *, with_default_commissions: bool = True) -> None:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code, (module, label) in PERMISSIONS.items():
        if code in existing:
            existing[code].module, existing[code].label = module, label
        else:
            db.add(Permission(code=code, module=module, label=label))
    db.flush()
    perms = {p.code: p for p in db.scalars(select(Permission)).all()}

    for code, spec in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=spec["name"], description=spec["description"], is_system=True,
                        is_superadmin=spec["is_superadmin"])
            role.permissions = [perms[c] for c in spec["permissions"]]
            db.add(role)
        elif role.is_superadmin:
            role.permissions = list(perms.values())
        # Existing non-admin roles keep the administrator's customisations.

    for i, (code, label, rooms) in enumerate(PROPERTY_TYPES):
        if db.get(PropertyCategory, code) is None:
            db.add(PropertyCategory(code=code, label=label, has_rooms=rooms, sort_order=i))
    for i, (code, label) in enumerate(FEATURES):
        if db.get(PropertyFeature, code) is None:
            db.add(PropertyFeature(code=code, label=label, sort_order=i))
    db.flush()

    if with_default_commissions and db.scalar(select(CommissionRule).limit(1)) is None:
        # Starting points only — administrators are expected to adapt them in Settings.
        db.add(CommissionRule(name="Vente — taux standard", transaction_type=TransactionType.SALE, rate_percent=Decimal("2.5")))
        db.add(CommissionRule(name="Location — un mois de loyer", transaction_type=TransactionType.RENT, rate_percent=Decimal("100")))
    db.flush()
