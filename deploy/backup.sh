#!/bin/sh
# Compressed logical backup of the database, with retention. Runs inside the "backup" container.
# Restore:  docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < backups/immo_YYYYmmdd_HHMMSS.dump
set -eu
STAMP=$(date +%Y%m%d_%H%M%S)
FILE="/backups/immo_${STAMP}.dump"
pg_dump -Fc -Z 9 -f "${FILE}.partial"
mv "${FILE}.partial" "$FILE"
find /backups -name 'immo_*.dump' -mtime "+${BACKUP_RETENTION_DAYS:-14}" -delete
echo "$(date -Iseconds) backup written: $FILE ($(du -h "$FILE" | cut -f1))"
