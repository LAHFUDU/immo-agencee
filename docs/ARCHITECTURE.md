# Architecture

## 1. Requirements analysis → system design

| Need | Design decision |
|---|---|
| Never lose a customer request | Requests are persisted before matching runs; there is no delete endpoint (close/archive only); the "waiting list" is a query (open requests without an active match), not a separate copy. |
| Find the right property automatically | A matching service runs synchronously in the same database transaction whenever a property or a request changes, and stores the result per pair in `matches`. |
| Never show unavailable properties as available | Eligibility (status) is a mandatory matching criterion; every status change goes through one function (`services.properties.change_status`) that deactivates matches, notifies and audits. The public API filters on `is_published AND status = 'available'`. |
| Agents see only what they are allowed to | Permission codes per role + row-level scopes applied in SQL for requests, customers, visits and deals; confidential property fields stripped in serializers. |
| Concurrent agents | Property rows are locked (`SELECT … FOR UPDATE OF properties`) during deal transitions; a partial unique index guarantees a single reservation per property. |
| Multi-worker / multi-server ready | No in-process state: sessions, rate limits, notifications and settings live in PostgreSQL; files go to a volume or S3. |
| Simple operations | One Compose file; background work is a small scheduler process (no broker needed). |

## 2. Data model

All business identifiers are UUIDs (non-guessable); human references come from PostgreSQL sequences
(`CLI-`, `DEM-`, `BIEN-`, `TRX-`). Money is `NUMERIC(14,2)`, surfaces `NUMERIC(10,2)`. Enumerations are
`VARCHAR` + `CHECK` constraints. Every important table has `created_at` / `updated_at` and ownership /
assignment columns.

```
roles ─< role_permissions >─ permissions
  │
users ─< user_sessions          users ─< auth_tokens (invite / reset, hashed, single use)
  │
  ├── assigned_agent ── customers ─< customer_requests ─< matches >─ properties >── owners
  │                         │              │                              │
  │                         │              ├─< tasks                      ├─< property_photos
  │                         │              ├─< visits >───────────────────┤
  │                         ├─< activities (contact history, also linked to requests/properties/deals)
  │                         └─< deals >──────────────────────────────────┘
  │                                │
  │                                ├─< offers
  │                                └── commission_rules
  ├─< notifications (unique per user + dedupe_key)
  ├─< saved_filters
  └─< audit_logs
property_categories, property_features   (configurable catalogue, FK targets)
app_settings (JSONB business configuration), rate_limit_events
```

Key constraints and indexes:

- `matches (request_id, property_id)` unique — one row per pair, updated in place, `is_active` flag keeps history.
- `deals` partial unique index on `property_id WHERE holds_reservation AND NOT reservation_override`.
- `notifications (user_id, dedupe_key)` unique — duplicate alerts are impossible even under concurrency
  (`INSERT … ON CONFLICT DO NOTHING`).
- Check constraints: price ≥ 0, surface > 0, `budget_min ≤ budget_max`, `surface_min ≤ surface_max`, commission rate 0–100.
- Composite indexes used by the matching engine: `(status, transaction_type, property_type, city_key)` on both
  `properties` and `customer_requests`; GIN index on `properties.features`.
- `city_key` / `neighborhood_key`: accent- and case-insensitive normalised keys.

Migrations: `backend/alembic/versions/`. The test suite verifies upgrade from an empty database, full downgrade,
re-upgrade and that the models and migrations are identical.

## 3. Access-control model

Permissions (`app/core/permissions.py`) are grouped by module; roles are sets of permissions editable by
administrators (`roles.manage`). The `super_admin` role implicitly holds all permissions and cannot be edited.

Default roles:

| Role | Profile |
|---|---|
| Super administrateur | Full access |
| Agent commercial | Restricted commercial access: own/new requests, own customers, inventory (no confidential fields), matches, visits, own deals |
| Responsable commercial | All requests/customers/visits/deals, assignment, exports, reports, commissions, confidential property data |
| Gestionnaire de biens | Inventory, owners, photos, documents, imports, publication |

Row-level scopes (applied in SQL, out-of-scope = 404):

| Data | Without `*_all` permission the user sees… |
|---|---|
| Requests | requests assigned to them, created by them, and **new unassigned** requests (so agents can pick them up) |
| Customers | customers assigned to/created by them, or having a request in their scope |
| Visits | visits where they are the agent or creator |
| Deals | deals where they are the agent or creator |

Field-level: `properties.view_confidential` controls address, GPS, owner, internal notes, confidential
documents and those fields in property history and search. Commission figures require `commissions.view`
(agents see the commission of their own deals).

## 4. Matching engine (`app/services/matching.py`)

```
evaluate(request, property, rules) → { eligible, score 0–100, category, met[], unmet[], failed[] }
```

Mandatory (any failure ⇒ `ineligible`, never an active match): status in eligible statuses, transaction type,
property type, city, currency, `price ≤ budget_max` (optional tolerance), `surface ≥ surface_min` (optional
tolerance), bedrooms (configurable), required features, neighbourhood if configured mandatory.

Score = 50 (all mandatory criteria met) + weighted preferences (default: neighbourhood 20, price within
range 10, surface within range 5, bathrooms 5, preferred features 10).

Category: `exact` only if score = 100 and nothing unmet; `strong` ≥ threshold (75); otherwise `partial`. Caps
prevent misleading labels: an unknown value (e.g. surface not filled in) or any unmet preference ⇒ at most
`strong`; neighbourhood mismatch or within-tolerance budget/surface overrun ⇒ at most `partial`.

Triggers:

- property created / matching fields changed / status changed ⇒ `refresh_for_property` (candidates: open
  requests with the same transaction, type and city) ⇒ notifications;
- request created / criteria or status changed ⇒ `refresh_for_request` (results shown to the user directly,
  so marked as surfaced without notification);
- matching rules changed ⇒ full recomputation (without notifications).

Notification de-duplication: each match stores `notified_signature = category|price`. An agent is notified
again only if that signature changes (material change) or if they press "Notifier" (explicit request).

## 5. Deal lifecycle (`app/services/deals.py`)

```
negotiation ──reserve──► reserved ──win──► won   (property → sold/rented, request → converted, competing deals → lost)
     │                      │
     └──── lose / cancel ───┴──► lost / cancelled (property → available again if no other active deal ⇒ re-matching)
```

Opening a deal moves an available property to *under negotiation*; a second reservation on the same
property requires `deals.override_reservation` and an explicit flag. Closed deals are read-only; offers and
activities are kept.

## 6. Background jobs (`app/services/jobs.py`)

Run by the `scheduler` container every `SCHEDULER_INTERVAL_SECONDS`: overdue follow-ups (one reminder per
follow-up date), tasks due within 30 minutes, visits within the configured window, and housekeeping (expired
sessions, old rate-limit rows). All notifications are de-duplicated, so the jobs are idempotent.
