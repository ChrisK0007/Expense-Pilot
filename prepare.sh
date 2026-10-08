#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [ ! -f .env ]; then
  setup_token=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  umask 077
  cat > .env <<EOF
SETUP_TOKEN=${setup_token}
OLLAMA_URL=
OLLAMA_MODEL=
COOKIE_SECURE=false
EOF
  echo 'Created .env with a unique setup token.'
else
  echo 'Keeping existing .env.'
fi
mkdir -p data
if [ "$(id -u)" = "0" ]; then
  chown -R 99:100 data
else
  echo 'Run sudo chown -R 99:100 data before starting Docker.'
fi
chmod 750 data
chmod 600 .env
echo 'Ready. Start with docker compose up -d --build, or follow README.html for plain Docker.'
