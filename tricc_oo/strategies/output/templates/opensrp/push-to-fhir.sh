#!/usr/bin/env bash
# Push TRICC OpenSRPStrategy JSON output to a FHIR R4 server (gateway or HAPI).
#
# This file is copied into the export directory by OpenSRPStrategy. Run from the
# package root (the folder that contains questionnaire/, plan-definition/, …)
# or pass CONTENT_DIR.
#
# Usage:
#   # .env is seeded once from env.fhir.example if missing; edit URL / APP_ID
#   # put KEYCLOAK_CLIENT_SECRET / passwords in .secrets (gitignored)
#   ./push-to-fhir.sh
#   ./push-to-fhir.sh /path/to/export/<form_id>
#   DRY_RUN=1 ./push-to-fhir.sh
#   SKIP_AUTH=1 FHIR_BASE_URL=http://localhost:8082/fhir ./push-to-fhir.sh
#
# Env (see env.fhir.example): FHIR_BASE_URL, APP_ID, KEYCLOAK_*, SKIP_AUTH, …

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTENT_DIR="${1:-$SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# Load .env / .secrets (do not override already-exported vars unless in file)
# ---------------------------------------------------------------------------
load_env_file() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source "$f"
  set +a
  echo "loaded $f"
}

# Prefer secrets next to the script, then CWD
load_env_file "$SCRIPT_DIR/.env"
load_env_file "$SCRIPT_DIR/.secrets"
load_env_file "$CONTENT_DIR/.env"
load_env_file "$CONTENT_DIR/.secrets"
load_env_file "${PWD}/.env"
load_env_file "${PWD}/.secrets"
# Monorepo openSRP-fhircore convenience
if [[ -f "$SCRIPT_DIR/../../../../.env" ]]; then
  load_env_file "$SCRIPT_DIR/../../../../.env"
fi

FHIR_BASE_URL="${FHIR_BASE_URL:-${FHIR:-http://localhost:8082/fhir}}"
FHIR_BASE_URL="${FHIR_BASE_URL%/}"
APP_ID="${APP_ID:-cdss}"
SKIP_AUTH="${SKIP_AUTH:-0}"
DRY_RUN="${DRY_RUN:-0}"
KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-${KEYCLOAK:-}}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-opensrp}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-fhir-core-client}"
KEYCLOAK_CLIENT_SECRET="${KEYCLOAK_CLIENT_SECRET:-}"
KEYCLOAK_USER="${KEYCLOAK_USER:-demo}"
KEYCLOAK_PASSWORD="${KEYCLOAK_PASSWORD:-demo}"
FHIR_ACCESS_TOKEN="${FHIR_ACCESS_TOKEN:-}"
FHIR_RESOURCE_TYPES="${FHIR_RESOURCE_TYPES:-}"

# Curl insecure optional (self-signed)
CURL_OPTS=(-sS)
if [[ "${CURL_INSECURE:-0}" == "1" ]]; then
  CURL_OPTS+=(-k)
fi

echo "=== push TRICC OpenSRP package ==="
echo "CONTENT_DIR=$CONTENT_DIR"
echo "FHIR_BASE_URL=$FHIR_BASE_URL"
echo "APP_ID=$APP_ID"
echo "SKIP_AUTH=$SKIP_AUTH DRY_RUN=$DRY_RUN"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_HDR=()
if [[ "$SKIP_AUTH" != "1" ]]; then
  if [[ -z "$FHIR_ACCESS_TOKEN" ]]; then
    if [[ -z "$KEYCLOAK_BASE_URL" ]]; then
      echo "ERROR: KEYCLOAK_BASE_URL (or KEYCLOAK) required when SKIP_AUTH=0 and FHIR_ACCESS_TOKEN unset" >&2
      exit 1
    fi
    if [[ -z "$KEYCLOAK_CLIENT_SECRET" ]]; then
      echo "ERROR: KEYCLOAK_CLIENT_SECRET required (set in .secrets)" >&2
      exit 1
    fi
    TOKEN_URL="${KEYCLOAK_BASE_URL%/}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token"
    echo "=== token ($KEYCLOAK_USER @ $TOKEN_URL) ==="
    FHIR_ACCESS_TOKEN=$(
      curl "${CURL_OPTS[@]}" -X POST "$TOKEN_URL" \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d "grant_type=password" \
        -d "client_id=${KEYCLOAK_CLIENT_ID}" \
        -d "client_secret=${KEYCLOAK_CLIENT_SECRET}" \
        -d "username=${KEYCLOAK_USER}" \
        -d "password=${KEYCLOAK_PASSWORD}" |
        python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("access_token") or sys.exit("no access_token: "+json.dumps(d)))'
    )
  fi
  AUTH_HDR=(-H "Authorization: Bearer ${FHIR_ACCESS_TOKEN}" -H "App-Id: ${APP_ID}")
fi

# ---------------------------------------------------------------------------
# Discover FHIR JSON resources under CONTENT_DIR
# ---------------------------------------------------------------------------
# Filenames are human-readable (PlanDefinition-demo-….json). REST addressing
# ALWAYS uses the JSON ``id`` field (UUID), never the filename stem.
# Skip: fsh/, contract/ (tooling metadata; Basic often 403 on gateways),
# non-FHIR json, env files
mapfile -t FILES < <(
  find "$CONTENT_DIR" -type f -name '*.json' \
    ! -path '*/fsh/*' \
    ! -path '*/contract/*' \
    ! -name 'env.fhir.example' \
    ! -name 'resource-ids.json' \
    ! -name 'related-person-contract.json' \
    ! -name '.secrets' \
    ! -name '.env' |
    sort
)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ERROR: no JSON files under $CONTENT_DIR" >&2
  exit 1
fi

# Parse resourceType + id from JSON body (not from filename).
# FHIR id = [A-Za-z0-9.-]{1,64}  — underscores are rejected by HAPI (HAPI-0521)
read_fhir_meta() {
  python3 - "$1" <<'PY'
import json, re, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
except Exception:
    sys.exit(1)
if not isinstance(d, dict):
    sys.exit(1)
rt = d.get("resourceType")
rid = d.get("id")
if not rt or not rid:
    sys.exit(1)
# Skip non-deployable / gateway-unfriendly types by default
if rt in {"Basic"}:
    sys.exit(1)
if not re.match(r"^[A-Za-z0-9.\-]{1,64}$", str(rid)):
    print(
        f"INVALID_ID\t{rt}\t{rid}\t{path}",
        file=sys.stderr,
    )
    sys.exit(2)
# filename is informational only
print(f"{rt}\t{rid}")
PY
}

# Optional type filter
type_allowed() {
  local rt="$1"
  [[ -z "$FHIR_RESOURCE_TYPES" ]] && return 0
  local IFS=','
  for t in $FHIR_RESOURCE_TYPES; do
    [[ "$(echo "$t" | tr -d '[:space:]')" == "$rt" ]] && return 0
  done
  return 1
}

# Prefer non-Composition first, Composition last (gateway ACL often needs Composition
# present; when bootstrapping via HAPI, order matters less)
declare -a ORDERED=()
declare -a COMPOSITIONS=()
INVALID_IDS=0

for f in "${FILES[@]}"; do
  # Capture stderr for invalid-id diagnostics
  meta_err=$(mktemp)
  set +e
  meta=$(read_fhir_meta "$f" 2>"$meta_err")
  rc=$?
  set -e
  if [[ $rc -eq 2 ]]; then
    cat "$meta_err" >&2
    echo "  → re-export with current OpenSRPStrategy (resource id must be a valid FHIR id / UUID)" >&2
    INVALID_IDS=1
    rm -f "$meta_err"
    continue
  fi
  rm -f "$meta_err"
  [[ $rc -eq 0 ]] || continue
  rt="${meta%%$'\t'*}"
  # rid from meta is only for ordering/display; put_one re-reads JSON id
  type_allowed "$rt" || continue
  if [[ "$rt" == "Composition" ]]; then
    COMPOSITIONS+=("$f")
  else
    ORDERED+=("$f")
  fi
done
ORDERED+=("${COMPOSITIONS[@]}")

if [[ "$INVALID_IDS" -ne 0 ]]; then
  echo "ERROR: one or more resources have invalid FHIR ids (HAPI-0521). Fix export and retry." >&2
  exit 1
fi

if [[ ${#ORDERED[@]} -eq 0 ]]; then
  echo "ERROR: no FHIR resources (resourceType+id) found under $CONTENT_DIR" >&2
  exit 1
fi

echo "=== uploading ${#ORDERED[@]} resources (URL uses JSON id, not filename) ==="

COMPILE_SM="${SCRIPT_DIR}/compile-structuremap.sh"
if [[ ! -x "$COMPILE_SM" && -f "$COMPILE_SM" ]]; then
  chmod +x "$COMPILE_SM" || true
fi

# Overlay identity (id/url/meta/…) from the export JSON onto HAPI-compiled groups.
merge_compiled_structuremap() {
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys
shell_path, compiled_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(shell_path, encoding="utf-8") as f:
    shell = json.load(f)
with open(compiled_path, encoding="utf-8") as f:
    compiled = json.load(f)
if compiled.get("resourceType") != "StructureMap":
    sys.exit("compiled output is not a StructureMap")
groups = compiled.get("group") or []
if not groups:
    sys.exit("compiled StructureMap has no group[]")
for key in (
    "id",
    "url",
    "name",
    "title",
    "version",
    "status",
    "description",
    "meta",
    "extension",
    "text",
):
    if key in shell:
        compiled[key] = shell[key]
compiled["resourceType"] = "StructureMap"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(compiled, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(
    f"groups={len(groups)} topRules={len(groups[0].get('rule') or [])}",
    file=sys.stderr,
)
PY
}

structuremap_payload() {
  # If a sibling .map exists, compile it. Never PUT the TRicc JSON stub.
  local file="$1"
  local mapfile="${file%.json}.map"
  if [[ "${file##*.}" != "json" ]]; then
    echo "$file"
    return 0
  fi
  if [[ ! -f "$mapfile" ]]; then
    echo "$file"
    return 0
  fi
  if [[ ! -x "$COMPILE_SM" ]]; then
    echo "ERROR: $mapfile exists but compile-structuremap.sh is missing/not executable" >&2
    return 1
  fi
  local compiled merged
  compiled="$(mktemp)"
  merged="$(mktemp)"
  echo "  compile FML ← ${mapfile#$CONTENT_DIR/}" >&2
  if ! "$COMPILE_SM" "$mapfile" "$compiled"; then
    rm -f "$compiled" "$merged"
    echo "ERROR: HAPI FML compile failed for $mapfile (refusing to upload stub JSON)" >&2
    return 1
  fi
  if ! merge_compiled_structuremap "$file" "$compiled" "$merged"; then
    rm -f "$compiled" "$merged"
    echo "ERROR: could not merge compiled StructureMap with $file" >&2
    return 1
  fi
  rm -f "$compiled"
  # stdout is captured as the curl payload path — only the file path
  printf '%s\n' "$merged"
}

put_one() {
  # Always re-read resourceType + id from the JSON body for the REST URL.
  # Package filenames are human-readable and must not drive PUT paths.
  local file="$1"
  local meta rt rid url code
  meta=$(read_fhir_meta "$file") || {
    echo "  SKIP (not a FHIR resource with id): ${file#$CONTENT_DIR/}" >&2
    return 1
  }
  rt="${meta%%$'\t'*}"
  rid="${meta#*$'\t'}"
  url="${FHIR_BASE_URL}/${rt}/${rid}"
  echo "PUT ${rt}/${rid}  ← ${file#$CONTENT_DIR/}"
  local payload="$file"
  local cleanup=""
  if [[ "$rt" == "StructureMap" ]]; then
    payload="$(structuremap_payload "$file")" || return 1
    if [[ "$payload" != "$file" ]]; then
      cleanup="$payload"
    fi
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    rm -f "$cleanup"
    return 0
  fi
  code=$(
    curl "${CURL_OPTS[@]}" -o /tmp/tricc-fhir-push-body.$$ -w '%{http_code}' \
      -X PUT "$url" \
      "${AUTH_HDR[@]}" \
      -H 'Content-Type: application/fhir+json' \
      --data-binary @"$payload"
  ) || true
  rm -f "$cleanup"
  if [[ "$code" =~ ^2 ]]; then
    echo "  OK $code"
  else
    echo "  FAIL HTTP $code" >&2
    head -c 500 /tmp/tricc-fhir-push-body.$$ >&2 || true
    echo >&2
    rm -f /tmp/tricc-fhir-push-body.$$
    return 1
  fi
  rm -f /tmp/tricc-fhir-push-body.$$
}

FAIL=0
for file in "${ORDERED[@]}"; do
  if ! put_one "$file"; then
    FAIL=1
  fi
done

if [[ "$FAIL" -ne 0 ]]; then
  echo "=== finished with errors ===" >&2
  exit 1
fi
echo "=== done ==="
