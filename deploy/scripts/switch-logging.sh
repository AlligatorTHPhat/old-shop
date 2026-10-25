#!/usr/bin/env bash
# Switch the log pipeline between Loki (Promtail -> Loki -> Grafana) and ELK
# (Filebeat -> Elasticsearch -> Kibana). Application containers are not restarted:
# both shippers read the same Docker json-file logs, so nothing is lost while switching.
#
#   deploy/scripts/switch-logging.sh status
#   deploy/scripts/switch-logging.sh elk
#   deploy/scripts/switch-logging.sh loki
#   deploy/scripts/switch-logging.sh loki --purge   # also delete the volumes of the stack you leave
source "$(dirname "$0")/lib.sh"

target="${1:-status}"
purge="${2:-}"
current="$(active_log_stack)"

case "$target" in
  status)
    log "Active log stack: $current"
    compose ps --format 'table {{.Service}}\t{{.Status}}' | grep -E 'SERVICE|loki|promtail|elasticsearch|kibana|filebeat' || true
    exit 0 ;;
  loki|elk) ;;
  *) die "Usage: $0 status|loki|elk [--purge]" ;;
esac

[[ "$target" == "$current" ]] && { log "Already on $target"; exit 0; }

if [[ "$target" == "elk" ]]; then
  mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
  (( mem_kb >= 3500000 )) || warn "Only $(( mem_kb / 1024 )) MB RAM: Elasticsearch + Kibana need ~2.5 GB on top of the app"
  map_count="$(sysctl -n vm.max_map_count)"
  if (( map_count < 262144 )); then
    die "vm.max_map_count=$map_count, Elasticsearch needs 262144. Run: sudo sysctl -w vm.max_map_count=262144 (bootstrap-vps.sh makes it permanent)"
  fi
  for key in ELASTIC_PASSWORD KIBANA_SYSTEM_PASSWORD KIBANA_ENCRYPTION_KEY KIBANA_BASIC_AUTH_HASH; do
    [[ -n "$(env_value "$key")" ]] || die "$key is empty in $ENV_FILE"
  done
fi

log "Switching log stack: $current -> $target"
# The new file set no longer lists the old stack's services, so --remove-orphans stops them.
LOG_STACK_OVERRIDE="$target" compose up -d --remove-orphans
echo "$target" > "$STATE_FILE"

if [[ "$purge" == "--purge" ]]; then
  if [[ "$current" == "loki" ]]; then volumes=(loki_data promtail_positions); else volumes=(es_data filebeat_data); fi
  for v in "${volumes[@]}"; do docker volume rm "oldshop_$v" >/dev/null 2>&1 && log "Removed volume oldshop_$v" || true; done
fi

if [[ "$target" == "elk" ]]; then
  wait_healthy elasticsearch 300
  log "ELK is up. Kibana: https://$(env_value KIBANA_DOMAIN) (index pattern: filebeat-*)"
else
  log "Loki is up. Grafana: https://$(env_value GRAFANA_DOMAIN) > Dashboards > OldShop - Logs (Loki)"
fi
