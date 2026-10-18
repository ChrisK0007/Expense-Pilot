#!/usr/bin/env bash
# Compatibility entry point for existing installation commands.
set -euo pipefail
exec bash "$(dirname -- "$0")/scripts/prepare.sh" "$@"
