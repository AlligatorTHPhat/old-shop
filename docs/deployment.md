# Deployment runbook (single VPS)

The separate Day 2 local data stack uses `deploy/docker-compose.distributed.yml` and
`deploy/.env.data`, not this production stack. See
[Day 2 strategy/runbook](design/02_distribution_strategy.md) for setup, replication profile,
ports, preserved volumes and MongoDB kernel compatibility findings.

Target: Ubuntu 22.04/24.04, 2 vCPU / 4 GB RAM recommended (2 GB is enough with the Loki stack).

## 1. DNS

Point three A records at the VPS: `shop.example.com`, `grafana.shop.example.com`, `kibana.shop.example.com`.
Caddy obtains Let's Encrypt certificates for them on first start.

## 2. Prepare the server (once)

```bash
ssh root@VPS
git clone https://github.com/<you>/<repo>.git /opt/oldshop
/opt/oldshop/deploy/scripts/bootstrap-vps.sh
```

The script installs Docker, configures log rotation, creates a `deploy` user (in the `docker` group),
enables the firewall (22/80/443 only) and fail2ban, adds swap, and sets `vm.max_map_count` for Elasticsearch.

## 3. Configure

```bash
su - deploy
cd /opt/oldshop
cp deploy/.env.example deploy/.env
nano deploy/.env          # every CHANGE_ME, domains, PayPal/SMTP/Apps Script values
```

Optional: copy `fraud_model.joblib` and `scaler.joblib` into `deploy/ml/` to enable ML scoring.

## 4. First deploy

```bash
# only if the GHCR packages are private:
echo <PAT with read:packages> | docker login ghcr.io -u <github-user> --password-stdin

deploy/scripts/deploy.sh          # or BUILD=1 deploy/scripts/deploy.sh to build on the server
```

On first start the backend container creates the schema, loads the seed data and copies the seed images
into the media volume. Later starts detect the existing schema and skip it.

## 5. Continuous deployment

Add these **repository secrets** (Settings → Secrets and variables → Actions) and a `production` environment:

| Secret | Value |
|---|---|
| `VPS_HOST` | server IP or hostname |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | private key whose public part is in `/home/deploy/.ssh/authorized_keys` |
| `VPS_PORT` | optional, defaults to 22 |
| `SONAR_TOKEN` | optional, enables the SonarCloud job |

Every green CI run on `main` builds `oldshop-backend` / `oldshop-frontend`, tags them with the short commit SHA
and `latest`, and runs `deploy.sh <sha>` on the server.

**Rollback:** Actions → Deploy → *Run workflow* with an older tag, or on the server
`deploy/scripts/deploy.sh <sha>` (see `deploy/.deploy-history`).

## 6. Observability

| What | Where |
|---|---|
| Dashboards: traffic, p95 latency, 5xx ratio, DB connections, host CPU/RAM/disk | `https://grafana.<domain>` → OldShop folder |
| Alert rules (backend down, 5xx > 5%, p95 > 1 s, Postgres down, disk < 10%) | Grafana → Alerting, or Prometheus rules |
| Logs (Loki mode) | Grafana → *OldShop - Logs (Loki)*, or Explore with `{service="backend", level="error"}` |
| Logs (ELK mode) | `https://kibana.<domain>` → Discover, data view `filebeat-*` |

Backend logs are JSON with `request_id`; the same id is returned to the client in the `X-Request-ID`
header and forwarded by Nginx, so a user-reported error can be traced to every log line of that request.

### Switching Loki ⇄ ELK

```bash
deploy/scripts/switch-logging.sh status
deploy/scripts/switch-logging.sh elk          # needs ELASTIC_PASSWORD, KIBANA_* in .env and ~2.5 GB free RAM
deploy/scripts/switch-logging.sh loki
deploy/scripts/switch-logging.sh loki --purge # also delete the Elasticsearch volume
```

Only the log containers change; the shop keeps running. Both shippers tail the same Docker json-file logs,
so the new stack picks up recent history that is still on disk (10 MB × 5 files per container).
The choice is remembered in `deploy/.log-stack` and reused by `deploy.sh`.

| | Loki + Promtail | Elasticsearch + Kibana + Filebeat |
|---|---|---|
| RAM | ~300 MB | ~2.5 GB |
| Indexing | labels only (service, level) | every field, full-text |
| Good for | day-to-day tailing, correlating with metrics in Grafana | ad-hoc search and aggregations over log fields |

## 7. Backups

```bash
deploy/scripts/backup-db.sh                                   # pg_dump + media archive into deploy/backups
deploy/scripts/restore-db.sh deploy/backups/oldshop-<date>.dump
```

Schedule it with cron (`crontab -e` as `deploy`):

```
0 3 * * * /opt/oldshop/deploy/scripts/backup-db.sh >> /home/deploy/backup.log 2>&1
```

Copy `deploy/backups` off the server (rclone, S3, another VPS); a backup on the same disk is not a backup.
