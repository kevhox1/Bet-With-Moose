#!/bin/bash
# Run database migrations manually (postgres docker-entrypoint handles this on first run)
set -e
cd "$(dirname "$0")/.."
for f in database/migrations/*.sql; do
  echo "Running migration: $f"
  psql "${DATABASE_URL:-postgresql://moosebets:moosebets@localhost:5432/moosebets}" -f "$f"
done
echo "Migrations complete."
