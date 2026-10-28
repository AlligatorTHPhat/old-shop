#!/bin/sh
set -eu
: "${REPLICATION_PASSWORD:?Missing replication password}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=repl_password="$REPLICATION_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE oldshop_repl WITH LOGIN REPLICATION PASSWORD %L', :'repl_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oldshop_repl')
\gexec
SQL
printf '\nhost replication oldshop_repl all scram-sha-256\n' >> "$PGDATA/pg_hba.conf"
