# OldShop — second-hand marketplace

A full-stack marketplace for second-hand goods: buyers browse and check out (COD or PayPal),
sellers list products that go through moderation, moderators handle reports and bans,
admins manage staff, vouchers and feedback. Each checkout is risk-scored before payment.

**Stack:** FastAPI · SQLAlchemy · PostgreSQL (SQL-first schema, PL/pgSQL) · Angular 21 · PayPal Orders API ·
scikit-learn · Google Apps Script · Docker · Caddy · Nginx · Prometheus · Grafana · Loki/Promtail ⇄ ELK ·
GitHub Actions · SonarCloud

```mermaid
flowchart LR
  user((Browser)) -->|HTTPS| caddy[Caddy<br/>TLS, HTTP/3]
  caddy --> web[Nginx<br/>Angular SPA]
  web -->|/api, /media| api[FastAPI<br/>uvicorn workers]
  api --> pg[(PostgreSQL)]
  api -->|Orders v2| paypal[PayPal]
  api -->|signed webhook| gas[Apps Script<br/>Sheet helpdesk + email]
  api -.->|/metrics| prom[Prometheus] --> grafana[Grafana]
  api -.->|JSON logs| ship{{Promtail or Filebeat}}
  ship --> loki[Loki] --> grafana
  ship --> es[Elasticsearch] --> kibana[Kibana]
```

## Features

| Area | What it does |
|---|---|
| Catalogue | Category tree, search, sorting, product pages with images and reviews, view counter |
| Cart | Stock is reserved when an item is added (row-level `SELECT … FOR UPDATE`) and released on removal |
| Checkout | COD or PayPal (sandbox), vouchers (fixed / percentage, min order, usage cap), address book |
| Fraud check | Hard limit + IsolationForest score on every order; risky PayPal checkouts are blocked or delayed |
| Seller | Multipart listing with image upload, moderation status, order handling, dashboard stats |
| Moderation | Approve/reject listings, review reports (rating 0), trust score penalties, auto-ban, violation log |
| Admin | Moderator accounts, vouchers, system feedback, revenue/user stats |
| Contact | Form → PostgreSQL → HMAC-signed relay to a Google Apps Script helpdesk sheet ([details](integrations/google-apps-script/README.md)) |
| Ops | Health/readiness probes, Prometheus metrics, JSON logs with request ids, one-command deploy and log-stack switch |

## Repository layout

```
backend/                  FastAPI service
  app/api/                routers (v1) and dependencies (auth, role guards)
  app/core/               config, DB session, security, logging, domain enums and errors
  app/crud/               data access and business rules
  app/models/ schemas/    SQLAlchemy models, Pydantic models (split by domain)
  app/services/           PayPal, fraud scoring, mail, media storage, Apps Script relay
  scripts/init_db.py      idempotent bootstrap: create DB, load schema/seed once, copy seed images
  tests/                  integration tests against a real PostgreSQL
database/                 SQL source of truth: schema, functions/triggers, seed data, seed images
frontend/                 Angular SPA + Nginx config
integrations/google-apps-script/   contact relay (clasp project)
deploy/                   production compose files, Caddy, Prometheus, Grafana, Loki, ELK, ops scripts
docs/deployment.md        VPS runbook
```

## Run locally

**With Docker** (everything, seeded):

```bash
docker compose up --build
# shop: http://localhost:8080   API docs: http://localhost:8000/api/docs
```

**Without Docker** (hot reload):

```bash
# database
createdb oldshop && (cd database && psql -d oldshop -f init.sql)

# backend
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                               # adjust DB credentials
uvicorn app.main:app --reload

# frontend
cd frontend && npm ci && npm start                 # http://localhost:4200
```

Seeded accounts: `admin@oldshop.com / admin123`, `mod1@oldshop.com / mod123`,
`user1@gmail.com … user11@gmail.com / user123`.

## Tests

The backend suite exercises the real API against PostgreSQL loaded with the seed data
(auth, RBAC, cart stock reservation, orders, vouchers, fraud rule, moderation, uploads, contact relay, metrics).

```bash
createdb oldshop_test && (cd database && psql -d oldshop_test -f init.sql)
cd backend
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/oldshop_test pytest
ruff check . && ruff format --check .
```

CI runs the same steps on every push, builds the Angular app, and builds both Docker images on pull requests.

## Deployment

**Day 2 data stack (local, separate volumes/ports):** PostgreSQL + MongoDB + MinIO,
with optional replication profile. See [distribution strategy and commands](docs/design/02_distribution_strategy.md)
and [Day 2 findings](docs/DAY2_FINDINGS_LOG.md), including the MongoDB 8/kernel compatibility exception.
This stack retains the baseline schema; partitioning and ETL are later milestones.

Production runs on a single VPS with Docker Compose; see **[docs/deployment.md](docs/deployment.md)**.

- `git push` to `main` → CI → images pushed to GHCR → SSH deploy with the commit tag (rollback = redeploy an older tag)
- Caddy terminates TLS for the shop, Grafana and Kibana sub-domains
- Metrics: Prometheus scrapes the API, PostgreSQL and the host; Grafana dashboards and alert rules are provisioned
- Logs: Promtail → Loki by default; `deploy/scripts/switch-logging.sh elk` swaps in Filebeat → Elasticsearch → Kibana
  without restarting the application (both read the same Docker log files)

## Notes on design choices

- **SQL-first schema.** Tables, indexes, triggers and seed data live in `database/` and are loaded once by
  `scripts/init_db.py`; the ORM maps onto them instead of generating them. Database tuning is passed to the
  Postgres container as flags, never via `ALTER SYSTEM` from an init script.
- **Stock reservation in the cart** rather than at payment keeps the "last item" race in one place, guarded by row locks.
- **Fraud model is optional at runtime.** Artifacts are mounted into the container; without them the service falls back
  to the hard business rule so dev and CI need no binary files.
- **The Apps Script URL never reaches the browser.** The backend signs each relay with HMAC-SHA256 and a timestamp,
  since Apps Script web apps cannot read request headers.

**Day 3 MongoDB / media:** six strict document contracts, idempotent schema/index provisioning,
private MinIO buckets and LocalStorage/MinioStorage behind existing `/media/...` URLs.
See [JSON and storage design](docs/design/03_json_design.md) and
[Day 3 findings](docs/DAY3_FINDINGS_LOG.md). Run `bash deploy/scripts/test-day3.sh`
after building/provisioning the data stack; it creates a separate PostgreSQL test database.
Mongo data synchronization is scheduled for Day 5.
