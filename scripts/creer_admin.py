"""Creates the first super administrator directly in the hosted (Neon) database.

Usage (from the immo-agence folder):  backend\\.venv\\Scripts\\python scripts\\creer_admin.py
Nothing typed here is written to disk. Input is shown on screen (hidden input does not work in
every Windows terminal), so run it where nobody is looking over your shoulder.
"""

import io
import os
import sys
from pathlib import Path

backend = Path(__file__).resolve().parent.parent / "backend"
os.chdir(backend)
sys.path.insert(0, str(backend))

os.environ["DATABASE_URL"] = input("1) Colle le lien Neon (postgresql://...) puis Entree :\n> ").strip()
os.environ["ENV"] = "production"
os.environ.setdefault("SECRET_KEY", "cli-only-not-used-for-sessions-0000000000")
email = input("2) E-mail de l'administrateur :\n> ").strip()
name = input("3) Nom complet :\n> ").strip() or "Administrateur"
password = input("4) Mot de passe (12 caracteres min., majuscule, minuscule, chiffre) :\n> ")
if input("5) Retape le mot de passe :\n> ") != password:
    sys.exit("Les mots de passe ne correspondent pas. Relance le script.")

from app.cli import main  # noqa: E402 - settings must see the environment above

sys.stdin = io.StringIO(password + "\n")
sys.exit(main(["create-admin", "--email", email, "--name", name, "--password-stdin"]))
