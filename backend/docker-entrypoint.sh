#!/bin/sh
set -e

# Several uvicorn workers share one /metrics view through this directory; stale files from a
# previous run would double-count, so start from an empty one.
if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
  rm -rf "$PROMETHEUS_MULTIPROC_DIR"
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

if [ "${SKIP_DB_INIT:-false}" != "true" ]; then
  if [ "${BUCKET_MODE:-false}" = "true" ]; then
    python -m scripts.bucket_setup
  else
    python -m scripts.init_db
  fi
fi

exec "$@"
