#!/usr/bin/env bash
# View history of deployed Liquibase changesets on PostgreSQL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
echo -e "\033[36m[Liquibase] Retrieving deployed migration history...\033[0m"
docker compose run --rm liquibase history
