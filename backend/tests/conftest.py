"""Test harness. Runs against a dedicated PostgreSQL database whose name must end in "_test";
it is wiped and rebuilt with Alembic migrations at the start of the session."""

import os
import shutil
import uuid

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://immo@localhost:5434/immo_test")
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["ENV"] = "test"
os.environ["UPLOAD_DIR"] = "test_uploads"
os.environ["COOKIE_SECURE"] = "false"
os.environ["SMTP_HOST"] = ""
os.environ["CORS_ORIGINS"] = "http://testserver"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import make_url, select, text  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.services import rate_limit  # noqa: E402
from app.services.bootstrap import seed_reference_data  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "Test-Password-123"

if not make_url(TEST_DB_URL).database.endswith("_test"):
    raise RuntimeError("Refusing to run tests on a database whose name does not end with '_test'.")

REFERENCE_TABLES = {"permissions", "roles", "role_permissions", "property_categories", "property_features", "alembic_version"}


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _database():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(TEST_DB_URL), "head")  # migrations from a clean database
    rate_limit.ENABLED = False
    yield
    engine.dispose()
    shutil.rmtree(os.path.join(os.getcwd(), "test_uploads"), ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean():
    with engine.begin() as conn:
        tables = [r[0] for r in conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))]
        data_tables = [t for t in tables if t not in REFERENCE_TABLES]
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in data_tables) + " RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE roles, role_permissions CASCADE"))
    with SessionLocal() as db:
        seed_reference_data(db)
        db.commit()
    rate_limit.ENABLED = False
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


class ApiClient(TestClient):
    """TestClient that logs in and automatically sends the CSRF header."""

    csrf: str | None = None
    user_id: str | None = None

    def login(self, email: str, password: str = PASSWORD):
        r = self.post("/api/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            self.csrf = r.json()["csrf_token"]
            self.user_id = r.json()["id"]
            self.headers["X-CSRF-Token"] = self.csrf
        return r


def make_user(role_code: str, email: str | None = None, name: str = "Utilisateur Test", is_agent: bool = True) -> User:
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == role_code))
        u = User(email=email or f"{role_code}-{uuid.uuid4().hex[:6]}@example.com", full_name=name, role_id=role.id,
                 password_hash=hash_password(PASSWORD), is_agent=is_agent)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u


@pytest.fixture
def client_factory():
    clients = []

    def _make(role_code: str | None = None, **kw) -> ApiClient:
        c = ApiClient(app)
        clients.append(c)
        if role_code:
            u = make_user(role_code, **kw)
            r = c.login(u.email)
            assert r.status_code == 200, r.text
        return c

    yield _make
    for c in clients:
        c.close()


@pytest.fixture
def admin(client_factory) -> ApiClient:
    return client_factory("super_admin", name="Admin Test", is_agent=False)


@pytest.fixture
def agent(client_factory) -> ApiClient:
    return client_factory("commercial_agent", name="Agent Un")


@pytest.fixture
def agent2(client_factory) -> ApiClient:
    return client_factory("commercial_agent", name="Agent Deux")


# ------------------------------------------------------------------ data builders


def property_payload(**over) -> dict:
    data = {
        "property_type": "apartment", "transaction_type": "sale", "title": "Appartement test", "city": "Rabat",
        "neighborhood": "Agdal", "surface": "110", "price": "1150000", "bedrooms": 3, "bathrooms": 2,
        "features": ["parking", "elevator"], "address": "12 rue Secrète", "internal_notes": "Note interne confidentielle",
        "owner": {"full_name": "Propriétaire Privé", "phone": "0611223344"},
    }
    data.update(over)
    return data


def request_payload(**over) -> dict:
    data = {
        "customer": {"full_name": "Client Test", "phone": f"06{uuid.uuid4().int % 10**8:08d}", "email": None},
        "property_type": "apartment", "transaction_type": "sale", "city": "Rabat", "neighborhood": "Agdal",
        "budget_max": "1200000", "surface_min": "90", "bedrooms_min": 2,
    }
    data.update(over)
    return data


@pytest.fixture
def make_property(admin):
    def _make(**over):
        r = admin.post("/api/properties", json=property_payload(**over))
        assert r.status_code == 201, r.text
        return r.json()

    return _make
