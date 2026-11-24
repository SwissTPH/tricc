#!/usr/bin/env bash
# Copy the shared display-text fixtures to the frontend
# (feature/20261120-prosemirror-display-text.md §3). tricc_oo holds the source of truth.
#
#   scripts/sync-text-fixtures.sh [path/to/tricc-frontend]
#
# The frontend path defaults to ../tricc-frontend next to this repository.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
frontend="${1:-$here/../tricc-frontend}"
target="$frontend/packages/core/src/text/fixtures"
[ -d "$frontend/packages/core" ] || { echo "not a tricc-frontend checkout: $frontend" >&2; exit 1; }
mkdir -p "$target"
rm -f "$target"/*.json
cp "$here"/tests/text/fixtures/*.json "$target"/
echo "copied $(ls "$here"/tests/text/fixtures/*.json | wc -l) fixtures to $target"
