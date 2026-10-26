from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import AuditLog

SENSITIVE_FIELDS = {"password_hash", "token_hash", "csrf_token"}


def _jsonable(v: Any) -> Any:
    if isinstance(v, (Decimal,)):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def snapshot(obj, fields: list[str]) -> dict:
    return {f: _jsonable(getattr(obj, f)) for f in fields}


def diff(before: dict, after: dict) -> dict:
    return {k: {"old": before.get(k), "new": after.get(k)} for k in after if before.get(k) != after.get(k)}


def model_columns(obj) -> list[str]:
    return [c.key for c in inspect(obj).mapper.column_attrs if c.key not in SENSITIVE_FIELDS]


def log(
    db: Session,
    *,
    user_id,
    action: str,
    entity_type: str,
    entity_id=None,
    label: str | None = None,
    changes: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            entity_label=label[:200] if label else None,
            changes=changes or None,
            ip=ip,
        )
    )
