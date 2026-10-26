import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Notification, Role, User, role_permissions
from app.models.auth import Permission

EMAIL_TYPES = {"match_found", "request_assigned", "follow_up_overdue", "visit_upcoming"}


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID | None],
    *,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    exclude_user_id: uuid.UUID | None = None,
) -> int:
    """Insert one notification per distinct active user. Duplicate (user, dedupe_key) pairs are ignored
    atomically via ON CONFLICT DO NOTHING. Returns the number of notifications actually created."""
    ids = {u for u in user_ids if u is not None and u != exclude_user_id}
    if not ids:
        return 0
    active = db.scalars(select(User).where(User.id.in_(ids), User.is_active.is_(True))).all()
    created = 0
    for user in active:
        stmt = (
            insert(Notification)
            .values(
                id=uuid.uuid4(),
                user_id=user.id,
                type=type,
                title=title[:200],
                body=body,
                link=link,
                entity_type=entity_type,
                entity_id=entity_id,
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(constraint="uq_notifications_user_dedupe")
            .returning(Notification.id)
        )
        new_id = db.execute(stmt).scalar()
        if new_id is None:
            continue
        created += 1
        if type in EMAIL_TYPES and settings.smtp_configured:
            from app.services.email import send_email

            status = send_email(user.email, title, f"{body or ''}\n\n{settings.FRONTEND_URL}{link or ''}")
            db.get(Notification, new_id).email_status = status
    return created


def users_with_permission(db: Session, code: str) -> list[uuid.UUID]:
    """Active users holding a permission (super admins always included)."""
    q = (
        select(User.id)
        .join(Role, Role.id == User.role_id)
        .outerjoin(role_permissions, role_permissions.c.role_id == Role.id)
        .outerjoin(Permission, Permission.id == role_permissions.c.permission_id)
        .where(User.is_active.is_(True))
        .where((Role.is_superadmin.is_(True)) | (Permission.code == code))
        .distinct()
    )
    return list(db.scalars(q).all())
