import hmac
from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db, utcnow
from app.core.security import token_hash
from app.models import User, UserSession

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Principal:
    user: User
    session: UserSession
    permissions: set[str] = field(default_factory=set)

    @property
    def id(self):
        return self.user.id

    def can(self, *codes: str) -> bool:
        return all(c in self.permissions for c in codes)

    def can_any(self, *codes: str) -> bool:
        return any(c in self.permissions for c in codes)


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "unknown")[:64]


def load_session(request: Request, db: Session) -> UserSession | None:
    raw = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
    now = utcnow()
    if not sess or sess.revoked_at is not None or sess.expires_at <= now:
        return None
    if not sess.user.is_active:
        return None
    return sess


def get_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    sess = load_session(request, db)
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.")

    # CSRF: double-submit token, compared with the value bound to the server-side session.
    if request.method not in SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Jeton CSRF invalide ou manquant.")

    now = utcnow()
    if (now - sess.last_seen_at) > timedelta(minutes=5):
        # Sliding expiration, written at most every 5 minutes.
        sess.last_seen_at = now
        sess.expires_at = now + timedelta(hours=settings.SESSION_TTL_HOURS)
        db.commit()

    principal = Principal(user=sess.user, session=sess, permissions=sess.user.permission_codes())
    request.state.principal = principal
    return principal


def get_active_principal(principal: Principal = Depends(get_principal)) -> Principal:
    """Users flagged must_change_password can only reach the auth endpoints."""
    if principal.user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vous devez changer votre mot de passe avant de continuer.")
    return principal


def require(*codes: str):
    def _dep(principal: Principal = Depends(get_active_principal)) -> Principal:
        missing = [c for c in codes if c not in principal.permissions]
        if missing:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès refusé : permission insuffisante.")
        return principal

    return _dep


def require_any(*codes: str):
    def _dep(principal: Principal = Depends(get_active_principal)) -> Principal:
        if not principal.can_any(*codes):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès refusé : permission insuffisante.")
        return principal

    return _dep
