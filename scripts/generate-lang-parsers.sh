#!/usr/bin/env bash
# Regenerate the Python parsers from tricc_oo/lang/ (feature/20261125-expression-languages.md).
#
#   scripts/generate-lang-parsers.sh            # writes into tricc_oo/converters/{cql,feel}/
#   scripts/generate-lang-parsers.sh --check    # regenerates into a temp dir, fails on drift
#
# Needs Java and antlr4-tools (pip install antlr4-tools); the ANTLR version is pinned to
# 4.13.2 to match antlr4-python3-runtime. Developers who do not change a grammar never run it:
# the generated files are committed.
set -euo pipefail

ANTLR_VERSION=4.13.2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LANG_DIR="$ROOT/tricc_oo/lang"
VERSION="$(tr -d '[:space:]' < "$LANG_DIR/VERSION")"
ANTLR="${ANTLR:-antlr4}"
if [ -x "$ROOT/.venv/bin/antlr4" ] && [ "$ANTLR" = antlr4 ]; then ANTLR="$ROOT/.venv/bin/antlr4"; fi

CHECK=0
if [ "${1:-}" = "--check" ]; then CHECK=1; fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

antlr() { (cd "$1" && shift && "$ANTLR" -v "$ANTLR_VERSION" -Dlanguage=Python3 -visitor -no-listener "$@"); }

# header: keep flake8 quiet (generated code) and record the package version
stamp() {
  local file="$1"
  { printf '# flake8: noqa\n# tricc-lang %s (tricc_oo/lang/VERSION)\n' "$VERSION"; cat "$file"; } > "$file.tmp"
  mv "$file.tmp" "$file"
}

# --- CQL: the TRICC profile and the untouched upstream grammar (standard-CQL libraries)
mkdir -p "$WORK/cql" "$WORK/out/cql"
cp "$LANG_DIR"/cql/*.g4 "$WORK/cql/"
antlr "$WORK/cql" tricc_cql.g4
antlr "$WORK/cql" cql.g4
for f in tricc_cqlLexer tricc_cqlParser tricc_cqlVisitor cqlLexer cqlParser cqlVisitor; do
  cp "$WORK/cql/$f.py" "$WORK/out/cql/$f.py"
  stamp "$WORK/out/cql/$f.py"
done

# --- FEEL: keep the generated lexer of tricc_feel.g4 only, then the TRICC cell parser
mkdir -p "$WORK/feel" "$WORK/out/feel"
cp "$LANG_DIR"/feel/*.g4 "$WORK/feel/"
antlr "$WORK/feel" tricc_feel.g4
antlr "$WORK/feel" TriccFeelParser.g4
for f in tricc_feelLexer TriccFeelParser TriccFeelParserVisitor; do
  cp "$WORK/feel/$f.py" "$WORK/out/feel/$f.py"
  stamp "$WORK/out/feel/$f.py"
done

if [ "$CHECK" = 1 ]; then
  status=0
  for kind in cql feel; do
    for f in "$WORK/out/$kind"/*.py; do
      target="$ROOT/tricc_oo/converters/$kind/$(basename "$f")"
      if ! cmp -s "$f" "$target"; then echo "drift: $target"; status=1; fi
    done
  done
  exit $status
fi

for kind in cql feel; do
  mkdir -p "$ROOT/tricc_oo/converters/$kind"
  cp "$WORK/out/$kind"/*.py "$ROOT/tricc_oo/converters/$kind/"
done
echo "generated parsers for tricc-lang $VERSION with ANTLR $ANTLR_VERSION"
