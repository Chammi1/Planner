#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
file="backups/planner-$(date -u +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U planner -d planner -Fc > "$file"
if [ ! -s "$file" ]; then echo "Backup empty" >&2; exit 1; fi
printf 'Database backup created: %s\n' "$file"
echo 'Copy it securely off this server. This does not back up .env or HTTPS certificates.'
