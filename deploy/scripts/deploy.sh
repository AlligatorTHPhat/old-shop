#!/usr/bin/env bash
# Pull the given image tag and (re)start the whole stack with zero manual steps.
#   deploy/scripts/deploy.sh            # tag from .env (IMAGE_TAG), usually "latest"
#   deploy/scripts/deploy.sh 3f2c1ab    # a specific commit, e.g. to roll back
#   BUILD=1 deploy/scripts/deploy.sh    # build images on the VPS instead of pulling
source "$(dirname "$0")/lib.sh"

export IMAGE_TAG="${1:-$(env_value IMAGE_TAG latest)}"
log "Deploying images tagged '$IMAGE_TAG' with log stack '$(active_log_stack)'"

if [[ "${BUILD:-0}" == "1" ]]; then
  compose build backend frontend
else
  compose pull --quiet backend frontend
fi
compose pull --quiet --ignore-buildable 2>/dev/null || true   # third-party images

compose up -d --remove-orphans
wait_healthy backend 180
log "Backend healthy"

# Record what is live so a rollback is one command away.
echo "$(date -Is) $IMAGE_TAG" >> "$DEPLOY_DIR/.deploy-history"
docker image prune -f >/dev/null
compose ps --format 'table {{.Service}}\t{{.Status}}'
log "Done: https://$(env_value DOMAIN)"
