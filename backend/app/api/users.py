from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import revoke_user_sessions
from app.api.helpers import parse_uuid
from app.core.config import settings
from app.core.db import get_db, utcnow
from app.core.deps import Principal, client_ip, get_active_principal, require
from app.core.permissions import PERMISSIONS
from app.core.security import generate_temp_password, hash_password, new_token, token_hash
from app.models import AuthToken, Permission, Role, User
from app.models.enums import TokenPurpose
from app.schemas.common import UserRef
from app.schemas.users import (
    CredentialResult,
    PermissionOut,
    ResetRequest,
    RoleIn,
    RoleOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import audit
from app.services.email import send_email
from app.services.text import normalize_key

router = APIRouter(tags=["users"])


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        phone=u.phone,
        job_title=u.job_title,
        role_id=u.role_id,
        role_name=u.role.name,
        role_code=u.role.code,
        is_active=u.is_active,
        is_agent=u.is_agent,
        must_change_password=u.must_change_password,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
    )


def role_out(r: Role) -> RoleOut:
    perms = list(PERMISSIONS) if r.is_superadmin else sorted(p.code for p in r.permissions)
    return RoleOut(
        id=r.id, code=r.code, name=r.name, description=r.description,
        is_system=r.is_system, is_superadmin=r.is_superadmin, permissions=perms,
    )


def _check_can_assign(p: Principal, role: Role) -> None:
    """Prevent privilege escalation: a non-super-admin can only grant permissions they hold."""
    if p.user.is_superadmin:
        return
    if role.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul un super administrateur peut attribuer ce rôle.")
    extra = {perm.code for perm in role.permissions} - p.permissions
    if extra:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ce rôle accorde des permissions que vous ne possédez pas.")


def _check_can_manage(p: Principal, target: User) -> None:
    if target.is_superadmin and not p.user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Seul un super administrateur peut modifier ce compte.")


def _issue_credentials(db: Session, user: User, mode: str, created_by, purpose: TokenPurpose) -> tuple[str | None, str | None, str]:
    if mode == "temp_password":
        pwd = generate_temp_password()
        user.password_hash = hash_password(pwd)
        user.must_change_password = True
        return None, pwd, "not_sent"
    raw = new_token()
    db.add(
        AuthToken(
            token_hash=token_hash(raw),
            user_id=user.id,
            purpose=purpose,
            expires_at=utcnow() + timedelta(hours=settings.INVITE_TTL_HOURS),
            created_by_id=created_by,
        )
    )
    url = f"{settings.FRONTEND_URL}/accept-invite?token={raw}"
    subject = "Invitation à rejoindre l'espace agence" if purpose == TokenPurpose.INVITE else "Réinitialisation de votre mot de passe"
    email_status = send_email(
        user.email,
        subject,
        f"Bonjour {user.full_name},\n\nUtilisez ce lien (valable {settings.INVITE_TTL_HOURS} h) pour définir votre mot de passe :\n{url}\n",
    )
    return url, None, email_status


# ------------------------------------------------------------------ users


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require("users.manage"))])
def list_users(db: Session = Depends(get_db), include_inactive: bool = True):
    stmt = select(User).order_by(User.is_active.desc(), User.full_name)
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    return [user_out(u) for u in db.scalars(stmt).all()]


@router.get("/users/directory", response_model=list[UserRef])
def user_directory(agents_only: bool = False, p: Principal = Depends(get_active_principal), db: Session = Depends(get_db)):
    """Minimal list (id + name) of active employees, for assignment pickers."""
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.full_name)
    if agents_only:
        stmt = stmt.where(User.is_agent.is_(True))
    return [UserRef(id=u.id, full_name=u.full_name) for u in db.scalars(stmt).all()]


@router.post("/users", response_model=CredentialResult, status_code=201)
def create_user(data: UserCreate, request: Request, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail.")
    role = db.get(Role, data.role_id)
    if role is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Rôle inconnu.")
    _check_can_assign(p, role)
    user = User(
        email=data.email.lower(), full_name=data.full_name, phone=data.phone, job_title=data.job_title,
        role_id=role.id, is_agent=data.is_agent, is_active=True,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    invite_url, temp_pwd, email_status = _issue_credentials(db, user, data.credential_mode, p.id, TokenPurpose.INVITE)
    audit.log(db, user_id=p.id, action="create", entity_type="user", entity_id=user.id, label=user.email,
              changes={"role": role.code, "credential_mode": data.credential_mode}, ip=client_ip(request))
    db.commit()
    return CredentialResult(user=user_out(user), mode=data.credential_mode, invite_url=invite_url,
                            temp_password=temp_pwd, email_status=email_status)


@router.get("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require("users.manage"))])
def get_user(user_id: str, db: Session = Depends(get_db)):
    u = db.get(User, parse_uuid(user_id))
    if not u:
        raise HTTPException(404, "Utilisateur introuvable.")
    return user_out(u)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, data: UserUpdate, request: Request, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.get(User, parse_uuid(user_id))
    if not u:
        raise HTTPException(404, "Utilisateur introuvable.")
    _check_can_manage(p, u)
    before = audit.snapshot(u, ["email", "full_name", "phone", "job_title", "role_id", "is_agent"])
    fields = data.model_dump(exclude_unset=True)
    if "email" in fields and fields["email"]:
        email = fields["email"].lower()
        if db.scalar(select(User).where(func.lower(User.email) == email, User.id != u.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cet e-mail.")
        u.email = email
    if "role_id" in fields and fields["role_id"] and fields["role_id"] != u.role_id:
        role = db.get(Role, fields["role_id"])
        if role is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Rôle inconnu.")
        _check_can_assign(p, role)
        if u.is_superadmin and not role.is_superadmin and _active_superadmins(db) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Impossible de retirer le dernier super administrateur.")
        u.role_id = role.id
        revoke_user_sessions(db, u.id)  # permissions changed: force a fresh login
    for f in ("full_name", "phone", "job_title", "is_agent"):
        if f in fields and fields[f] is not None:
            setattr(u, f, fields[f])
    db.flush()
    db.refresh(u)
    audit.log(db, user_id=p.id, action="update", entity_type="user", entity_id=u.id, label=u.email,
              changes=audit.diff(before, audit.snapshot(u, list(before))), ip=client_ip(request))
    db.commit()
    return user_out(u)


def _active_superadmins(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).join(Role).where(User.is_active.is_(True), Role.is_superadmin.is_(True))
    ) or 0


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: str, request: Request, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.get(User, parse_uuid(user_id))
    if not u:
        raise HTTPException(404, "Utilisateur introuvable.")
    _check_can_manage(p, u)
    if u.id == p.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Vous ne pouvez pas désactiver votre propre compte.")
    if u.is_superadmin and _active_superadmins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Impossible de désactiver le dernier super administrateur.")
    u.is_active = False
    revoke_user_sessions(db, u.id)
    audit.log(db, user_id=p.id, action="deactivate", entity_type="user", entity_id=u.id, label=u.email, ip=client_ip(request))
    db.commit()
    return user_out(u)


@router.post("/users/{user_id}/reactivate", response_model=UserOut)
def reactivate_user(user_id: str, request: Request, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.get(User, parse_uuid(user_id))
    if not u:
        raise HTTPException(404, "Utilisateur introuvable.")
    _check_can_manage(p, u)
    u.is_active = True
    audit.log(db, user_id=p.id, action="reactivate", entity_type="user", entity_id=u.id, label=u.email, ip=client_ip(request))
    db.commit()
    return user_out(u)


@router.post("/users/{user_id}/reset-password", response_model=CredentialResult)
def reset_password(user_id: str, data: ResetRequest, request: Request, p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    u = db.get(User, parse_uuid(user_id))
    if not u:
        raise HTTPException(404, "Utilisateur introuvable.")
    _check_can_manage(p, u)
    revoke_user_sessions(db, u.id)
    if data.credential_mode == "invite":
        # Invalidate any previous unused links for this user.
        for t in db.scalars(select(AuthToken).where(AuthToken.user_id == u.id, AuthToken.used_at.is_(None))).all():
            t.used_at = utcnow()
    invite_url, temp_pwd, email_status = _issue_credentials(db, u, data.credential_mode, p.id, TokenPurpose.RESET)
    audit.log(db, user_id=p.id, action="reset_password", entity_type="user", entity_id=u.id, label=u.email,
              changes={"mode": data.credential_mode}, ip=client_ip(request))
    db.commit()
    return CredentialResult(user=user_out(u), mode=data.credential_mode, invite_url=invite_url,
                            temp_password=temp_pwd, email_status=email_status)


# ------------------------------------------------------------------ roles & permissions


@router.get("/permissions", response_model=list[PermissionOut], dependencies=[Depends(require("roles.manage"))])
def list_permissions():
    return [PermissionOut(code=c, module=m, label=label) for c, (m, label) in PERMISSIONS.items()]


@router.get("/roles", response_model=list[RoleOut])
def list_roles(p: Principal = Depends(require("users.manage")), db: Session = Depends(get_db)):
    return [role_out(r) for r in db.scalars(select(Role).order_by(Role.is_superadmin.desc(), Role.name)).all()]


def _set_permissions(db: Session, role: Role, codes: list[str], p: Principal) -> None:
    unknown = [c for c in codes if c not in PERMISSIONS]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Permissions inconnues : {', '.join(unknown)}")
    if not p.user.is_superadmin and set(codes) - p.permissions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vous ne pouvez pas accorder des permissions que vous ne possédez pas.")
    role.permissions = list(db.scalars(select(Permission).where(Permission.code.in_(codes))).all())


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(data: RoleIn, request: Request, p: Principal = Depends(require("roles.manage")), db: Session = Depends(get_db)):
    code = (normalize_key(data.name) or "role").replace(" ", "_")[:40]
    base, i = code, 2
    while db.scalar(select(Role).where(Role.code == code)):
        code, i = f"{base}_{i}", i + 1
    role = Role(code=code, name=data.name, description=data.description, is_system=False, is_superadmin=False)
    db.add(role)
    _set_permissions(db, role, data.permissions, p)
    db.flush()
    audit.log(db, user_id=p.id, action="create", entity_type="role", entity_id=role.id, label=role.name,
              changes={"permissions": sorted(data.permissions)}, ip=client_ip(request))
    db.commit()
    return role_out(role)


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: str, data: RoleIn, request: Request, p: Principal = Depends(require("roles.manage")), db: Session = Depends(get_db)):
    role = db.get(Role, parse_uuid(role_id))
    if not role:
        raise HTTPException(404, "Rôle introuvable.")
    if role.is_superadmin:
        raise HTTPException(status.HTTP_409_CONFLICT, "Le rôle super administrateur ne peut pas être modifié.")
    before = sorted(pp.code for pp in role.permissions)
    role.name = data.name
    role.description = data.description
    _set_permissions(db, role, data.permissions, p)
    # Sessions keep working; permissions are re-read from the role on every request.
    audit.log(db, user_id=p.id, action="update", entity_type="role", entity_id=role.id, label=role.name,
              changes={"permissions": {"old": before, "new": sorted(data.permissions)}}, ip=client_ip(request))
    db.commit()
    return role_out(role)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(role_id: str, request: Request, p: Principal = Depends(require("roles.manage")), db: Session = Depends(get_db)):
    role = db.get(Role, parse_uuid(role_id))
    if not role:
        raise HTTPException(404, "Rôle introuvable.")
    if role.is_system:
        raise HTTPException(status.HTTP_409_CONFLICT, "Les rôles système ne peuvent pas être supprimés.")
    if db.scalar(select(func.count()).select_from(User).where(User.role_id == role.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce rôle est attribué à des utilisateurs.")
    audit.log(db, user_id=p.id, action="delete", entity_type="role", entity_id=role.id, label=role.name, ip=client_ip(request))
    db.delete(role)
    db.commit()
