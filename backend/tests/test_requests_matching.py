from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import func, select

from app.models import CustomerRequest, Match, Notification
from app.models.enums import MatchCategory, PropertyStatus, TransactionType
from app.services.app_settings import DEFAULTS
from app.services.matching import evaluate
from tests.conftest import request_payload


def _notifs(db, user_id, type_="match_found"):
    return db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.type == type_))


# ------------------------------------------------------------------ requests


def test_agent_creates_and_updates_own_request(agent, agent2):
    r = agent.post("/api/requests", json=request_payload())
    assert r.status_code == 201, r.text
    req = r.json()["request"]
    assert req["reference"].startswith("DEM-")
    assert req["assigned_agent"]["id"] == agent.user_id  # agents keep the requests they create
    rid = req["id"]

    r = agent.patch(f"/api/requests/{rid}", json={"status": "contacted", "priority": "high", "budget_max": "1300000"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "contacted" and r.json()["priority"] == "high"
    assert r.json()["first_contacted_at"] is not None

    acts = agent.get(f"/api/requests/{rid}/activities").json()
    assert any(a["type"] == "status_change" for a in acts)
    # Another agent cannot see or modify it (reported as not found).
    assert agent2.get(f"/api/requests/{rid}").status_code == 404
    assert agent2.patch(f"/api/requests/{rid}", json={"priority": "low"}).status_code == 404
    # Agents without the archive permission cannot archive.
    assert agent.patch(f"/api/requests/{rid}", json={"status": "archived"}).status_code == 403
    assert agent.patch(f"/api/requests/{rid}", json={"status": "closed_lost"}).status_code == 422  # reason required


def test_request_saved_even_without_matching_property(admin, db):
    r = admin.post("/api/requests", json=request_payload(city="Ifrane", neighborhood="Centre"))
    assert r.status_code == 201
    body = r.json()
    assert body["match_count"] == 0
    assert "liste d'attente" in body["message"]
    rid = body["request"]["id"]
    assert db.get(CustomerRequest, rid) is not None
    waiting = admin.get("/api/requests", params={"waiting": "true"}).json()
    assert [w["id"] for w in waiting["items"]] == [rid]
    assert admin.get("/api/requests-waiting/stats").json() == {"waiting": 1, "waiting_unassigned": 1}


def test_validation_rejects_inconsistent_request(admin):
    r = admin.post("/api/requests", json=request_payload(budget_min="2000000", budget_max="1000000"))
    assert r.status_code == 422
    assert "budget" in r.json()["detail"].lower()
    assert admin.post("/api/requests", json=request_payload(property_type="spaceship")).status_code == 422


def test_duplicate_customer_detected(admin):
    p = request_payload()
    p["customer"]["phone"] = "06 12 34 56 78"
    assert admin.post("/api/requests", json=p).status_code == 201
    p2 = request_payload()
    p2["customer"]["phone"] = "+212612345678"  # same number, international format
    r = admin.post("/api/requests", json=p2)
    assert r.status_code == 409
    dups = r.json()["detail"]["duplicates"]
    assert dups and dups[0]["reason"] == "Même téléphone"
    # Attach to the existing customer instead.
    p3 = request_payload(customer=None, customer_id=dups[0]["id"])
    assert admin.post("/api/requests", json=p3).status_code == 201


def test_assignment_notifies_agent(admin, agent, db):
    rid = admin.post("/api/requests", json=request_payload()).json()["request"]["id"]
    r = admin.post(f"/api/requests/{rid}/assign", json={"agent_id": agent.user_id})
    assert r.status_code == 200 and r.json()["status"] == "to_contact"
    assert _notifs(db, agent.user_id, "request_assigned") == 1
    assert agent.get(f"/api/requests/{rid}").status_code == 200
    assert agent.post(f"/api/requests/{rid}/assign", json={"agent_id": None}).status_code == 403


def test_agent_sees_and_claims_new_unassigned_requests(admin, agent):
    rid = admin.post("/api/requests", json=request_payload()).json()["request"]["id"]
    assert rid in [x["id"] for x in agent.get("/api/requests").json()["items"]]
    assert agent.post(f"/api/requests/{rid}/claim").json()["assigned_agent"]["id"] == agent.user_id


# ------------------------------------------------------------------ matching engine


def test_new_property_triggers_matching_and_notifies_agent(admin, agent, db, make_property):
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    assert agent.get(f"/api/requests/{rid}/matches").json() == []

    prop = make_property(price="1150000")
    matches = agent.get(f"/api/requests/{rid}/matches").json()
    assert len(matches) == 1
    m = matches[0]
    assert m["property_id"] == prop["id"] and m["category"] == "exact" and m["score"] == 100
    assert any("Quartier" in s for s in m["explanation"]["met"])
    assert _notifs(db, agent.user_id) == 1
    # No longer on the waiting list.
    assert agent.get("/api/requests", params={"waiting": "true"}).json()["total"] == 0


def test_over_budget_property_is_never_an_exact_match(admin, agent, make_property):
    rid = agent.post("/api/requests", json=request_payload(budget_max="1200000")).json()["request"]["id"]
    make_property(price="1250000")
    assert agent.get(f"/api/requests/{rid}/matches").json() == []
    near = agent.get(f"/api/requests/{rid}/matches", params={"include_near_misses": True}).json()
    assert len(near) == 1 and near[0]["category"] == "ineligible" and near[0]["is_active"] is False
    assert "budget maximum" in near[0]["explanation"]["failed"][0]

    # With a configured 10 % tolerance it is shown, but only as a partial match.
    s = admin.get("/api/settings").json()["matching"]
    s["budget_tolerance_percent"] = 10
    assert admin.put("/api/settings/matching", json={"value": s}).status_code == 200
    m = agent.get(f"/api/requests/{rid}/matches").json()
    assert len(m) == 1 and m[0]["category"] == "partial"
    assert any("Dépasse le budget" in u for u in m[0]["explanation"]["unmet"])


def test_unavailable_properties_excluded_from_matches(admin, agent, make_property):
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    for st in ("sold", "rented", "unavailable", "reserved", "under_negotiation", "archived"):
        make_property(status=st)
    assert agent.get(f"/api/requests/{rid}/matches").json() == []
    avail = make_property()
    assert len(agent.get(f"/api/requests/{rid}/matches").json()) == 1
    # Selling it removes it from the available matches immediately.
    assert admin.post(f"/api/properties/{avail['id']}/status", json={"status": "sold"}).status_code == 200
    assert agent.get(f"/api/requests/{rid}/matches").json() == []
    hist = agent.get(f"/api/requests/{rid}/matches", params={"include_inactive": True}).json()
    assert len(hist) == 1 and hist[0]["is_active"] is False  # history kept


def test_no_duplicate_notifications_without_material_change(admin, agent, db, make_property):
    agent.post("/api/requests", json=request_payload())
    prop = make_property()
    assert _notifs(db, agent.user_id) == 1
    pid = prop["id"]
    # Non-material edits and re-saves do not re-notify.
    admin.patch(f"/api/properties/{pid}", json={"title": "Nouveau titre", "description": "Desc"})
    admin.patch(f"/api/properties/{pid}", json={"features": ["parking", "elevator", "balcony"]})
    admin.post(f"/api/properties/{pid}/status", json={"status": "unavailable"})
    admin.post(f"/api/properties/{pid}/status", json={"status": "available"})
    assert _notifs(db, agent.user_id) == 1
    # A material change (price) re-notifies once.
    admin.patch(f"/api/properties/{pid}", json={"price": "1100000"})
    assert _notifs(db, agent.user_id) == 2
    admin.patch(f"/api/properties/{pid}", json={"title": "Encore"})
    assert _notifs(db, agent.user_id) == 2
    # Explicit request from the agent.
    mid = db.scalar(select(Match.id))
    assert agent.post(f"/api/matches/{mid}/renotify").status_code == 200
    assert _notifs(db, agent.user_id) == 3


def test_request_change_rematches(agent, make_property):
    make_property(city="Casablanca", neighborhood="Maârif")
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    assert agent.get(f"/api/requests/{rid}/matches").json() == []
    agent.patch(f"/api/requests/{rid}", json={"city": "casablanca", "neighborhood": "maarif"})  # case/accent-insensitive
    assert len(agent.get(f"/api/requests/{rid}/matches").json()) == 1
    agent.patch(f"/api/requests/{rid}", json={"status": "closed_lost", "close_reason": "A acheté ailleurs"})
    assert agent.get(f"/api/requests/{rid}/matches").json() == []


def test_match_workflow_propose_reject(agent, db, make_property):
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    make_property()
    mid = agent.get(f"/api/requests/{rid}/matches").json()[0]["id"]
    r = agent.patch(f"/api/matches/{mid}", json={"status": "proposed", "customer_feedback": "Intéressé"})
    assert r.status_code == 200 and r.json()["status"] == "proposed"
    assert agent.get(f"/api/requests/{rid}").json()["status"] == "proposed"
    assert agent.patch(f"/api/matches/{mid}", json={"status": "rejected"}).status_code == 422
    r = agent.patch(f"/api/matches/{mid}", json={"status": "rejected", "rejection_reason": "Trop sombre"})
    assert r.json()["rejection_reason"] == "Trop sombre"


# ------------------------------------------------------------------ pure scoring rules


def _req(**kw):
    base = dict(transaction_type=TransactionType.SALE, property_type="apartment", city_key="rabat", currency="MAD",
                neighborhood="Agdal", budget_min=None, budget_max=Decimal("1200000"), surface_min=Decimal("90"), surface_max=None,
                bedrooms_min=2, bathrooms_min=None, required_features=[], preferred_features=[])
    base.update(kw)
    return SimpleNamespace(**base)


def _prop(**kw):
    base = dict(status=PropertyStatus.AVAILABLE, transaction_type=TransactionType.SALE, property_type="apartment", city="Rabat",
                city_key="rabat", currency="MAD", neighborhood="Agdal", neighborhood_key="agdal", price=Decimal("1150000"),
                surface=Decimal("110"), bedrooms=3, bathrooms=2, features=["parking"])
    base.update(kw)
    return SimpleNamespace(**base)


RULES = DEFAULTS["matching"]


def test_scoring_categories():
    assert evaluate(_req(), _prop(), RULES).category == MatchCategory.EXACT
    ev = evaluate(_req(preferred_features=["parking", "terrace"]), _prop(), RULES)
    assert ev.category == MatchCategory.STRONG and ev.score == 95 and any("Terrasse" in u or "terrace" in u for u in ev.unmet)
    ev = evaluate(_req(), _prop(neighborhood="Hassan", neighborhood_key="hassan"), RULES)
    assert ev.eligible and ev.category == MatchCategory.PARTIAL
    ev = evaluate(_req(required_features=["pool"]), _prop(), RULES)
    assert not ev.eligible and ev.category == MatchCategory.INELIGIBLE
    ev = evaluate(_req(), _prop(bedrooms=1), RULES)
    assert not ev.eligible
    ev = evaluate(_req(), _prop(surface=None), RULES)
    assert ev.eligible and ev.category != MatchCategory.EXACT  # unknown value is never "exact"
    ev = evaluate(_req(neighborhood="Agdal, Hay Riad"), _prop(neighborhood="Hay Riad", neighborhood_key="hay riad"), RULES)
    assert ev.category == MatchCategory.EXACT
    strict = {**RULES, "neighborhood_mandatory": True}
    assert not evaluate(_req(), _prop(neighborhood="Hassan", neighborhood_key="hassan"), strict).eligible
    assert not evaluate(_req(currency="EUR"), _prop(), RULES).eligible
