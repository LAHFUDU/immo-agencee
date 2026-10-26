# Immo Agence — Real estate agency management platform

Full-stack web application for a real estate agency: customer requests (leads), property inventory, an
automatic **matching engine**, CRM, visits, sales & rental transactions with commissions, notifications,
reports, role-based access control and an optional public property website.

- **Interface:** French by default (i18n layer ready for Arabic RTL and English), responsive (phone / tablet / desktop).
- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Argon2id, server-side sessions.
- **Frontend:** React 19, TypeScript, Tailwind CSS 4, TanStack Query, Recharts.
- **Deployment:** Docker Compose (PostgreSQL + API + scheduler + Caddy with automatic HTTPS + nightly backups).

---

## Contents

1. [Features](#features)
2. [Architecture](#architecture)
3. [Quick start with Docker](#quick-start-with-docker)
4. [Native development setup](#native-development-setup)
5. [Configuration](#configuration)
6. [Tests](#tests)
7. [Production deployment (VPS)](#production-deployment-vps)
8. [Backups & restore](#backups--restore)
9. [Security](#security)
10. [Business rules & assumptions](#business-rules--assumptions)
11. [Feature checklist & known limitations](#feature-checklist--known-limitations)

Detailed data model, access-control model and matching algorithm: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Interactive API documentation (OpenAPI): `/api/docs` (Swagger) and `/api/redoc` on any running instance.

---

## Features

| Module | What it does |
|---|---|
| **Customer requests** | Reference numbers (`DEM-2026-00042`), full search criteria (type, purchase/rental, budget, city, one or several neighbourhoods, surface, rooms, mandatory and preferred features), priority, 9 statuses, follow-up date, assignment, interaction history, tasks. **A request is always saved, even when nothing matches.** |
| **Waiting list** | Open requests with no matching property. Re-evaluated automatically whenever a property is added or changed; the assigned agent (or managers, if unassigned) is notified when a match appears. |
| **Properties** | Full inventory with confidential fields (address, owner, internal notes, documents), photos, documents, 7 availability statuses, publication flag, history of every change, bulk status update, CSV / Excel import with validation, duplicate detection and error report, CSV / Excel export. |
| **Matching engine** | Score 0–100, categories *exact / strong / partial*, mandatory vs optional criteria, per-match explanation (met / unmet / failed), near misses shown separately as *non conforme*, configurable rules, de-duplicated notifications. |
| **CRM** | Customer profiles, multiple requests per customer, contact history (calls, meetings, e-mails, WhatsApp, visits, offers), tasks & reminders, duplicate detection (phone numbers normalised, e.g. `+212 6…` = `06…`). |
| **Visits** | Scheduling from a matching property, double-booking protection per agent, visit reports with customer feedback, reminders. |
| **Sales & rentals** | Deals with offers / counter-offers, reservation (one reservation per property, admin override required for a second one), win / lose / cancel, automatic property & request status updates, configurable commission rules, history preserved (closed deals are read-only). |
| **Notifications** | In-app notification centre (read/unread, per user, de-duplicated). E-mail via SMTP when configured — never pretends to send otherwise. |
| **Dashboard & reports** | KPIs, charts, agent performance, requests per month, inventory by city/type, sold/rented over time, waiting list analysis, time to first contact, time to close, conversion rate, revenue & commissions, reasons for failure — all computed from real records; CSV / Excel export. |
| **Administration** | Users (invitation link or temporary password, reset, deactivate/reactivate), roles with granular permissions, settings (matching rules, deal rules, reminders, public site, property types, features, commission rules), audit log. |
| **Public website** (optional) | Property search & detail pages (published **and** available properties only, whitelisted fields), contact form and "submit your search" form feeding the same request system, with honeypot, consent and rate limiting. Can be disabled in Settings. |

---

## Architecture

```
            ┌────────────────────────────── Docker host (VPS) ───────────────────────────────┐
 Browser ──►│ web: Caddy :80/:443 ── static React build (/)                                  │
  HTTPS     │                     └─ reverse proxy /api/* ──► backend: FastAPI (gunicorn)    │
            │                                                   │        │                   │
            │ scheduler: reminders job loop ────────────────────┤        ├── uploads volume  │
            │                                                   ▼        │   (or S3 bucket)  │
            │ backup: nightly pg_dump ──► ./backups      db: PostgreSQL (not exposed)        │
            └────────────────────────────────────────────────────────────────────────────────┘
```

```
immo-agence/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (auth, users, properties, requests, crm, deals, reports, system, public)
│   │   ├── core/           # config, database, security (Argon2id), permissions catalogue, auth dependencies
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # matching engine, deals lifecycle, imports, notifications, storage, jobs, audit…
│   │   ├── cli.py          # init / create-admin / seed-demo / run-jobs / scheduler
│   │   └── main.py
│   ├── alembic/            # migrations
│   └── tests/              # pytest suite (runs against a real PostgreSQL test database)
├── frontend/
│   ├── src/                # React app (internal app under /app, public site under /)
│   ├── Caddyfile           # web server + reverse proxy + security headers
│   └── Dockerfile
├── deploy/                 # backup.sh, restore.sh
├── scripts/dev-db.sh       # optional project-local PostgreSQL for development
├── docker-compose.yml
└── .env.example
```

---

## Quick start with Docker

Requirements: Docker Engine 24+ with the Compose plugin.

```bash
cp .env.example .env
```

Edit `.env`: set `SECRET_KEY` and `POSTGRES_PASSWORD` to long random values
(`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Keep `SITE_ADDRESS=:80`,
`PUBLIC_URL=http://localhost` and `COOKIE_SECURE=false` for a local test.

```bash
docker compose up -d --build
```

Migrations and reference data (roles, permissions, property types, features, default commission rules)
are applied automatically by the `migrate` service before the API starts. Then create the first
administrator (the password is asked interactively and never stored in clear text):

```bash
docker compose run --rm backend python -m app.cli create-admin --email you@your-agency.com --name "Your Name"
```

Open <http://localhost> (public site) and <http://localhost/login> (agency area).

Optional, **development only** — sample agents, properties and requests (random passwords are printed once):

```bash
docker compose run --rm -e ENV=development backend python -m app.cli seed-demo
```

---

## Native development setup

Requirements: Python 3.12+, Node.js 20+, PostgreSQL 15+.

**1. Database.** Either use an existing PostgreSQL server (create a database and a user), or start a
throw-away project-local cluster (port 5434):

```bash
PGBIN="/c/Program Files/PostgreSQL/18/bin" bash scripts/dev-db.sh start
```

**2. Backend.**

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt
cp .env.example .env
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.cli init
.venv/Scripts/python -m app.cli create-admin --email admin@example.com --name "Admin"
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

On Linux/macOS use `.venv/bin/...` instead of `.venv/Scripts/...`. Edit `DATABASE_URL` in `backend/.env` if
you do not use the local cluster.

**3. Frontend** (Vite proxies `/api` to `localhost:8000`, so cookies stay same-origin):

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

---

## Configuration

All configuration comes from environment variables (`.env`); nothing secret is hard-coded.

| Variable | Default | Purpose |
|---|---|---|
| `ENV` | `development` | `production` enforces a strong `SECRET_KEY`. |
| `SECRET_KEY` | — | Required in production (≥ 32 chars). |
| `DATABASE_URL` | local dev URL | `postgresql+psycopg://user:pass@host:5432/db` (set automatically by Compose). |
| `FRONTEND_URL` / `PUBLIC_URL` | `http://localhost:5173` | Used to build invitation / reset links. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins (same origin in production). |
| `COOKIE_SECURE` | `false` | **`true` in production (HTTPS).** |
| `SESSION_TTL_HOURS` | `12` | Sliding session lifetime. |
| `LOGIN_MAX_FAILURES` / `LOGIN_WINDOW_MINUTES` | `5` / `15` | Login rate limiting per account + IP. |
| `TRUST_PROXY_HEADERS` | `false` | `true` behind the reverse proxy (Compose sets it). |
| `STORAGE_BACKEND` | `local` | `local` (volume) or `s3` (+ `S3_*` variables, any S3-compatible provider). |
| `MAX_UPLOAD_MB` | `15` | Per-file limit; real file type checked from content. |
| `SMTP_*` | empty | Optional e-mail delivery (invitations, match / follow-up notifications). |
| `SCHEDULER_INTERVAL_SECONDS` | `300` | Reminder job frequency. |
| `SITE_ADDRESS` | `:80` | Caddy site address — your domain name enables automatic HTTPS. |

Business rules (matching, deals, reminders, public site, catalogue, commissions) are edited in the
application under **Paramètres** and stored in the database.

---

## Tests

### Backend (pytest, real PostgreSQL)

The suite rebuilds a dedicated database from the Alembic migrations at start-up. For safety it **refuses to
run unless the database name ends with `_test`**, so production data cannot be touched.

```bash
cd backend
# default: postgresql+psycopg://immo@localhost:5434/immo_test
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/immo_test .venv/Scripts/python -m pytest
```

Covered workflows (46 tests): employee creation (temporary password and invitation link), restricted users
blocked from admin operations, privilege-escalation prevention, CSRF, session revocation, login rate limiting,
agent request creation/update and row-level isolation, request saved without matches, waiting list,
automatic matching on new properties, over-budget never exact, unavailable properties excluded, no duplicate
notifications (re-notified only on material change or explicit request), status changes reflected everywhere,
deal lifecycle with history preserved, double-reservation protection, commission rules, CSV/XLSX import
validation & duplicates, combined filters, confidential data hidden from unauthorised users (API, search,
history, documents), public website exposure rules and anti-spam, dashboard/report figures from real data,
CSV formula-injection protection, reminder jobs, **migrations from a clean database (upgrade → downgrade →
upgrade, no model drift)** and **the documented start-up procedure (migrate → init → create-admin → start
server → health check → login)**.

### Frontend (Vitest)

```bash
cd frontend
npm test            # unit tests (API client, CSRF header, routing guards, formatting)
npx tsc --noEmit -p .
npm run build
```

---

## Production deployment (VPS)

A small VPS is enough to start (2 vCPU, 4 GB RAM, 40 GB SSD — e.g. Hetzner, OVHcloud, Scaleway,
DigitalOcean). Once deployed, the application runs on the server and does not depend on your computer.

1. **DNS:** create an `A` record (and `AAAA` if IPv6) `agence.example.com → <server IP>`.
2. **Server** (Ubuntu 24.04 LTS):
   ```bash
   sudo apt update && sudo apt -y upgrade
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER   # log out / in afterwards
   sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw enable
   ```
   Use SSH keys and disable password login (`PasswordAuthentication no` in `/etc/ssh/sshd_config`).
   Note: Docker-published ports bypass UFW, which is why **only Caddy (80/443) publishes ports** — PostgreSQL
   is reachable only inside the Docker network.
3. **Application:**
   ```bash
   git clone <your repository> immo-agence && cd immo-agence
   cp .env.example .env && chmod 600 .env
   ```
   In `.env` set `ENV=production`, strong `SECRET_KEY` and `POSTGRES_PASSWORD`, and:
   ```
   SITE_ADDRESS=agence.example.com
   PUBLIC_URL=https://agence.example.com
   COOKIE_SECURE=true
   ```
   Optionally configure `SMTP_*` (transactional e-mail provider) and `STORAGE_BACKEND=s3` + `S3_*`.
4. **Start:**
   ```bash
   docker compose up -d --build
   docker compose run --rm backend python -m app.cli create-admin --email you@agency.com --name "Your Name"
   ```
   Caddy obtains and renews the Let's Encrypt certificate automatically (ports 80 and 443 must be reachable).
5. **Verify:** `curl https://agence.example.com/api/health/ready` → `{"status":"ok","database":"ok"}`, then log in.

**Updates:** `git pull && docker compose up -d --build` — pending migrations run automatically before the API restarts.

**Logs & monitoring:** `docker compose logs -f backend web scheduler`. The API logs one line per request with a
request id (also returned in the `X-Request-ID` header); unhandled errors are logged with a stack trace and the
user gets a generic message with the request id. Point an uptime monitor (UptimeRobot, Better Stack…) at
`/api/health/ready`. For error aggregation, a Sentry DSN can be added in `app/main.py` (not enabled by default).

**Platform alternative:** any host that runs containers works (e.g. a managed PostgreSQL + a container
service): build `backend/` and `frontend/` images, run `alembic upgrade head && python -m app.cli init` as a
release command, and route `/api/*` to the backend and everything else to the frontend.

---

## Backups & restore

- The `backup` service writes a compressed `pg_dump` to `./backups/` every 24 h and keeps
  `BACKUP_RETENTION_DAYS` (default 14). **Copy `./backups` off the server** (e.g. `rclone` to object storage,
  or your provider's snapshot feature) — a backup on the same disk does not protect against server loss.
- Uploaded files live in the `uploads` volume (or your S3 bucket). Back up the volume with:
  ```bash
  docker run --rm -v immo-agence_uploads:/data -v "$PWD/backups":/backup alpine tar czf /backup/uploads_$(date +%F).tgz -C /data .
  ```
- **Restore** the database: `sh deploy/restore.sh backups/immo_YYYYmmdd_HHMMSS.dump`. Test a restore on a
  separate machine periodically.
- On-demand dump: `docker compose exec backup sh /backup.sh`.

---

## Security

- Passwords hashed with **Argon2id** (argon2-cffi), strength policy (≥ 10 chars, 3 character classes),
  transparent re-hashing when parameters change.
- **Server-side sessions**: random 256-bit token in an `HttpOnly`, `SameSite=Lax` (and `Secure` in production)
  cookie; only its SHA-256 is stored. Sessions are revoked on logout, password change/reset, role change and
  deactivation.
- **CSRF**: every state-changing request must carry the per-session token in `X-CSRF-Token`.
- **Authorisation enforced on the server for every endpoint** (permission checks + row-level scopes). Records
  outside a user's scope return 404, so their existence is not revealed. Confidential property fields
  (address, owner, internal notes, documents, GPS) are removed from responses, search and history for users
  without `properties.view_confidential`. Hiding buttons in the UI is only a convenience.
- No privilege escalation: a non-super-admin cannot grant permissions they do not hold or modify a super admin;
  the last super admin cannot be removed.
- Rate limiting (stored in PostgreSQL, so it works across workers): login, token links, public forms.
- Uploads: size limit, real type detected from file content (JPEG/PNG/WebP/PDF only), random storage keys,
  files served only through permission-checked endpoints with `nosniff`.
- Validation with Pydantic on every input; SQL exclusively through SQLAlchemy bound parameters; `LIKE`
  wildcards escaped; spreadsheet formula injection neutralised in exports.
- Security headers (CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy) set by Caddy and the API.
- Audit log of logins (including failures), creations, updates (with before/after values), status changes,
  exports, permission and setting changes.
- Secrets only in environment variables; `.env` is git-ignored; PostgreSQL is not exposed to the internet.
- **Data retention:** requests and deals are never hard-deleted (archived/closed instead), which preserves
  history. To honour a deletion request (e.g. Moroccan law 09-08 / GDPR), an administrator can archive the
  customer and anonymise the contact fields; a dedicated anonymisation command is listed under limitations.

---

## Business rules & assumptions

Ambiguous rules were given safe defaults and made configurable (Paramètres → Moteur de correspondance /
Agence & fonctionnement):

| Rule | Default | Configurable |
|---|---|---|
| Property statuses eligible for matching | `available` only | yes |
| Budget above `budget_max` | excluded (tolerance 0 %) | tolerance %; within tolerance → at best *partial* |
| Surface below `surface_min` | excluded | tolerance % |
| Neighbourhood mismatch (same city) | shown as *partial* with the gap explained | can be made mandatory |
| Minimum bedrooms | mandatory | yes |
| Bathrooms, preferred features, price within range | contribute to the score | weights |
| Notification threshold | *strong* and *exact* matches | exact / strong / partial |
| Opening a deal on an available property | property → *under negotiation* (leaves the match list) | yes |
| Winning a deal | competing open deals on the property closed as lost | yes |
| Commission | Sale 2.5 %, rental 100 % of one month (starting points) | rules by transaction, type, price band, priority, fixed amount; manual override per deal |
| Currency | MAD; no currency conversion — a property in another currency never matches | default currency |

Other decisions: a customer request can list several neighbourhoods separated by commas; city and neighbourhood
comparisons ignore case and accents (`Salé` = `sale`); public-site submissions with a phone/e-mail already known
are attached to the existing customer (no duplicate) and flagged for verification in the history.

---

## Feature checklist & known limitations

**Implemented and tested** — see the module table above and the test list. The application has been run end to end
locally (public site, login, dashboard, request created with no match → waiting list → property added through the
form → exact match 100/100 shown on the request and the assigned agent notified once).

**Known limitations / next steps**

- **Not deployed to a public URL by this work**: deployment files and instructions are provided and the Compose
  stack is configured, but no server or domain was provisioned, and the Docker images were not built in the
  development environment (Docker was not installed there). Run the steps in [Production deployment](#production-deployment-vps).
- WhatsApp / SMS notifications are not integrated (the notification layer has a single place to add a provider;
  the UI shows them as "not configured").
- E-mail is sent synchronously during the request when SMTP is configured (15 s timeout); for high volumes move
  sending to a queue (e.g. Celery/RQ with Redis).
- Only French UI strings are complete; navigation and enum labels go through the i18n layer, but some page text
  is still inline French and would need extracting for Arabic/English.
- No customer anonymisation command yet (archive + manual edit of contact fields in the meantime).
- No map view (coordinates are stored and linked to OpenStreetMap).
- Photo thumbnails are not generated (originals are served; 15 MB limit).
- Commissions are calculated per deal; there is no split between several agents.
