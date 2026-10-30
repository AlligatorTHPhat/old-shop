#!/usr/bin/env bash
# Real PG/Mongo tests use two NEW isolated DB pairs; MinIO tests use unique keys.
set -euo pipefail
cd "$(dirname "$0")/../.."
stamp="$(date +%Y%m%d%H%M%S)_${RANDOM}"
compose=(docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml)
for phase in regression etl; do
  db="day5_test_${stamp}_${phase}"
  run=("${compose[@]}" run --rm --no-deps -e "DB_NAME=$db" -e "MONGO_DB=$db" -e MEDIA_DIR=/tmp/day5-media)
  "${run[@]}" --entrypoint python etl-test -m scripts.init_db
  "${run[@]}" --entrypoint python etl-test -m scripts.init_mongo
  selection=(tests --ignore=tests/test_day5_etl.py)
  storage=local
  if [[ $phase == etl ]]; then selection=(tests/test_day5_etl.py); storage=minio; fi
  "${run[@]}" -e "STORAGE_BACKEND=$storage" -e DAY3_INTEGRATION=1 -e DAY5_INTEGRATION=1 -e DEBUG=false -e PYTHONUSERBASE=/tmp/day5-py \
    -v "$PWD/backend/tests:/app/tests:ro" -v "$PWD/backend/pytest.ini:/app/pytest.ini:ro" -v "$PWD/backend/requirements-dev.lock:/tmp/dev.lock:ro" \
    --entrypoint sh etl-test -c 'mkdir -p /tmp/prometheus && python -m pip install --user --require-hashes --only-binary :all: -q --no-warn-script-location -r /tmp/dev.lock && python -m pytest -o addopts="" -p no:cacheprovider "$@"' sh "${selection[@]}"
  printf 'Isolated PG/Mongo databases retained for inspection: %s\n' "$db"
done
