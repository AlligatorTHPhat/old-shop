#!/usr/bin/env bash
# Apply the tested additive indexes with maintenance, backup, restore and reconciliation.
set -euo pipefail
cd "$(dirname "$0")/../.."
compose=(docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml)
if [[ "${1:-}" == --resilience ]]; then
  compose+=(--profile resilience)
elif [[ $# -ne 0 ]]; then
  echo 'Usage: bash deploy/scripts/apply-indexing-v2.sh [--resilience]' >&2
  exit 2
fi
[[ -n "$("${compose[@]}" ps -q pg-primary)" ]] || {
  echo 'No running pg-primary in this Compose project; nothing was changed.' >&2
  exit 1
}
# Build a reviewable current image; never run an older embedded migration directory.
"${compose[@]}" build backend
"${compose[@]}" run --rm --no-deps --entrypoint python backend -m scripts.verify_indexing_v2 --preflight
umask 077
stamp="$(TZ=Asia/Ho_Chi_Minh date +%Y%m%d_%H%M%S)"
backup="$PWD/deploy/backups/indexing_v2_$stamp"
restore_db="indexing_v2_restore_$stamp"
mkdir -p "$backup"
maintenance=0
on_error() {
  if [[ $maintenance == 1 ]]; then
    "${compose[@]}" stop frontend backend etl-worker >/dev/null 2>&1 || true
    echo "Indexing rollout failed; application remains stopped. Inspect private backup: $backup" >&2
  fi
}
trap on_error ERR
maintenance=1
"${compose[@]}" stop frontend backend etl-worker
job=("${compose[@]}" run --rm --no-deps --user "$(id -u):$(id -g)" -v "$backup:/backup" --entrypoint python backend)
"${job[@]}" -m scripts.verify_day4 --output /backup/source_before.json
"${compose[@]}" exec -T pg-primary sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup/postgres.dump"
"${compose[@]}" exec -T pg-primary sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$restore_db"
"${compose[@]}" exec -T pg-primary sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$1"' sh "$restore_db" < "$backup/postgres.dump"
"${compose[@]}" run --rm --no-deps --user "$(id -u):$(id -g)" -e "DB_NAME=$restore_db" -v "$backup:/backup" --entrypoint python backend -m scripts.verify_day4 --compare /backup/source_before.json
"${job[@]}" -m scripts.archive_day4 backup /backup/stores
"${job[@]}" -m scripts.archive_day4 verify /backup/stores
# Migration/Mongo init add indexes; reconcile can perform normal sweep/media cleanup.
"${job[@]}" -m scripts.migrate
"${compose[@]}" exec -T pg-primary sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<'SQL'
ANALYZE product, product_image, user_profile, "order", etl_runs, etl_outbox, user_role;
SQL
"${compose[@]}" run --rm --no-deps mongo-schema-init
"${job[@]}" -m scripts.verify_indexing_v2 --mongo
"${job[@]}" -m scripts.verify_day4 --compare /backup/source_before.json --output /backup/source_after.json
"${job[@]}" -m etl.run reconcile
"${compose[@]}" up -d --no-deps --wait --wait-timeout 180 backend
"${compose[@]}" up -d --no-deps --wait --wait-timeout 180 etl-worker frontend
"${compose[@]}" restart frontend
"${compose[@]}" exec -T backend python -m scripts.verify_indexing_v2 --mongo
maintenance=0
printf 'PASS. Backup: %s\nRestore rehearsal DB retained: %s\n' "$backup" "$restore_db"
