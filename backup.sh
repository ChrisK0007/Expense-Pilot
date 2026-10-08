#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Consistent backup: database, receipts, and session signing key together.
backup_dir=${1:?Usage: bash backup.sh /path/to/private/backup-directory}
mkdir -p -- "$backup_dir"
backup_path=$(cd -- "$backup_dir" && pwd)/expense-pilot-$(date -u +%Y%m%dT%H%M%SZ).tar.gz
umask 077
docker stop expense-pilot
trap 'docker start expense-pilot >/dev/null' EXIT
tar -czf "$backup_path" data .env
printf 'Backup saved: %s\n' "$backup_path"
