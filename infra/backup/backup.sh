#!/bin/sh
# One compressed PostgreSQL dump (custom format, restorable table by table) into $BACKUP_DIR, then delete dumps
# older than $BACKUP_KEEP_DAYS. Connection from the standard PG* variables (PGHOST, PGUSER, PGPASSWORD, PGDATABASE).
# Copy the files off the host as well (object storage, another server): a backup on the same disk is not a backup.
set -eu
dir="${BACKUP_DIR:-/backups}"
keep="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$dir/zentrix-$stamp.dump"
pg_dump --format=custom --compress=6 --no-owner --file="$file.partial"
mv "$file.partial" "$file"
pg_restore --list "$file" > /dev/null   # the dump is readable
find "$dir" -name 'zentrix-*.dump' -mtime +"$keep" -delete
echo "{\"level\":\"info\",\"event\":\"backup_done\",\"file\":\"$file\",\"bytes\":$(wc -c < "$file"),\"at\":\"$stamp\"}"
