#!/usr/bin/env bash
# Maintenance migration, with private backups, restore rehearsal and row reconciliation.
# Run after test-day5.sh passes. Keeps API/frontend stopped on any failure.
set -euo pipefail
cd "$(dirname "$0")/../.."
compose=(docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml)
if [[ "${1:-}" == --resilience ]]; then
  compose+=(--profile resilience)
elif [[ $# -ne 0 ]]; then
  echo 'Usage: bash deploy/scripts/apply-day5.sh [--resilience]' >&2
  exit 2
fi
maintenance=0
on_error() {
  if [[ $maintenance == 1 ]]; then
    "${compose[@]}" stop frontend backend etl-worker >/dev/null 2>&1 || true
    echo 'Migration failed; API/frontend remain stopped. Inspect backups before recovery.' >&2
  fi
}
trap on_error ERR
"${compose[@]}" build backend
umask 077
stamp="$(TZ=Asia/Ho_Chi_Minh date +%Y%m%d_%H%M%S)"
backup="$PWD/deploy/backups/day5_$stamp"
restore_db="day5_restore_$stamp"
mkdir -p "$backup"
maintenance=1
"${compose[@]}" stop frontend backend etl-worker
# API and ETL are stopped; originals stay unchanged while backups and backfill run.
run_backup=("${compose[@]}" run --rm --no-deps --user "$(id -u):$(id -g)" -v "$backup:/backup" --entrypoint python backend)
"${run_backup[@]}" -m scripts.verify_day4 --output /backup/pg_before.json
"${compose[@]}" exec -T pg-primary sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup/postgres.dump"
"${compose[@]}" exec -T pg-primary sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$restore_db"
"${compose[@]}" exec -T pg-primary sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$1"' sh "$restore_db" < "$backup/postgres.dump"
"${compose[@]}" run --rm --no-deps --user "$(id -u):$(id -g)" -e "DB_NAME=$restore_db" -v "$backup:/backup" --entrypoint python backend -m scripts.verify_day4 --compare /backup/pg_before.json
"${run_backup[@]}" -m scripts.archive_day4 backup /backup/stores
"${run_backup[@]}" -m scripts.archive_day4 verify /backup/stores
"${compose[@]}" run --rm --no-deps --entrypoint python backend -m scripts.migrate
"${compose[@]}" run --rm --no-deps mongo-schema-init
"${compose[@]}" run --rm --no-deps --entrypoint python backend -m etl.run full
"${compose[@]}" run --rm --no-deps --entrypoint python backend -m etl.run full
"${run_backup[@]}" -m scripts.verify_day4 --compare /backup/pg_before.json --output /backup/pg_after.json
"${compose[@]}" up -d --wait --wait-timeout 180
# Nginx resolves the backend name at startup; restart after replacing the backend container.
"${compose[@]}" restart frontend
"${compose[@]}" exec -T etl-worker python -m etl.run status
"${compose[@]}" exec -T backend python -c 'import urllib.request,json; result=json.load(urllib.request.urlopen("http://127.0.0.1:8000/health/ready",timeout=15)); assert result["status"]=="ok"; print(json.dumps(result))'
maintenance=0
printf 'PASS. Private backup directory: %s\nRestore rehearsal database retained: %s\n' "$backup" "$restore_db"
