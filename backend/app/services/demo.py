"""DEVELOPMENT ONLY sample data. Passwords are random and printed once; nothing is hardcoded."""

import random
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.security import generate_temp_password, hash_password
from app.models import Customer, CustomerRequest, Owner, Property, Role, User
from app.models.enums import CustomerSource, Priority, PropertyStatus, RequestStatus, TransactionType
from app.services import matching
from app.services.references import next_reference
from app.services.text import normalize_key, phone_key

CITIES = {
    "Rabat": ["Agdal", "Hay Riad", "Souissi", "Hassan", "Océan"],
    "Casablanca": ["Maârif", "Gauthier", "Ain Diab", "Bourgogne", "Californie"],
    "Marrakech": ["Guéliz", "Hivernage", "Palmeraie", "Targa"],
    "Tanger": ["Malabata", "Centre-ville", "Iberia"],
}
FIRST = ["Yassine", "Salma", "Karim", "Nadia", "Omar", "Imane", "Mehdi", "Sara", "Hamza", "Leila", "Rachid", "Amal", "Youssef", "Hiba"]
LAST = ["Benali", "El Idrissi", "Alaoui", "Berrada", "Tazi", "Chraibi", "Bennani", "Fassi", "Lahlou", "Kettani"]


def seed_demo(db: Session) -> str:
    if db.scalar(select(Property).limit(1)) is not None:
        return "Des biens existent déjà : données de démonstration non ajoutées."
    rnd = random.Random(42)
    agent_role = db.scalar(select(Role).where(Role.code == "commercial_agent"))
    manager_role = db.scalar(select(Role).where(Role.code == "sales_manager"))
    pm_role = db.scalar(select(Role).where(Role.code == "property_manager"))
    creds = []
    staff = []
    for email, name, role in [
        ("agent1@example.com", "Amine Agent", agent_role),
        ("agent2@example.com", "Sofia Agent", agent_role),
        ("manager@example.com", "Mounir Manager", manager_role),
        ("biens@example.com", "Fatima Gestion", pm_role),
    ]:
        if db.scalar(select(User).where(User.email == email)):
            continue
        pwd = generate_temp_password()
        u = User(email=email, full_name=name, role_id=role.id, password_hash=hash_password(pwd),
                 is_agent=role.code != "property_manager", must_change_password=False)
        db.add(u)
        staff.append(u)
        creds.append(f"  {email} / {pwd}  ({role.name})")
    db.flush()
    agents = [u for u in staff if u.is_agent]

    owners = [Owner(full_name=f"{rnd.choice(FIRST)} {rnd.choice(LAST)}", phone=f"06{rnd.randint(10000000, 99999999)}") for _ in range(8)]
    db.add_all(owners)
    db.flush()

    props = []
    for _ in range(30):
        city = rnd.choice(list(CITIES))
        nb = rnd.choice(CITIES[city])
        ptype = rnd.choices(["apartment", "villa", "house", "land", "commercial"], [6, 2, 2, 1, 1])[0]
        tx = rnd.choices([TransactionType.SALE, TransactionType.RENT], [3, 2])[0]
        surface = Decimal(rnd.choice([55, 70, 85, 100, 120, 150, 200, 300, 450]))
        if tx == TransactionType.SALE:
            price = Decimal(int(surface * rnd.randint(9000, 16000) / 1000) * 1000)
        else:
            price = Decimal(int(surface * rnd.randint(60, 120) / 100) * 100)
        rooms = ptype in ("apartment", "villa", "house")
        feats = sorted(rnd.sample(["parking", "elevator", "terrace", "garden", "pool", "furnished", "air_conditioning", "balcony"], rnd.randint(0, 4)))
        p = Property(
            reference=next_reference(db, "BIEN"), property_type=ptype, transaction_type=tx,
            title=f"{ {'apartment': 'Appartement', 'villa': 'Villa', 'house': 'Maison', 'land': 'Terrain', 'commercial': 'Local commercial'}[ptype]} {int(surface)} m² — {nb}",
            description="Bien de démonstration.", city=city, city_key=normalize_key(city), neighborhood=nb, neighborhood_key=normalize_key(nb),
            address=f"{rnd.randint(1, 200)} rue de démonstration", surface=surface, price=price,
            bedrooms=rnd.randint(1, 5) if rooms else None, bathrooms=rnd.randint(1, 3) if rooms else None,
            floor=rnd.randint(0, 8) if ptype == "apartment" else None, features=feats,
            status=rnd.choices([PropertyStatus.AVAILABLE, PropertyStatus.SOLD, PropertyStatus.RENTED, PropertyStatus.UNAVAILABLE], [8, 1, 1, 1])[0],
            is_published=rnd.random() < 0.6, owner=rnd.choice(owners), responsible_id=rnd.choice(staff).id if staff else None,
        )
        db.add(p)
        props.append(p)
    db.flush()

    for i in range(16):
        name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
        phone = f"06{rnd.randint(10000000, 99999999)}"
        c = Customer(reference=next_reference(db, "CLI"), full_name=name, phone=phone, phone_key=phone_key(phone),
                     email=f"client{i}@example.com", source=rnd.choice(list(CustomerSource)))
        db.add(c)
        db.flush()
        city = rnd.choice(list(CITIES))
        tx = rnd.choice([TransactionType.SALE, TransactionType.RENT])
        bmax = Decimal(rnd.choice([900000, 1200000, 1800000, 2500000])) if tx == TransactionType.SALE else Decimal(rnd.choice([5000, 8000, 12000]))
        nb = rnd.choice(CITIES[city] + [None])
        agent = rnd.choice(agents + [None]) if agents else None
        r = CustomerRequest(
            reference=next_reference(db, "DEM"), customer_id=c.id, property_type=rnd.choices(["apartment", "villa", "house"], [5, 2, 1])[0],
            transaction_type=tx, budget_max=bmax, city=city, city_key=normalize_key(city), neighborhood=nb, neighborhood_key=normalize_key(nb),
            surface_min=Decimal(rnd.choice([60, 80, 100])), bedrooms_min=rnd.randint(1, 3),
            preferred_features=sorted(rnd.sample(["parking", "elevator", "terrace", "garden"], rnd.randint(0, 2))),
            priority=rnd.choice(list(Priority)), status=RequestStatus.TO_CONTACT if agent else RequestStatus.NEW,
            assigned_agent_id=agent.id if agent else None, assigned_at=utcnow() if agent else None,
            next_follow_up_at=utcnow() + timedelta(days=rnd.randint(-3, 7)), source=c.source,
        )
        r.created_at = utcnow() - timedelta(days=rnd.randint(0, 200))
        db.add(r)
        db.flush()
        matching.refresh_for_request(db, r)
    return "Données de démonstration créées. Comptes (mots de passe générés, affichés une seule fois) :\n" + "\n".join(creds)
