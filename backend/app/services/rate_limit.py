from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import RateLimitEvent

# Tests disable rate limiting globally (they fire many requests from one client).
ENABLED = True


def count_recent(db: Session, key: str, window: timedelta) -> int:
    since = utcnow() - window
    return db.scalar(select(func.count()).where(RateLimitEvent.key == key, RateLimitEvent.created_at >= since)) or 0


def hit(db: Session, key: str) -> None:
    db.add(RateLimitEvent(key=key))
    db.commit()


def check(db: Session, key: str, limit: int, window: timedelta) -> None:
    if ENABLED and count_recent(db, key, window) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Trop de tentatives. Veuillez réessayer plus tard.",
            headers={"Retry-After": str(int(window.total_seconds()))},
        )


def clear(db: Session, key: str) -> None:
    db.execute(delete(RateLimitEvent).where(RateLimitEvent.key == key))
    db.commit()


def purge_old(db: Session, older_than: timedelta = timedelta(days=2)) -> int:
    res = db.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at < utcnow() - older_than))
    db.commit()
    return res.rowcount or 0
