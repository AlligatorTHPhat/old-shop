#!/usr/bin/env bash
# Restore a dump produced by backup-db.sh. Overwrites the current database.
#   deploy/scripts/restore-db.sh deploy/backups/oldshop-20250101-030000.dump
source "$(dirname "$0")/lib.sh"

file="${1:-}"
[[ -f "$file" ]] || die "Usage: $0 <file.dump>"
db_user="$(env_value DB_USER)"
db_name="$(env_value DB_NAME)"

read -r -p "This replaces database '$db_name' with $file. Type the database name to continue: " answer
[[ "$answer" == "$db_name" ]] || die "Aborted"

compose stop backend
compose exec -T postgres pg_restore -U "$db_user" -d "$db_name" --clean --if-exists --no-owner < "$file"
compose start backend
wait_healthy backend 120
log "Restore complete"
