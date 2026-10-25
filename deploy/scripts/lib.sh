#!/usr/bin/env bash
# Shared helpers for the deploy scripts. Source it, don't run it.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
STATE_FILE="$DEPLOY_DIR/.log-stack"   # remembers the active log stack across deploys

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || die "Missing $ENV_FILE (copy deploy/.env.example and fill it in)"
grep -q 'CHANGE_ME' "$ENV_FILE" && warn "$ENV_FILE still contains CHANGE_ME placeholders"

env_value() {  # env_value KEY [default]
  local value
  value="$(grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true)"
  echo "${value:-${2:-}}"
}

active_log_stack() {
  if [[ -f "$STATE_FILE" ]]; then cat "$STATE_FILE"; else env_value LOG_STACK loki; fi
}

# compose [args...] — docker compose with the app, monitoring and current log-stack files.
compose() {
  local stack="${LOG_STACK_OVERRIDE:-$(active_log_stack)}"
  docker compose \
    --project-directory "$DEPLOY_DIR" \
    --env-file "$ENV_FILE" \
    -p oldshop \
    -f "$DEPLOY_DIR/docker-compose.yml" \
    -f "$DEPLOY_DIR/docker-compose.monitoring.yml" \
    -f "$DEPLOY_DIR/docker-compose.$stack.yml" \
    "$@"
}

wait_healthy() {  # wait_healthy SERVICE [timeout_seconds]
  local service="$1" timeout="${2:-120}" waited=0 id status
  id="$(compose ps -q "$service")"
  [[ -n "$id" ]] || die "Service $service is not running"
  while (( waited < timeout )); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id")"
    # Services without a healthcheck count as ready once running; the backend must report healthy.
    [[ "$status" == "healthy" ]] && return 0
    [[ "$status" == "running" && "$service" != "backend" ]] && return 0
    sleep 3; waited=$(( waited + 3 ))
  done
  compose logs --tail 50 "$service" >&2
  die "$service did not become healthy within ${timeout}s"
}
