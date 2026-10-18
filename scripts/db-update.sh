#!/usr/bin/env bash
# Apply pending Liquibase migrations to PostgreSQL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
echo -e "\033[32m[Liquibase] Applying pending database migrations...\033[0m"
docker compose run --rm liquibase update
