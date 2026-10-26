#!/usr/bin/env bash
# Starts a project-local PostgreSQL cluster for development (port 5434, trust auth on localhost only).
# Needs the PostgreSQL server binaries (initdb, pg_ctl) on PATH, or set PGBIN.
#   bash scripts/dev-db.sh start | stop | status
set -euo pipefail
cd "$(dirname "$0")/.."
PGBIN="${PGBIN:-}"
bin() { if [ -n "$PGBIN" ]; then echo "$PGBIN/$1"; else echo "$1"; fi; }
DATA=.pgdata
PORT=5434

case "${1:-start}" in
  start)
    if [ ! -d "$DATA" ]; then
      "$(bin initdb)" -D "$DATA" -U immo -A trust -E UTF8 --locale=C >/dev/null
    fi
    "$(bin pg_ctl)" -D "$DATA" -o "-p $PORT -c listen_addresses=localhost" -l "$DATA/server.log" start
    sleep 2
    "$(bin createdb)" -h localhost -p $PORT -U immo immo 2>/dev/null || true
    "$(bin createdb)" -h localhost -p $PORT -U immo immo_test 2>/dev/null || true
    echo "PostgreSQL ready: postgresql+psycopg://immo@localhost:$PORT/immo (tests: .../immo_test)"
    ;;
  stop) "$(bin pg_ctl)" -D "$DATA" stop ;;
  status) "$(bin pg_ctl)" -D "$DATA" status ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
