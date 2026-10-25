#!/usr/bin/env bash
# Dump the database (custom format) into deploy/backups and prune old dumps.
# Cron example (daily 03:00):
#   0 3 * * * /opt/oldshop/deploy/scripts/backup-db.sh >> /var/log/oldshop-backup.log 2>&1
source "$(dirname "$0")/lib.sh"

backup_dir="$DEPLOY_DIR/backups"
keep_days="$(env_value BACKUP_KEEP_DAYS 14)"
db_user="$(env_value DB_USER)"
db_name="$(env_value DB_NAME)"
file="$backup_dir/${db_name}-$(date +%Y%m%d-%H%M%S).dump"

mkdir -p "$backup_dir"
log "Dumping $db_name to $file"
compose exec -T postgres pg_dump -U "$db_user" -d "$db_name" -Fc > "$file"
[[ -s "$file" ]] || die "Backup file is empty"

# Uploaded images live in the media volume; archive them alongside the dump.
docker run --rm -v oldshop_media_data:/media:ro -v "$backup_dir":/backup alpine \
  tar czf "/backup/media-$(date +%Y%m%d-%H%M%S).tar.gz" -C /media .

find "$backup_dir" -type f \( -name '*.dump' -o -name 'media-*.tar.gz' \) -mtime +"$keep_days" -print -delete
log "Backup done ($(du -h "$file" | cut -f1))"
