"""Periodic jobs (run by `python -m app.cli scheduler`): reminders and housekeeping.
All notifications are de-duplicated, so running the jobs more often than needed is harmless."""

import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import CustomerRequest, Task, UserSession, Visit
from app.models.enums import OPEN_REQUEST_STATUSES, TaskStatus, VisitStatus
from app.services import rate_limit
from app.services.app_settings import get_setting
from app.services.notifications import notify, users_with_permission

log = logging.getLogger("immo.jobs")


def overdue_follow_ups(db: Session) -> int:
    if not get_setting(db, "reminders")["overdue_follow_up_enabled"]:
        return 0
    now = utcnow()
    rows = db.scalars(
        select(CustomerRequest).where(
            CustomerRequest.status.in_(OPEN_REQUEST_STATUSES),
            CustomerRequest.next_follow_up_at < now,
            # one reminder per follow-up date
            (CustomerRequest.follow_up_reminded_at.is_(None)) | (CustomerRequest.follow_up_reminded_at < CustomerRequest.next_follow_up_at),
        )
    ).unique().all()
    managers = None
    for r in rows:
        if r.assigned_agent_id:
            recipients = [r.assigned_agent_id]
        else:
            managers = managers if managers is not None else users_with_permission(db, "requests.assign")
            recipients = managers
        notify(db, recipients, type="follow_up_overdue", title=f"Relance en retard : {r.reference} — {r.customer.full_name}",
               body=f"Relance prévue le {r.next_follow_up_at:%d/%m/%Y %H:%M}", link=f"/app/requests/{r.id}",
               entity_type="request", entity_id=r.id, dedupe_key=f"followup:{r.id}:{r.next_follow_up_at.isoformat()}")
        r.follow_up_reminded_at = now
    return len(rows)


def due_tasks(db: Session) -> int:
    now = utcnow()
    rows = db.scalars(select(Task).where(Task.status == TaskStatus.OPEN, Task.due_at <= now + timedelta(minutes=30), Task.reminded_at.is_(None))).unique().all()
    for t in rows:
        notify(db, [t.assigned_to_id], type="task_due", title=f"Tâche à échéance : {t.title}",
               body=f"Échéance {t.due_at:%d/%m/%Y %H:%M}", link=f"/app/requests/{t.request_id}" if t.request_id else "/app/visits?tab=tasks",
               entity_type="task", entity_id=t.id, dedupe_key=f"task_due:{t.id}:{t.due_at.isoformat()}")
        t.reminded_at = now
    return len(rows)


def upcoming_visits(db: Session) -> int:
    hours = int(get_setting(db, "reminders")["visit_reminder_hours"])
    now = utcnow()
    rows = db.scalars(select(Visit).where(
        Visit.status == VisitStatus.SCHEDULED, Visit.scheduled_at > now, Visit.scheduled_at <= now + timedelta(hours=hours),
        Visit.reminder_sent_at.is_(None))).unique().all()
    for v in rows:
        notify(db, [v.agent_id], type="visit_upcoming", title=f"Visite à venir : {v.property.reference} — {v.customer.full_name}",
               body=f"{v.scheduled_at:%d/%m/%Y %H:%M}", link="/app/visits", entity_type="visit", entity_id=v.id,
               dedupe_key=f"visit_upcoming:{v.id}:{v.scheduled_at.isoformat()}")
        v.reminder_sent_at = now
    return len(rows)


def housekeeping(db: Session) -> None:
    db.execute(delete(UserSession).where(UserSession.expires_at < utcnow() - timedelta(days=30)))
    rate_limit.purge_old(db)


def run_all(db: Session) -> dict:
    out = {"follow_ups": overdue_follow_ups(db), "tasks": due_tasks(db), "visits": upcoming_visits(db)}
    housekeeping(db)
    db.commit()
    return out
