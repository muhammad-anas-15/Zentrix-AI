#!/bin/sh
# Restore a dump into a database (default: a NEW database, so production is never overwritten by accident).
#   docker compose -f docker-compose.prod.yml exec backup sh /scripts/restore.sh /backups/zentrix-<stamp>.dump zentrix_restore
# Then point the API at it only after checking it (docs/RUNBOOK.md, "Restore").
set -eu
file="${1:?usage: restore.sh <dump file> [target database]}"
target="${2:-zentrix_restore}"
createdb "$target"
pg_restore --no-owner --exit-on-error --dbname="$target" "$file"
psql -d "$target" -Atc "SELECT 'users=' || count(*) FROM users UNION ALL SELECT 'signals=' || count(*) FROM signals UNION ALL SELECT 'candles=' || count(*) FROM candles"
echo "restored into $target"
