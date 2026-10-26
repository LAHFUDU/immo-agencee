from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db, utcnow
from app.core.deps import Principal, client_ip, get_principal
from app.core.security import (
    hash_password,
    needs_rehash,
    new_token,
    token_hash,
    validate_password_strength,
    verify_password,
)
from app.models import AuthToken, User, UserSession
from app.schemas.users import AcceptTokenIn, ChangePasswordIn, LoginIn, MeOut
from app.services import audit, rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def me_out(user: User, sess: UserSession) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role_name=user.role.name,
        role_code=user.role.code,
        is_superadmin=user.is_superadmin,
        must_change_password=user.must_change_password,
        language=user.language,
        permissions=sorted(user.permission_codes()),
        csrf_token=sess.csrf_token,
    )


def _start_session(db: Session, user: User, request: Request, response: Response) -> UserSession:
    raw = new_token()
    sess = UserSession(
        token_hash=token_hash(raw),
        csrf_token=new_token(24),
        user_id=user.id,
        expires_at=utcnow() + timedelta(hours=settings.SESSION_TTL_HOURS),
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    db.add(sess)
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        raw,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return sess


def revoke_user_sessions(db: Session, user_id, except_id=None) -> None:
    stmt = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id:
        stmt = stmt.where(UserSession.id != except_id)
    db.execute(stmt.values(revoked_at=utcnow()))


@router.post("/login", response_model=MeOut)
def login(data: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    email = data.email.lower()
    key = f"login:{ip}:{email}"
    window = timedelta(minutes=settings.LOGIN_WINDOW_MINUTES)
    rate_limit.check(db, key, settings.LOGIN_MAX_FAILURES, window)
    rate_limit.check(db, f"login-ip:{ip}", settings.LOGIN_MAX_FAILURES * 6, window)

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not verify_password(data.password, user.password_hash) or not user.is_active:
        rate_limit.hit(db, key)
        rate_limit.hit(db, f"login-ip:{ip}")
        audit.log(db, user_id=user.id if user else None, action="login_failed", entity_type="auth", label=email, ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides.")

    rate_limit.clear(db, key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
    user.last_login_at = utcnow()
    sess = _start_session(db, user, request, response)
    audit.log(db, user_id=user.id, action="login", entity_type="auth", label=user.email, ip=ip)
    db.commit()
    return me_out(user, sess)


@router.post("/logout", status_code=204)
def logout(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    principal.session.revoked_at = utcnow()
    db.commit()
    resp = Response(status_code=204)
    resp.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return resp


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(get_principal)):
    return me_out(principal.user, principal.session)


@router.post("/change-password", response_model=MeOut)
def change_password(
    data: ChangePasswordIn, request: Request, principal: Principal = Depends(get_principal), db: Session = Depends(get_db)
):
    user = principal.user
    rate_limit.check(db, f"pwd:{user.id}", 10, timedelta(minutes=15))
    if not verify_password(data.current_password, user.password_hash):
        rate_limit.hit(db, f"pwd:{user.id}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect.")
    if err := validate_password_strength(data.new_password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, err)
    if verify_password(data.new_password, user.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Le nouveau mot de passe doit être différent.")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    revoke_user_sessions(db, user.id, except_id=principal.session.id)
    audit.log(db, user_id=user.id, action="password_change", entity_type="user", entity_id=user.id, label=user.email, ip=client_ip(request))
    db.commit()
    return me_out(user, principal.session)


@router.post("/accept-token", response_model=MeOut)
def accept_token(data: AcceptTokenIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Consume an invitation or password-reset link: sets the password and opens a session."""
    ip = client_ip(request)
    rate_limit.check(db, f"token:{ip}", 20, timedelta(minutes=15))
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(data.token)).with_for_update())
    if tok is None or tok.used_at is not None or tok.expires_at <= utcnow():
        rate_limit.hit(db, f"token:{ip}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Lien invalide ou expiré. Demandez un nouveau lien à l'administrateur.")
    if err := validate_password_strength(data.new_password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, err)
    user = db.get(User, tok.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Compte désactivé.")
    tok.used_at = utcnow()
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    user.last_login_at = utcnow()
    revoke_user_sessions(db, user.id)
    sess = _start_session(db, user, request, response)
    audit.log(db, user_id=user.id, action=f"token_{tok.purpose.value}_used", entity_type="user", entity_id=user.id, label=user.email, ip=ip)
    db.commit()
    return me_out(user, sess)


@router.get("/token-info")
def token_info(token: str, db: Session = Depends(get_db)):
    tok = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash(token)))
    if tok is None or tok.used_at is not None or tok.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Lien invalide ou expiré.")
    user = db.get(User, tok.user_id)
    return {"email": user.email, "full_name": user.full_name, "purpose": tok.purpose.value}
