"""Immo Agence — desktop launcher (Windows).

Double-click (via the desktop shortcut): opens the app window immediately with a loading screen,
starts the local database if needed, starts the application server in the background, then shows
the login page. Closing the window stops the server. No terminal, no browser needed.
"""

import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
DIST = ROOT / "frontend" / "dist"
PGDATA = ROOT / ".pgdata"
PG_BIN = Path(os.environ.get("IMMO_PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
DB_PORT = 5434
APP_PORT = 8765
LOG = ROOT / "desktop" / "launcher.log"
MUTEX_NAME = "Local\\ImmoAgenceDesktopLauncher"
SERVICE = "ImmoAgenceDB"  # created by desktop/Installer-Immo-Agence.cmd

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
DETACHED = 0x00000008  # DETACHED_PROCESS
NEW_GROUP = 0x00000200  # CREATE_NEW_PROCESS_GROUP

LOADING_HTML = """<!doctype html><html lang="fr"><meta charset="utf-8">
<body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:Segoe UI,sans-serif;background:#0f3d3e;color:#fff">
<div style="text-align:center"><div style="font-size:24px;font-weight:600">Immo Agence</div>
<p style="color:#acd8d4">Démarrage en cours… (jusqu'à une minute la première fois)</p></div></body></html>"""


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def message(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "Immo Agence", 0x10)


def port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def db_ready() -> bool:
    try:
        import psycopg

        with psycopg.connect(f"postgresql://immo@127.0.0.1:{DB_PORT}/immo", connect_timeout=3) as c:
            c.execute("select 1")
        return True
    except Exception:  # noqa: BLE001
        return False


def pg_ctl(*args: str, wait: bool = True):
    cmd = [str(PG_BIN / "pg_ctl.exe"), "-D", str(PGDATA), *args]
    if wait:
        return subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW, timeout=60)
    # Fully detached so the database keeps running independently of this window.
    subprocess.Popen(cmd, creationflags=NO_WINDOW | DETACHED | NEW_GROUP, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return None


def ensure_database() -> None:
    """Start the database if needed, then wait. Never stops a server that is still starting:
    after an unclean shutdown PostgreSQL can take a minute to recover."""
    if db_ready():
        return
    if service_installed():
        # Installed mode: the Windows service owns the database. Never start a second copy.
        log("waiting for Windows service " + SERVICE)
        subprocess.run(["sc", "start", SERVICE], capture_output=True, creationflags=NO_WINDOW)
        _wait_db("Le service « Immo Agence DB » ne répond pas. Relancez « Installer Immo Agence » ou redémarrez le PC.")
        return
    status = pg_ctl("status")
    if status is not None and status.returncode == 0:
        log("database process running, waiting for it to accept connections")
    else:
        log("starting database")
        pg_ctl("-o", f"-p {DB_PORT} -c listen_addresses=localhost", "-l", str(PGDATA / "server.log"), "-W", "start", wait=False)
    _wait_db("La base de données ne répond pas après 3 minutes.\nDétails : " + str(PGDATA / "server.log"))


def service_installed() -> bool:
    r = subprocess.run(["sc", "query", SERVICE], capture_output=True, creationflags=NO_WINDOW)
    return r.returncode == 0


def _wait_db(error: str, seconds: int = 180) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if db_ready():
            log("database ready")
            return
        time.sleep(1)
    raise RuntimeError(error)


def load_env() -> None:
    env_file = BACKEND / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    os.environ["DATABASE_URL"] = f"postgresql+psycopg://immo@127.0.0.1:{DB_PORT}/immo"
    os.environ["FRONTEND_DIST"] = str(DIST)
    os.environ["UPLOAD_DIR"] = str(BACKEND / "uploads")
    os.environ["FRONTEND_URL"] = f"http://127.0.0.1:{APP_PORT}"
    os.environ["CORS_ORIGINS"] = f"http://127.0.0.1:{APP_PORT}"
    os.environ["COOKIE_SECURE"] = "false"


def start_server():
    import uvicorn

    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=APP_PORT, log_level="warning", log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(150):
        if port_open(APP_PORT):
            return server
        time.sleep(0.1)
    raise RuntimeError("Le serveur de l'application n'a pas démarré.")


def single_instance() -> bool:
    """True if no other launcher is running (Windows named mutex, released when the process exits)."""
    ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    LOG.parent.mkdir(exist_ok=True)
    if not single_instance():
        message("L'application est déjà ouverte ou en train de démarrer.\nRegardez dans la barre des tâches.")
        return
    try:
        if not (DIST / "index.html").is_file():
            raise RuntimeError("Interface non construite : lancez « npm run build » dans le dossier frontend.")
        import webview
    except Exception as exc:  # noqa: BLE001
        log(traceback.format_exc())
        message(f"Impossible de démarrer l'application :\n\n{exc}")
        return

    state: dict = {"server": None}
    window = webview.create_window("Immo Agence", html=LOADING_HTML, width=1360, height=860, min_size=(380, 600))

    def boot() -> None:
        try:
            if port_open(APP_PORT):
                raise RuntimeError(f"Le port {APP_PORT} est déjà utilisé par un autre programme.")
            ensure_database()
            load_env()
            state["server"] = start_server()
            window.load_url(f"http://127.0.0.1:{APP_PORT}/login")
        except Exception as exc:  # noqa: BLE001
            log(traceback.format_exc())
            message(f"Impossible de démarrer l'application :\n\n{exc}\n\nJournal : {LOG}")
            window.destroy()

    webview.start(boot, private_mode=False)  # private_mode=False keeps the login between launches
    if state["server"]:
        state["server"].should_exit = True


if __name__ == "__main__":
    main()
