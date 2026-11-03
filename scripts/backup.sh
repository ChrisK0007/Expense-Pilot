#!/usr/bin/env bash
# Back up the actual /data mount, including receipts and the session signing key.
set -euo pipefail
umask 077
repo_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
container=${CONTAINER_NAME:-expense-pilot}
backup_dir=${1:?Usage: bash backup.sh /path/to/private/backup-directory}
data_dir=${EXPENSE_PILOT_DATA_DIR:-}
env_file=${EXPENSE_PILOT_ENV_FILE:-$repo_dir/.env}
restart=false
temporary=''
cleanup() {
  status=$?
  trap - EXIT
  if [ -n "$temporary" ]; then rm -f -- "$temporary"; fi
  if $restart; then docker start "$container" >/dev/null || status=1; fi
  exit "$status"
}
trap cleanup EXIT
if [ -z "$data_dir" ]; then
  data_dir=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$container")
  [ -n "$data_dir" ] || { echo 'No /data mount found on the selected container.' >&2; exit 1; }
  running=$(docker inspect --format '{{.State.Running}}' "$container")
  case "$running" in true|false) ;; *) echo 'Cannot determine container state.' >&2; exit 1;; esac
else
  # Explicit offline mode: callers must stop every writer before invoking this.
  running=false
fi
data_dir=$(cd -- "$data_dir" && pwd -P)
[ -f "$data_dir/rounded.sqlite" ] || { echo 'No Expense Pilot database found in the data directory.' >&2; exit 1; }
mkdir -p -- "$backup_dir"
backup_dir=$(cd -- "$backup_dir" && pwd -P)
case "$backup_dir/" in "$data_dir/"*) echo 'Backup destination must be outside the data directory.' >&2; exit 1;; esac
backup_path="$backup_dir/expense-pilot-$(date -u +%Y%m%dT%H%M%SZ)-$$.tar.gz"
temporary=$(mktemp "$backup_dir/.expense-pilot-XXXXXX")
if [ "$running" = true ]; then
  restart=true
  docker stop "$container" >/dev/null
fi
# The archive has stable data/ and optional .env entries, regardless of host paths.
# Automatic backups stored in data/backups are archives already; do not nest them.
args=(--exclude=./backups --exclude='./.backup-stage-*' --exclude=./backup-id --exclude=./.backup-identity.lock -C "$data_dir" --transform 's,^\./,data/,;s,^\.$,data,' .)
if [ -f "$env_file" ]; then
  env_dir=$(cd -- "$(dirname -- "$env_file")" && pwd -P)
  env_name=$(basename -- "$env_file")
  [ "$env_name" = .env ] || { echo 'Environment file must be named .env.' >&2; exit 1; }
  args+=(-C "$env_dir" .env)
fi
tar -czf "$temporary" "${args[@]}"
mv -- "$temporary" "$backup_path"
temporary=''
printf 'Backup saved: %s\n' "$backup_path"
