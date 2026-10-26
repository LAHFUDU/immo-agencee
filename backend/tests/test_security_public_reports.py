from sqlalchemy import select

from app.models import Customer, CustomerRequest
from app.services import rate_limit
from tests.conftest import request_payload


def test_unauthenticated_access_is_rejected(client_factory):
    anon = client_factory()
    for path in ("/api/requests", "/api/properties", "/api/customers", "/api/deals", "/api/dashboard", "/api/users", "/api/notifications"):
        assert anon.get(path).status_code == 401, path


def test_agent_cannot_read_confidential_property_data(admin, agent, make_property):
    prop = make_property()
    full = admin.get(f"/api/properties/{prop['id']}").json()
    assert full["address"] == "12 rue Secrète" and full["owner"]["full_name"] == "Propriétaire Privé"
    seen = agent.get(f"/api/properties/{prop['id']}").json()
    assert seen["address"] is None and seen["owner"] is None and seen["internal_notes"] is None
    assert seen["confidential_visible"] is False
    listing = agent.get("/api/properties").text
    assert "Secrète" not in listing and "Propriétaire Privé" not in listing and "confidentielle" not in listing
    assert agent.get("/api/owners").status_code == 403
    assert agent.patch(f"/api/properties/{prop['id']}", json={"address": "x"}).status_code == 403  # no edit permission at all
    # Search does not leak addresses either.
    assert agent.get("/api/search", params={"q": "Secrète"}).json()["properties"] == []
    # Confidential documents are hidden and not downloadable.
    pdf = b"%PDF-1.4\n%test\n"
    doc = admin.post(f"/api/properties/{prop['id']}/documents", files={"file": ("titre.pdf", pdf, "application/pdf")}, data={"is_confidential": "true"})
    assert doc.status_code == 201
    assert agent.get(f"/api/properties/{prop['id']}/documents").json() == []
    assert agent.get(f"/api/files/documents/{doc.json()['id']}").status_code == 404
    assert admin.get(f"/api/files/documents/{doc.json()['id']}").content == pdf
    # History hides confidential changes from users without the permission.
    admin.patch(f"/api/properties/{prop['id']}", json={"address": "Nouvelle adresse secrète"})
    assert "secrète" not in agent.get(f"/api/properties/{prop['id']}/history").text.lower()


def test_agent_cannot_access_other_agents_customers_through_api(agent, agent2, db):
    body = agent.post("/api/requests", json=request_payload()).json()["request"]
    cid, rid = body["customer"]["id"], body["id"]
    for path in (f"/api/customers/{cid}", f"/api/customers/{cid}/activities", f"/api/requests/{rid}", f"/api/requests/{rid}/matches",
                 f"/api/requests/{rid}/activities"):
        assert agent2.get(path).status_code == 404, path
    assert agent2.get("/api/customers").json()["total"] == 0
    assert agent2.get("/api/search", params={"q": body["customer"]["full_name"]}).json()["customers"] == []
    assert agent2.post(f"/api/customers/{cid}/activities", json={"type": "call", "summary": "x"}).status_code == 404
    assert agent2.post("/api/visits", json={"property_id": "00000000-0000-0000-0000-000000000000", "customer_id": cid,
                                            "scheduled_at": "2030-01-01T10:00:00Z"}).status_code in (404, 422)
    # Duplicate detection does not leak another agent's customer contact details.
    p = request_payload()
    p["customer"]["phone"] = body["customer"]["phone"]
    dup = agent2.post("/api/requests", json=p).json()["detail"]["duplicates"][0]
    assert dup["phone"] is None and dup["email"] is None


def test_manager_sees_everything_agent_sees_own(agent, client_factory):
    agent.post("/api/requests", json=request_payload())
    manager = client_factory("sales_manager")
    assert manager.get("/api/requests").json()["total"] == 1
    assert manager.get("/api/customers").json()["total"] == 1


def test_public_site_exposes_only_published_available_properties(admin, make_property, client_factory):
    pub = make_property(is_published=True, title="Publié")
    make_property(is_published=False, title="Privé")
    make_property(is_published=True, status="sold", title="Vendu")
    anon = client_factory()
    items = anon.get("/api/public/properties").json()["items"]
    assert [i["title"] for i in items] == ["Publié"]
    raw = anon.get(f"/api/public/properties/{pub['reference']}").json()
    for forbidden in ("address", "owner", "internal_notes", "responsible", "latitude", "id"):
        assert forbidden not in raw
    assert "Secrète" not in anon.get("/api/public/properties").text
    # Disabling the public website hides everything.
    admin.put("/api/settings/public_site", json={"value": {"enabled": False, "show_price": True}})
    assert anon.get("/api/public/properties").status_code == 404


def test_public_request_form_is_saved_and_protected(admin, client_factory, db):
    anon = client_factory()
    form = {"full_name": "Visiteur Web", "phone": "0677889900", "property_type": "apartment", "transaction_type": "rent",
            "city": "Rabat", "budget_max": "7000", "consent": True, "website": ""}
    r = anon.post("/api/public/requests", json=form)
    assert r.status_code == 201 and r.json()["reference"].startswith("DEM-")
    req = db.scalar(select(CustomerRequest).where(CustomerRequest.reference == r.json()["reference"]))
    assert req.source.value == "website" and req.status.value == "new"
    # honeypot: silently ignored
    before = db.query(CustomerRequest).count()
    assert anon.post("/api/public/requests", json={**form, "website": "http://spam"}).json()["reference"] is None
    assert db.query(CustomerRequest).count() == before
    # consent required, validation enforced
    assert anon.post("/api/public/requests", json={**form, "consent": False}).status_code == 422
    # same phone: customer re-used, no duplicate
    anon.post("/api/public/requests", json={**form, "city": "Salé"})
    assert db.query(Customer).count() == 1
    # admins are notified
    assert admin.get("/api/notifications/unread-count").json()["count"] >= 2
    # rate limiting
    rate_limit.ENABLED = True
    codes = [anon.post("/api/public/contact", json={"full_name": "X Y", "phone": "0600000000", "message": "Bonjour, infos ?", "consent": True}).status_code for _ in range(12)]
    assert 429 in codes


def test_dashboard_and_reports_use_real_data(admin, agent, make_property):
    empty = admin.get("/api/reports").json()
    assert empty["conversion"]["requests"] == 0 and empty["requests_per_month"] == []
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    agent.post("/api/requests", json=request_payload(city="Fès"))
    prop = make_property()
    deal = agent.post("/api/deals", json={"request_id": rid, "property_id": prop["id"]}).json()
    agent.post(f"/api/deals/{deal['id']}/win", json={"agreed_price": "1100000"})

    dash = admin.get("/api/dashboard").json()
    assert dash["requests"]["total"] == 2 and dash["requests"]["converted"] == 1 and dash["requests"]["waiting_no_match"] == 1
    assert dash["deals"]["won"] == 1 and dash["revenue"]["commission"] == "27500.00"
    rep = admin.get("/api/reports").json()
    assert rep["conversion"] == {"requests": 2, "converted": 1, "rate": 50.0}
    assert rep["waiting"]["count"] == 1 and rep["waiting"]["oldest"][0]["city"] == "Fès"
    me = next(a for a in rep["agents"] if a["agent_id"] == agent.user_id)
    assert me["deals_won"] == 1 and me["requests_converted"] == 1
    csv = admin.get("/api/reports/export", params={"report": "agents", "fmt": "csv"})
    assert csv.status_code == 200 and "Agent Un" in csv.text
    xlsx = admin.get("/api/requests/export", params={"fmt": "xlsx"})
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    # agent dashboard is scoped to their own data, without agency-wide revenue
    adash = agent.get("/api/dashboard").json()
    assert adash["scope"] == "mine" and "revenue" not in adash and "agents" not in adash


def test_export_neutralises_spreadsheet_formulas(admin):
    p = request_payload()
    p["customer"]["full_name"] = "=HYPERLINK(\"http://evil\")"
    admin.post("/api/requests", json=p)
    text = admin.get("/api/requests/export").text
    assert "'=HYPERLINK" in text


def test_reminder_jobs_notify_once(admin, agent, db):
    from app.services.jobs import run_all

    agent.post("/api/requests", json=request_payload(next_follow_up_at="2020-01-01T09:00:00Z"))
    assert run_all(db)["follow_ups"] == 1
    assert run_all(db)["follow_ups"] == 0
    assert agent.get("/api/notifications", params={"unread": True}).json()["items"][0]["type"] == "follow_up_overdue"
