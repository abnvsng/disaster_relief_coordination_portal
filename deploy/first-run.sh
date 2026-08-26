#!/usr/bin/env bash
# One-shot setup on a fresh EC2 instance. Run from the repo root.
set -euo pipefail

if [ ! -f .env ]; then
  cp .env.example .env
  python3 - <<'PY' >> /dev/null
PY
  echo "Created .env from the example. Edit it before going public."
fi

docker compose build
docker compose up -d
sleep 6
docker compose exec -T web python manage.py migrate --noinput
docker compose exec -T web python manage.py seed_india
docker compose exec -T web python manage.py simulate_event --district DBG --reports 22

echo
echo "Portal is up. Sign in as ddma_darbhanga / relief2026"
