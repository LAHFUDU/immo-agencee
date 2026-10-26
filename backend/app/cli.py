"""Management commands.

  python -m app.cli init                      # reference data (roles, permissions, types...) — idempotent
  python -m app.cli create-admin --email a@b.c --name "Nom"   # password prompted (or --password-stdin)
  python -m app.cli seed-demo                 # DEVELOPMENT ONLY: sample agents, properties, requests
  python -m app.cli run-jobs                  # run reminders once
  python -m app.cli scheduler                 # run reminders forever (every SCHEDULER_INTERVAL_SECONDS)
"""

import argparse
import getpass
import logging
import sys
import time

from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_password, validate_password_strength
from app.models import Role, User
from app.services.bootstrap import seed_reference_data

log = logging.getLogger("immo.cli")


def cmd_init(_args) -> int:
    with SessionLocal() as db:
        seed_reference_data(db)
        db.commit()
    print("Données de référence initialisées.")
    return 0


def cmd_create_admin(args) -> int:
    email = args.email.strip().lower()
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Mot de passe : ")
        if getpass.getpass("Confirmation : ") != password:
            print("Les mots de passe ne correspondent pas.", file=sys.stderr)
            return 1
    if err := validate_password_strength(password):
        print(err, file=sys.stderr)
        return 1
    with SessionLocal() as db:
        seed_reference_data(db)
        role = db.scalar(select(Role).where(Role.code == "super_admin"))
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user and not args.update:
            print("Un compte existe déjà avec cet e-mail (utilisez --update pour le promouvoir et changer son mot de passe).", file=sys.stderr)
            return 1
        if user is None:
            user = User(email=email, full_name=args.name, role_id=role.id, is_agent=False)
            db.add(user)
        user.role_id = role.id
        user.password_hash = hash_password(password)
        user.is_active = True
        user.must_change_password = False
        db.commit()
    print(f"Super administrateur prêt : {email}")
    return 0


def cmd_seed_demo(args) -> int:
    if settings.ENV == "production" and not args.force:
        print("Refusé : les données de démonstration ne doivent pas être chargées en production.", file=sys.stderr)
        return 1
    from app.services.demo import seed_demo

    with SessionLocal() as db:
        seed_reference_data(db)
        info = seed_demo(db)
        db.commit()
    print(info)
    return 0


def cmd_run_jobs(_args) -> int:
    from app.services.jobs import run_all

    with SessionLocal() as db:
        print(run_all(db))
    return 0


def cmd_scheduler(_args) -> int:
    from app.services.jobs import run_all

    log.info("scheduler started, interval=%ss", settings.SCHEDULER_INTERVAL_SECONDS)
    while True:
        try:
            with SessionLocal() as db:
                log.info("jobs: %s", run_all(db))
        except Exception:  # noqa: BLE001 - keep the loop alive; errors are logged
            log.exception("scheduled jobs failed")
        time.sleep(settings.SCHEDULER_INTERVAL_SECONDS)


def main(argv=None) -> int:
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Administrateur")
    p.add_argument("--password-stdin", action="store_true", help="lire le mot de passe sur l'entrée standard")
    p.add_argument("--update", action="store_true", help="mettre à jour un compte existant")
    p.set_defaults(fn=cmd_create_admin)
    p = sub.add_parser("seed-demo")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_seed_demo)
    sub.add_parser("run-jobs").set_defaults(fn=cmd_run_jobs)
    sub.add_parser("scheduler").set_defaults(fn=cmd_scheduler)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
