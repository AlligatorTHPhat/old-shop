#!/bin/sh
set -eu
: "${PGDATA:?}" "${REPLICATION_PASSWORD:?}"
if [ "$(id -u)" = 0 ]; then
  mkdir -p "$PGDATA"
  chown postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
  exec su-exec postgres sh "$0"
fi
umask 077
printf 'pg-primary:5432:replication:oldshop_repl:%s\n' "$REPLICATION_PASSWORD" > /tmp/oldshop-replication.pgpass
export PGPASSFILE=/tmp/oldshop-replication.pgpass
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  # Never delete a partially initialized or existing volume automatically.
  if [ -n "$(ls -A "$PGDATA")" ]; then
    echo 'Replica volume is non-empty without PG_VERSION; inspect it before retrying.' >&2
    exit 1
  fi
  pg_basebackup --dbname="host=pg-primary port=5432 user=oldshop_repl application_name=oldshop-data-replica passfile=/tmp/oldshop-replication.pgpass" \
    --pgdata="$PGDATA" --wal-method=stream --write-recovery-conf --checkpoint=fast
fi
test -f "$PGDATA/standby.signal" || { echo 'Refusing to start a promoted/non-standby volume as a replica.' >&2; exit 1; }
exec docker-entrypoint.sh postgres -c hot_standby=on -c shared_buffers=128MB
