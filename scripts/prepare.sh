#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
if [ ! -f .env ]; then
  setup_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  umask 077
  cat > .env <<EOF
SETUP_TOKEN=${setup_token}
# Configure receipt AI in the app's Settings → Receipts & AI.
COOKIE_SECURE=false
EOF
  echo 'Created .env with an optional setup token. Keep it for protected owner setup, or clear SETUP_TOKEN for token-free setup.'
else
  echo 'Keeping existing .env.'
fi
mkdir -p data
if [ ! -f data/expense-pilot-logo.png ]; then
  cp server/static/expense-pilot-logo.png data/expense-pilot-logo.png
  chmod 644 data/expense-pilot-logo.png
fi
if [ "$(id -u)" = "0" ]; then
  chown -R 99:100 data
else
  echo 'Run sudo chown -R 99:100 data before starting Docker.'
fi
chmod 750 data
chmod 600 .env
echo 'Ready. Start with docker compose up -d --build, or follow README.md for Unraid installation.'
