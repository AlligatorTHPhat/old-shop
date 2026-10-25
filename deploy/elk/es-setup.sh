#!/bin/sh
# Runs once in the es-setup container: sets the kibana_system password and a 14-day retention policy
# on the Filebeat data stream, then exits.
set -eu

ES=http://elasticsearch:9200
AUTH="elastic:${ELASTIC_PASSWORD}"

echo "Setting kibana_system password..."
until curl -fs -u "$AUTH" -X POST "$ES/_security/user/kibana_system/_password" \
  -H 'Content-Type: application/json' -d "{\"password\":\"${KIBANA_SYSTEM_PASSWORD}\"}" >/dev/null; do
  sleep 3
done

echo "Applying 14-day retention to filebeat logs..."
curl -fs -u "$AUTH" -X PUT "$ES/_ilm/policy/filebeat" -H 'Content-Type: application/json' -d '{
  "policy": {
    "phases": {
      "hot":    { "actions": { "rollover": { "max_age": "1d", "max_primary_shard_size": "5gb" } } },
      "delete": { "min_age": "14d", "actions": { "delete": {} } }
    }
  }
}' >/dev/null

echo "Elasticsearch setup done."
