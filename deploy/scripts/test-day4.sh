#!/usr/bin/env bash
# Runs write tests on a NEW PostgreSQL database, never the application database.
set -euo pipefail
cd "$(dirname "$0")/../.."
day4_test_db="day4_test_$(date +%Y%m%d%H%M%S)_${RANDOM}"
compose=(docker compose --env-file deploy/.env.data -f deploy/docker-compose.distributed.yml)
"${compose[@]}" run --rm --no-deps -e "DB_NAME=$day4_test_db" -e MEDIA_DIR=/tmp/day4-test-media --entrypoint python backend -m scripts.init_db
"${compose[@]}" run --rm --no-deps -e "DB_NAME=$day4_test_db" -e MEDIA_DIR=/tmp/day4-test-media -e STORAGE_BACKEND=local -e DAY3_INTEGRATION=1 -e DEBUG=false -e PYTHONUSERBASE=/tmp/day3-py \
  -v "$PWD/backend/tests:/app/tests:ro" -v "$PWD/backend/pytest.ini:/app/pytest.ini:ro" -v "$PWD/backend/requirements-dev.lock:/tmp/dev.lock:ro" --entrypoint sh backend \
  -c 'mkdir -p /tmp/prometheus && python -m pip install --user --require-hashes -q --no-warn-script-location -r /tmp/dev.lock && python -m pytest -o addopts="" -p no:cacheprovider tests'
printf 'Test database retained for inspection: %s\n' "$day4_test_db"
