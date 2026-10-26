#!/bin/sh
# Usage (on the server, from the project directory):  sh deploy/restore.sh backups/immo_20260101_030000.dump
# Stops the API, restores the dump into the database, restarts. Uploaded files live in the "uploads" volume (back it up separately).
set -eu
DUMP="${1:?usage: deploy/restore.sh <dump file>}"
. ./.env
docker compose stop backend scheduler
docker compose exec -T db pg_restore -U "${POSTGRES_USER:-immo}" -d "${POSTGRES_DB:-immo}" --clean --if-exists --no-owner < "$DUMP"
docker compose start backend scheduler
echo "Restored $DUMP"
