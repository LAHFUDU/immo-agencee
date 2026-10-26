"""Migrations from a clean database, and the documented start-up procedure, run for real."""

import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, make_url, text

from app.core.db import Base
from tests.conftest import BACKEND_DIR, TEST_DB_URL, alembic_config


@pytest.fixture
def scratch_db():
    """A throw-away database next to the test database (skipped if the role cannot CREATE DATABASE)."""
    url = make_url(TEST_DB_URL)
    name = f"{url.database}_scratch"
    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
            c.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"cannot create scratch database: {exc}")
    yield url.set(database=name).render_as_string(hide_password=False)
    with admin_engine.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin_engine.dispose()


def test_migrations_from_clean_database(scratch_db, monkeypatch):
    import app.core.config as cfg

    monkeypatch.setattr(cfg.settings, "DATABASE_URL", scratch_db)
    alembic_cfg = alembic_config(scratch_db)
    command.upgrade(alembic_cfg, "head")
    eng = create_engine(scratch_db)
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"models and migrations differ: {diff}"
        assert conn.execute(text("SELECT nextval('request_ref_seq')")).scalar() == 1
    command.downgrade(alembic_cfg, "base")
    with eng.connect() as conn:
        tables = conn.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'alembic_version'")).scalar()
        assert tables == 0
    command.upgrade(alembic_cfg, "head")
    eng.dispose()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_documented_setup_starts_the_application(scratch_db):
    """README procedure: migrate -> init -> create-admin -> start server -> health + login."""
    env = {**os.environ, "DATABASE_URL": scratch_db, "ENV": "development", "SECRET_KEY": "x" * 40, "UPLOAD_DIR": "test_uploads"}
    py = sys.executable
    run = lambda *args, **kw: subprocess.run([py, "-m", *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120, **kw)  # noqa: E731
    r = run("alembic", "upgrade", "head")
    assert r.returncode == 0, r.stderr
    r = run("app.cli", "init")
    assert r.returncode == 0, r.stderr
    r = run("app.cli", "create-admin", "--email", "boss@example.org", "--name", "Patron", "--password-stdin", input="Admin-Password-2026\n")
    assert r.returncode == 0, r.stderr
    weak = run("app.cli", "create-admin", "--email", "weak@example.org", "--password-stdin", input="weak\n")
    assert weak.returncode == 1

    port = _free_port()
    server = subprocess.Popen([py, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND_DIR, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(60):
            try:
                if httpx.get(f"{base}/api/health/ready", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            pytest.fail("server did not become ready")
        with httpx.Client(base_url=base) as c:
            r = c.post("/api/auth/login", json={"email": "boss@example.org", "password": "Admin-Password-2026"})
            assert r.status_code == 200 and "users.manage" in r.json()["permissions"]
            assert c.get("/api/dashboard").status_code == 200
            assert c.get("/api/openapi.json").status_code == 200
    finally:
        server.terminate()
        server.wait(timeout=20)
