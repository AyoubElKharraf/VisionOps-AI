#!/usr/bin/env bash
# Check Liquibase database migration status against PostgreSQL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
echo -e "\033[36m[Liquibase] Checking database migration status...\033[0m"
docker compose run --rm liquibase status --verbose
