#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
file="${1:?Usage: sh scripts/restore.sh backups/file.dump}"
test -s "$file"
echo 'This REPLACES planner database contents and stops only this project services.'
echo 'Existing sessions are revoked after restore. Amnezia is not managed here.'
printf 'Type RESTORE to continue: '
read answer
test "$answer" = RESTORE || exit 1
docker compose stop web api bot
docker compose exec -T db pg_restore -U planner -d planner --clean --if-exists --no-owner --exit-on-error < "$file"
docker compose exec -T db psql -U planner -d planner -v ON_ERROR_STOP=1 -c 'TRUNCATE sessions, login_codes;'
docker compose up -d api web
echo 'Restored. If needed, explicitly restart the optional bot after checking its status.'
