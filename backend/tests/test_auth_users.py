from sqlalchemy import select

from app.models import AuditLog, Role
from app.services import rate_limit
from tests.conftest import PASSWORD, ApiClient, make_user


def _role_id(admin, code):
    return next(r["id"] for r in admin.get("/api/roles").json() if r["code"] == code)


def test_admin_creates_employee_with_temp_password(admin, client_factory):
    r = admin.post("/api/users", json={"email": "Nouvel.Agent@Example.com", "full_name": "Nouvel Agent",
                                        "role_id": _role_id(admin, "commercial_agent"), "credential_mode": "temp_password"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "nouvel.agent@example.com"
    assert body["user"]["must_change_password"] is True
    assert body["email_status"] == "not_sent"
    temp = body["temp_password"]
    assert temp and len(temp) >= 10

    emp = client_factory()
    me = emp.login("nouvel.agent@example.com", temp)
    assert me.status_code == 200
    # Must change the temporary password before using the application.
    assert emp.get("/api/requests").status_code == 403
    r = emp.post("/api/auth/change-password", json={"current_password": temp, "new_password": "Nouveau-Mdp-2026"})
    assert r.status_code == 200, r.text
    assert emp.get("/api/requests").status_code == 200
    assert admin.post("/api/users", json={"email": "nouvel.agent@example.com", "full_name": "Doublon",
                                          "role_id": _role_id(admin, "commercial_agent")}).status_code == 409


def test_admin_invitation_link_flow(admin, client_factory, db):
    r = admin.post("/api/users", json={"email": "invite@example.com", "full_name": "Invité",
                                        "role_id": _role_id(admin, "sales_manager"), "credential_mode": "invite"})
    assert r.status_code == 201
    url = r.json()["invite_url"]
    assert r.json()["email_status"] == "not_configured"  # SMTP not configured: nothing pretended
    token = url.split("token=")[1]
    anon = client_factory()
    assert anon.get("/api/auth/token-info", params={"token": token}).json()["email"] == "invite@example.com"
    assert anon.post("/api/auth/accept-token", json={"token": token, "new_password": "faible"}).status_code == 422
    r = anon.post("/api/auth/accept-token", json={"token": token, "new_password": "Mot-de-passe-Solide-1"})
    assert r.status_code == 200
    assert "requests.view_all" in r.json()["permissions"]
    # single use
    assert anon.post("/api/auth/accept-token", json={"token": token, "new_password": "Mot-de-passe-Solide-2"}).status_code == 400
    assert db.scalar(select(AuditLog).where(AuditLog.action == "create", AuditLog.entity_type == "user")) is not None


def test_restricted_agent_cannot_use_admin_operations(agent):
    assert agent.get("/api/users").status_code == 403
    assert agent.post("/api/users", json={"email": "x@example.com", "full_name": "X Y", "role_id": "00000000-0000-0000-0000-000000000000"}).status_code == 403
    assert agent.get("/api/roles").status_code == 403
    assert agent.post("/api/roles", json={"name": "Hack", "permissions": ["users.manage"]}).status_code == 403
    assert agent.get("/api/settings").status_code == 403
    assert agent.put("/api/settings/matching", json={"value": {"budget_tolerance_percent": 50}}).status_code == 403
    assert agent.get("/api/audit-logs").status_code == 403
    assert agent.post("/api/commission-rules", json={"name": "x", "transaction_type": "sale", "rate_percent": "50"}).status_code == 403
    assert agent.get("/api/reports").status_code == 403
    # but the agent can do their own work
    assert agent.get("/api/requests").status_code == 200
    assert agent.get("/api/properties").status_code == 200


def test_no_privilege_escalation_through_custom_role(admin, client_factory, db):
    r = admin.post("/api/roles", json={"name": "RH", "permissions": ["users.manage", "dashboard.view"]})
    assert r.status_code == 201
    hr = client_factory()
    u = make_user("commercial_agent", email="rh@example.com")
    with db.begin():
        db.get(type(u), u.id).role_id = db.scalar(select(Role).where(Role.code == r.json()["code"])).id
    assert hr.login("rh@example.com").status_code == 200
    admin_role = _role_id(hr, "super_admin")
    res = hr.post("/api/users", json={"email": "evil@example.com", "full_name": "Evil", "role_id": admin_role})
    assert res.status_code == 403
    manager_role = _role_id(hr, "sales_manager")  # grants permissions HR does not hold
    assert hr.post("/api/users", json={"email": "evil@example.com", "full_name": "Evil", "role_id": manager_role}).status_code == 403
    # cannot modify a super admin
    admin_id = admin.get("/api/auth/me").json()["id"]
    assert hr.post(f"/api/users/{admin_id}/deactivate").status_code == 403


def test_csrf_required_for_state_changes(agent):
    token = agent.headers.pop("X-CSRF-Token")
    assert agent.post("/api/requests", json={}).status_code == 403
    agent.headers["X-CSRF-Token"] = "wrong"
    assert agent.post("/api/auth/logout").status_code == 403
    agent.headers["X-CSRF-Token"] = token
    assert agent.post("/api/auth/logout").status_code == 204
    assert agent.get("/api/auth/me").status_code == 401


def test_deactivation_revokes_sessions_and_reactivation(admin, agent):
    me = agent.get("/api/auth/me").json()
    agent_id = me["id"]
    assert admin.post(f"/api/users/{agent_id}/deactivate").status_code == 200
    assert agent.get("/api/requests").status_code == 401
    assert agent.login(me["email"]).status_code == 401  # deactivated accounts cannot log in
    assert admin.post(f"/api/users/{agent_id}/reactivate").json()["is_active"] is True
    me = admin.get("/api/auth/me").json()
    assert admin.post(f"/api/users/{me['id']}/deactivate").status_code == 409  # not yourself


def test_password_reset_revokes_sessions(admin, agent):
    agent_id = agent.get("/api/auth/me").json()["id"]
    r = admin.post(f"/api/users/{agent_id}/reset-password", json={"credential_mode": "temp_password"})
    assert r.status_code == 200 and r.json()["temp_password"]
    assert agent.get("/api/requests").status_code == 401


def test_login_rate_limited(client_factory):
    rate_limit.ENABLED = True
    make_user("commercial_agent", email="victim@example.com")
    c: ApiClient = client_factory()
    codes = [c.login("victim@example.com", "wrong-password").status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    assert c.login("victim@example.com", PASSWORD).status_code == 429  # still locked even with the right password


def test_login_does_not_reveal_unknown_accounts(client_factory):
    c = client_factory()
    r = c.login("nobody@example.com", "whatever-123")
    assert r.status_code == 401 and r.json()["detail"] == "Identifiants invalides."
