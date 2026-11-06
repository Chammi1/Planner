#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test -f .env || { echo 'Create .env from .env.example first'; exit 1; }
docker compose version
docker compose config --quiet
printf '\nExisting containers (must remain running):\n'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
printf '\nPorts required by this project (should be free before first launch):\n'
ss -lntp '( sport = :80 or sport = :8443 )'
printf '\nDNS IPv4:\n'
getent ahostsv4 bot.sotaholder.ru || true
printf '\nDNS IPv6 (remove stale AAAA if it points elsewhere):\n'
getent ahostsv6 bot.sotaholder.ru || true
printf '\nMemory and disk:\n'
free -h
df -h .
echo 'Preflight only. No services were started or stopped.'
