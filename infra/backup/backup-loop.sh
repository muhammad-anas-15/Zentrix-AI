#!/bin/sh
# Runs inside the `backup` service: one dump now, then every BACKUP_INTERVAL_S seconds.
set -eu
while true; do
  sh /scripts/backup.sh || echo "{\"level\":\"error\",\"event\":\"backup_failed\",\"at\":\"$(date -u +%FT%TZ)\"}"
  sleep "${BACKUP_INTERVAL_S:-86400}"
done
