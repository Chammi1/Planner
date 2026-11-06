#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
    echo "Missing server .env file" >&2
    exit 1
fi

exec docker compose \
    --project-directory "$ROOT" \
    --env-file "$ROOT/.env" \
    --env-file "$ROOT/deploy/release.env" \
    -f "$ROOT/deploy/compose.production.yaml" \
    "$@"