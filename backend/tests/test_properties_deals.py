import io

from openpyxl import Workbook
from sqlalchemy import select

from app.models import Activity, AuditLog, Deal
from tests.conftest import request_payload

CSV_HEADER = "reference;type;transaction;titre;ville;quartier;surface;prix;chambres;equipements;statut\n"


def test_property_status_change_reflected_everywhere(admin, agent, make_property, client_factory):
    prop = make_property(is_published=True)
    pid = prop["id"]
    anon = client_factory()
    assert anon.get(f"/api/public/properties/{prop['reference']}").status_code == 200
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    assert len(agent.get(f"/api/requests/{rid}/matches").json()) == 1
    before = admin.get("/api/dashboard").json()["properties"]

    r = admin.post(f"/api/properties/{pid}/status", json={"status": "rented", "reason": "Test"})
    assert r.status_code == 200 and r.json()["status"] == "rented"

    assert admin.get(f"/api/properties/{pid}").json()["status"] == "rented"
    assert pid not in [p["id"] for p in admin.get("/api/properties", params={"status": "available"}).json()["items"]]
    assert pid in [p["id"] for p in admin.get("/api/properties", params={"status": "rented"}).json()["items"]]
    assert anon.get(f"/api/public/properties/{prop['reference']}").status_code == 404
    assert anon.get("/api/public/properties").json()["total"] == 0
    assert agent.get(f"/api/requests/{rid}/matches").json() == []
    after = admin.get("/api/dashboard").json()["properties"]
    assert after["available"] == before["available"] - 1 and after["sold_or_rented"] == before["sold_or_rented"] + 1
    hist = admin.get(f"/api/properties/{pid}/history").json()
    assert hist[0]["action"] == "status_change" and hist[0]["changes"]["status"] == {"old": "available", "new": "rented"}


def test_bulk_status_update(admin, make_property):
    ids = [make_property(price=str(1000000 + i))["id"] for i in range(3)]
    r = admin.post("/api/properties/bulk-status", json={"ids": ids, "status": "unavailable"})
    assert r.json()["updated"] == 3
    assert admin.get("/api/properties", params={"status": "unavailable"}).json()["total"] == 3


def test_csv_import_validates_and_reports_errors(admin, agent):
    agent.post("/api/requests", json=request_payload())
    csv = CSV_HEADER + (
        ";apartment;vente;Appartement A;Rabat;Agdal;120;1150000;3;parking,elevator;disponible\n"
        ";villa;location;Villa B;Marrakech;Guéliz;300;25000;4;jacuzzi;\n"            # unknown feature label
        ";castle;vente;Château;Rabat;;500;abc;2;;\n"                                 # unknown type + bad price
        ";apartment;vente;Appartement A bis;Rabat;Agdal;120;1150000;3;;\n"           # duplicate of row 2
        ";apartment;achat;;Rabat;;80;900000;2;;inconnu\n"                            # missing title + bad status
    )
    files = {"file": ("biens.csv", csv.encode("utf-8"), "text/csv")}
    r = admin.post("/api/properties/import", files=files, data={"dry_run": "true"})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["total_rows"] == 5 and rep["valid_rows"] == 1 and rep["imported"] == 0, rep
    fields = {(e["row"], e["field"]) for e in rep["errors"]}
    assert (3, "equipements") in fields and (4, "type") in fields and (4, "prix") in fields
    assert (6, "titre") in fields and (6, "statut") in fields
    assert rep["duplicates"][0]["row"] == 5
    assert admin.get("/api/properties").json()["total"] == 0  # dry run wrote nothing

    rep = admin.post("/api/properties/import", files=files, data={"dry_run": "false"}).json()
    assert rep["imported"] == 1
    assert admin.get("/api/properties").json()["total"] == 1
    # imported properties are matched like any other
    assert admin.get("/api/matches").json()["total"] == 1
    # re-importing the same file detects the existing property
    rep = admin.post("/api/properties/import", files=files, data={"dry_run": "true"}).json()
    assert any("Doublon probable du bien" in d["reason"] for d in rep["duplicates"])


def test_xlsx_import(admin):
    wb = Workbook()
    ws = wb.active
    ws.append(["type", "transaction", "titre", "ville", "prix", "surface", "equipements"])
    ws.append(["Appartement", "location", "Studio meublé", "Tanger", 4500, 40, "Meublé, Climatisation"])
    buf = io.BytesIO()
    wb.save(buf)
    files = {"file": ("biens.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    rep = admin.post("/api/properties/import", files=files, data={"dry_run": "false"}).json()
    assert rep["imported"] == 1, rep
    p = admin.get("/api/properties").json()["items"][0]
    assert p["features"] == ["air_conditioning", "furnished"] and p["transaction_type"] == "rent"


def test_import_and_upload_form_defaults_are_safe(admin, agent, make_property):
    csv = CSV_HEADER + ";apartment;vente;Appartement Z;Rabat;Agdal;120;1150000;3;;\n"
    rep = admin.post("/api/properties/import", files={"file": ("b.csv", csv.encode(), "text/csv")}).json()
    assert rep["dry_run"] is True and admin.get("/api/properties").json()["total"] == 0  # no flag => simulation only
    pid = make_property()["id"]
    admin.post(f"/api/properties/{pid}/documents", files={"file": ("acte.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert agent.get(f"/api/properties/{pid}/documents").json() == []  # no flag => confidential


def test_import_rejects_unknown_format(admin):
    r = admin.post("/api/properties/import", files={"file": ("x.txt", b"hello", "text/plain")}, data={"dry_run": "true"})
    assert r.status_code == 422


def test_combined_property_filters(admin, make_property):
    make_property(title="Bien A", city="Rabat", neighborhood="Agdal", price="900000", surface="80", bedrooms=2, features=["parking"])
    make_property(title="Bien B", city="Rabat", neighborhood="Agdal", price="1500000", surface="150", bedrooms=4, features=["parking", "pool"])
    make_property(title="Bien C", city="Rabat", neighborhood="Souissi", price="1400000", surface="140", bedrooms=4, features=["pool"])
    make_property(title="Bien D", city="Casablanca", neighborhood="Agdal", price="1450000", surface="160", bedrooms=4, features=["parking", "pool"], transaction_type="rent")
    q = lambda **p: [x["title"][-1] for x in admin.get("/api/properties", params=p).json()["items"]]  # noqa: E731
    assert sorted(q(city="rabat")) == ["A", "B", "C"]
    assert q(city="Rabat", neighborhood="Agdal", price_min=1000000) == ["B"]
    assert sorted(q(price_min=1000000, surface_min=145)) == ["B", "D"]
    assert q(features="parking,pool", transaction_type="sale") == ["B"]
    assert sorted(q(bedrooms_min=3, price_max=1450000)) == ["C", "D"]
    assert q(q="Souissi") == ["C"]
    assert q(city="Rabat", sort="price", order="asc") == ["A", "C", "B"]
    page = admin.get("/api/properties", params={"page_size": 2, "page": 2, "sort": "price", "order": "asc"}).json()
    assert page["total"] == 4 and [x["title"][-1] for x in page["items"]] == ["D", "B"]


def test_combined_request_filters(admin, agent):
    admin.post("/api/requests", json=request_payload(city="Rabat", priority="high", budget_max="1500000"))
    admin.post("/api/requests", json=request_payload(city="Rabat", priority="low", budget_max="800000", transaction_type="rent"))
    rid = agent.post("/api/requests", json=request_payload(city="Tanger", priority="high", budget_max="2000000")).json()["request"]["id"]
    q = lambda **p: admin.get("/api/requests", params=p).json()["total"]  # noqa: E731
    assert q(city="Rabat") == 2
    assert q(city="Rabat", priority="high") == 1
    assert q(priority="high", budget_min=1600000) == 1
    assert q(assigned_agent_id=agent.user_id) == 1
    assert q(assigned_agent_id="none", transaction_type="rent") == 1
    assert q(status="open", waiting="true") == 3
    assert q(q=admin.get(f"/api/requests/{rid}").json()["reference"]) == 1


def test_photo_upload_validates_real_file_type(admin, make_property):
    pid = make_property()["id"]
    fake = admin.post(f"/api/properties/{pid}/photos", files=[("files", ("evil.jpg", b"<?php echo 1; ?>", "image/jpeg"))])
    assert fake.status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    ok = admin.post(f"/api/properties/{pid}/photos", files=[("files", ("photo.png", png, "image/png"))])
    assert ok.status_code == 201 and len(ok.json()["photos"]) == 1
    url = ok.json()["photos"][0]["url"]
    assert admin.get(url).content == png


# ------------------------------------------------------------------ deals


def _deal_setup(agent, make_property):
    rid = agent.post("/api/requests", json=request_payload()).json()["request"]["id"]
    prop = make_property()
    r = agent.post("/api/deals", json={"request_id": rid, "property_id": prop["id"]})
    assert r.status_code == 201, r.text
    return rid, prop, r.json()


def test_completed_transaction_preserves_history(admin, agent, make_property, db):
    rid, prop, deal = _deal_setup(agent, make_property)
    assert deal["status"] == "negotiation" and deal["asking_price"] == "1150000.00"
    assert admin.get(f"/api/properties/{prop['id']}").json()["status"] == "under_negotiation"
    assert agent.post(f"/api/deals/{deal['id']}/offers", json={"amount": "1080000", "party": "customer"}).status_code == 201
    d = agent.get(f"/api/deals/{deal['id']}").json()
    offer_id = d["offers"][0]["id"]
    agent.patch(f"/api/deals/{deal['id']}/offers/{offer_id}", json={"status": "accepted"})
    assert agent.post(f"/api/deals/{deal['id']}/reserve", json={}).json()["status"] == "reserved"
    assert admin.get(f"/api/properties/{prop['id']}").json()["status"] == "reserved"
    won = agent.post(f"/api/deals/{deal['id']}/win", json={"closing_date": "2026-10-20"}).json()
    assert won["status"] == "won" and won["agreed_price"] == "1080000.00" and won["actual_closing_date"] == "2026-10-20"
    assert won["commission_amount"] == "27000.00"  # default sale rule 2.5 %

    assert admin.get(f"/api/properties/{prop['id']}").json()["status"] == "sold"
    assert admin.get(f"/api/requests/{rid}").json()["status"] == "converted"
    # The history is intact and the closed deal is read-only.
    d = admin.get(f"/api/deals/{deal['id']}").json()
    assert len(d["offers"]) == 1 and d["offers"][0]["status"] == "accepted"
    assert agent.patch(f"/api/deals/{deal['id']}", json={"notes": "x"}).status_code == 409
    assert agent.post(f"/api/deals/{deal['id']}/win", json={}).status_code == 409
    assert db.scalar(select(Deal).where(Deal.id == deal["id"])) is not None
    acts = db.scalars(select(Activity).where(Activity.deal_id == deal["id"])).all()
    assert len(acts) >= 4
    assert db.scalar(select(AuditLog).where(AuditLog.action == "win")) is not None
    # A sold property cannot be the object of a new deal.
    assert agent.post("/api/deals", json={"request_id": rid, "property_id": prop["id"]}).status_code == 409


def test_double_reservation_requires_admin_override(admin, agent, agent2, make_property):
    rid, prop, deal1 = _deal_setup(agent, make_property)
    rid2 = agent2.post("/api/requests", json=request_payload()).json()["request"]["id"]
    deal2 = agent2.post("/api/deals", json={"request_id": rid2, "property_id": prop["id"]}).json()
    assert agent.post(f"/api/deals/{deal1['id']}/reserve", json={}).status_code == 200
    r = agent2.post(f"/api/deals/{deal2['id']}/reserve", json={})
    assert r.status_code == 409 and "autorisation administrative" in r.json()["detail"]
    assert agent2.post(f"/api/deals/{deal2['id']}/reserve", json={"override": True}).status_code == 403
    r = admin.post(f"/api/deals/{deal2['id']}/reserve", json={"override": True})
    assert r.status_code == 200 and r.json()["reservation_override"] is True


def test_lost_deal_puts_property_back_and_notifies_waiting_agents(admin, agent, agent2, make_property, db):
    rid, prop, deal = _deal_setup(agent, make_property)
    # Another customer waiting for the same kind of property
    rid2 = agent2.post("/api/requests", json=request_payload()).json()["request"]["id"]
    assert agent2.get(f"/api/requests/{rid2}/matches").json() == []  # property is under negotiation
    r = agent.post(f"/api/deals/{deal['id']}/lose", json={"reason": "Financement refusé"})
    assert r.status_code == 200 and r.json()["status"] == "lost"
    assert admin.get(f"/api/properties/{prop['id']}").json()["status"] == "available"
    assert len(agent2.get(f"/api/requests/{rid2}/matches").json()) == 1
    from app.models import Notification

    assert db.scalar(select(Notification).where(Notification.user_id == agent2.user_id, Notification.type == "match_found")) is not None


def test_commission_rules_are_configurable(admin, agent, make_property):
    r = admin.post("/api/commission-rules", json={"name": "Villas premium", "transaction_type": "sale", "property_type": "villa",
                                                  "min_price": "2000000", "rate_percent": "3", "fixed_amount": "5000", "priority": 10})
    assert r.status_code == 201
    rid = agent.post("/api/requests", json=request_payload(property_type="villa", budget_max="5000000")).json()["request"]["id"]
    prop = make_property(property_type="villa", price="3000000")
    deal = agent.post("/api/deals", json={"request_id": rid, "property_id": prop["id"]}).json()
    assert deal["commission_amount"] == "95000.00"  # 3 % of 3 000 000 + 5 000
    won = agent.post(f"/api/deals/{deal['id']}/win", json={"agreed_price": "2500000"}).json()
    assert won["commission_amount"] == "80000.00"
    assert agent.post(f"/api/deals/{deal['id']}/commission", json={"commission_amount": "1"}).status_code == 403
