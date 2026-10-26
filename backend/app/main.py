import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, crm, deals, properties, public, reports, requests, system, users
from app.core.config import settings

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("immo")

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version="1.0.0",
    description="API de gestion d'agence immobilière : demandes clients, inventaire, correspondances, CRM, transactions.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        if settings.ENV == "test":
            raise
        log.exception("unhandled error rid=%s %s %s", rid, request.method, request.url.path)
        response = JSONResponse({"detail": "Erreur interne du serveur.", "request_id": rid}, status_code=500)
    response.headers["X-Request-ID"] = rid
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/") and not request.url.path.startswith(("/api/docs", "/api/redoc")):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.ENV != "test":
        log.info("%s %s %s %.0fms rid=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - start) * 1000, rid)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        msg = str(e.get("msg", "")).removeprefix("Value error, ")
        loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path")]
        errors.append({"field": ".".join(loc), "message": msg})
    summary = "; ".join(f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors[:5])
    return JSONResponse({"detail": summary or "Données invalides.", "errors": errors}, status_code=422)


for module in (auth, users, properties, requests, crm, deals, reports, system, public):
    app.include_router(module.router, prefix="/api")


# Optional: serve the built React app from the API itself (desktop / single-server mode).
# Set FRONTEND_DIST to the frontend "dist" folder; in Docker, Caddy serves it instead.
def _mount_frontend() -> None:
    import os
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = os.environ.get("FRONTEND_DIST")
    if not dist or not (Path(dist) / "index.html").is_file():
        return
    root = Path(dist).resolve()
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Introuvable."}, status_code=404)
        candidate = (root / path).resolve()
        if path and root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(root / "index.html")


_mount_frontend()
