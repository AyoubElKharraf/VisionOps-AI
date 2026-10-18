#!/usr/bin/env bash
# Rollback Liquibase database changesets on PostgreSQL.
# Usage: ./scripts/db-rollback.sh [COUNT]
#    or: ./scripts/db-rollback.sh --tag <TAG>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

COUNT="${1:-1}"
TAG=""

if [[ "${1:-}" == "--tag" ]]; then
    TAG="${2:-}"
    if [[ -z "$TAG" ]]; then
        echo "Error: Tag name required after --tag"
        exit 1
    fi
fi

cd "$PROJECT_ROOT"

if [[ -n "$TAG" ]]; then
    echo -e "\033[35m[Liquibase] Rolling back to tag: $TAG...\033[0m"
    docker compose run --rm liquibase rollback "$TAG"
else
    echo -e "\033[35m[Liquibase] Rolling back $COUNT changeset(s)...\033[0m"
    docker compose run --rm liquibase rollbackCount "$COUNT"
fi
