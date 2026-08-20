#!/usr/bin/env bash
# Compile a FHIR Mapping Language .map to StructureMap JSON via HAPI parse.
#
# Usage:
#   ./compile-structuremap.sh <file.map> [out.json]
#
# Resolution order for the compiler:
#   1. FHIR_SM_COMPILER_JAR          — prebuilt fat/runnable jar
#   2. FHIR_SM_COMPILER_CLASSPATH    — already-built class + HAPI jars
#   3. Cached jars + CompileStructureMap.java (javac, or docker eclipse-temurin)
#
# Exit 0 writes JSON to out.json or stdout. Parse failures are non-zero.

set -euo pipefail

MAP_FILE="${1:-}"
OUT_FILE="${2:-}"
if [[ -z "$MAP_FILE" || ! -f "$MAP_FILE" ]]; then
  echo "Usage: $0 <file.map> [out.json]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JAVA_SRC="${COMPILE_STRUCTUREMAP_JAVA:-$SCRIPT_DIR/CompileStructureMap.java}"
CACHE_DIR="${FHIR_SM_COMPILER_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/tricc/hapi-fml-compiler}"
R4_VER="${FHIR_SM_R4_VERSION:-6.0.22}"
HAPI_BASE_VER="${FHIR_SM_HAPI_BASE_VERSION:-6.8.0}"
MAVEN_BASE="${FHIR_SM_MAVEN_BASE:-https://repo1.maven.org/maven2}"
DOCKER_IMAGE="${FHIR_SM_COMPILER_IMAGE:-eclipse-temurin:17-jdk}"

run_compiled() {
  local cp="$1"
  shift
  if [[ -n "$OUT_FILE" ]]; then
    java -cp "$cp" CompileStructureMap "$MAP_FILE" "$OUT_FILE"
  else
    java -cp "$cp" CompileStructureMap "$MAP_FILE"
  fi
}

if [[ -n "${FHIR_SM_COMPILER_JAR:-}" ]]; then
  if [[ -n "$OUT_FILE" ]]; then
    java -jar "$FHIR_SM_COMPILER_JAR" "$MAP_FILE" "$OUT_FILE"
  else
    java -jar "$FHIR_SM_COMPILER_JAR" "$MAP_FILE"
  fi
  exit 0
fi

if [[ -n "${FHIR_SM_COMPILER_CLASSPATH:-}" ]]; then
  run_compiled "$FHIR_SM_COMPILER_CLASSPATH"
  exit 0
fi

mkdir -p "$CACHE_DIR"

download_jar() {
  local rel="$1"
  local dest="$2"
  if [[ -f "$dest" ]]; then
    return 0
  fi
  echo "fetch $rel" >&2
  curl -fsSL "$MAVEN_BASE/$rel" -o "$dest.partial"
  mv "$dest.partial" "$dest"
}

# Pinned HL7 core + HAPI base (same family OpenSRP 6.8 / org.hl7.fhir.r4 6.0.22 uses).
download_jar \
  "ca/uhn/hapi/fhir/org.hl7.fhir.r4/${R4_VER}/org.hl7.fhir.r4-${R4_VER}.jar" \
  "$CACHE_DIR/org.hl7.fhir.r4-${R4_VER}.jar"
download_jar \
  "ca/uhn/hapi/fhir/org.hl7.fhir.utilities/${R4_VER}/org.hl7.fhir.utilities-${R4_VER}.jar" \
  "$CACHE_DIR/org.hl7.fhir.utilities-${R4_VER}.jar"
download_jar \
  "ca/uhn/hapi/fhir/hapi-fhir-base/${HAPI_BASE_VER}/hapi-fhir-base-${HAPI_BASE_VER}.jar" \
  "$CACHE_DIR/hapi-fhir-base-${HAPI_BASE_VER}.jar"

# Common runtime deps of utilities / r4 JSON compose (downloaded if missing).
download_jar \
  "com/google/code/gson/gson/2.10.1/gson-2.10.1.jar" \
  "$CACHE_DIR/gson-2.10.1.jar"
download_jar \
  "commons-io/commons-io/2.15.1/commons-io-2.15.1.jar" \
  "$CACHE_DIR/commons-io-2.15.1.jar"
download_jar \
  "commons-codec/commons-codec/1.16.1/commons-codec-1.16.1.jar" \
  "$CACHE_DIR/commons-codec-1.16.1.jar"
download_jar \
  "org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar" \
  "$CACHE_DIR/commons-lang3-3.14.0.jar"
download_jar \
  "org/apache/commons/commons-text/1.11.0/commons-text-1.11.0.jar" \
  "$CACHE_DIR/commons-text-1.11.0.jar"
download_jar \
  "org/slf4j/slf4j-api/2.0.12/slf4j-api-2.0.12.jar" \
  "$CACHE_DIR/slf4j-api-2.0.12.jar"
download_jar \
  "org/slf4j/slf4j-nop/2.0.12/slf4j-nop-2.0.12.jar" \
  "$CACHE_DIR/slf4j-nop-2.0.12.jar"
download_jar \
  "com/google/guava/guava/32.1.3-jre/guava-32.1.3-jre.jar" \
  "$CACHE_DIR/guava-32.1.3-jre.jar"
download_jar \
  "com/google/guava/failureaccess/1.0.2/failureaccess-1.0.2.jar" \
  "$CACHE_DIR/failureaccess-1.0.2.jar"
download_jar \
  "org/fhir/ucum/1.0.3/ucum-1.0.3.jar" \
  "$CACHE_DIR/ucum-1.0.3.jar"

# Explicit classpath — javac wildcards + SELinux docker mounts are unreliable.
build_cp() {
  local prefix="${1:-$CACHE_DIR}"
  local first=1
  local f
  for f in "$CACHE_DIR"/*.jar; do
    [[ -f "$f" ]] || continue
    if [[ "$prefix" == "$CACHE_DIR" ]]; then
      if [[ $first -eq 1 ]]; then
        printf '%s' "$f"
        first=0
      else
        printf ':%s' "$f"
      fi
    else
      local base
      base="$(basename "$f")"
      if [[ $first -eq 1 ]]; then
        printf '%s/%s' "$prefix" "$base"
        first=0
      else
        printf ':%s/%s' "$prefix" "$base"
      fi
    fi
  done
}

HOST_CP="$(build_cp "$CACHE_DIR")"
CLASS_FILE="$CACHE_DIR/CompileStructureMap.class"
if [[ ! -f "$JAVA_SRC" ]]; then
  echo "ERROR: CompileStructureMap.java not found at $JAVA_SRC" >&2
  exit 1
fi

need_compile=0
if [[ ! -f "$CLASS_FILE" || "$JAVA_SRC" -nt "$CLASS_FILE" ]]; then
  need_compile=1
fi

if [[ "$need_compile" -eq 1 ]]; then
  if command -v javac >/dev/null 2>&1; then
    javac -cp "$HOST_CP" -d "$CACHE_DIR" "$JAVA_SRC"
  elif command -v docker >/dev/null 2>&1; then
    # :z relabels for Fedora/RHEL SELinux so the container can read the cache.
    docker run --rm \
      --user "$(id -u):$(id -g)" \
      -e HOME=/tmp \
      -v "$CACHE_DIR:/out:z" \
      -v "$JAVA_SRC:/src/CompileStructureMap.java:ro,z" \
      -w /out \
      "$DOCKER_IMAGE" \
      javac -cp "$(build_cp /out)" -d /out /src/CompileStructureMap.java
  else
    echo "ERROR: need javac or docker to compile CompileStructureMap.java" >&2
    echo "  set FHIR_SM_COMPILER_JAR or FHIR_SM_COMPILER_CLASSPATH, or install a JDK" >&2
    exit 1
  fi
fi

# Class must be first so our CompileStructureMap wins over any similarly named jar class.
run_compiled "$CACHE_DIR:$HOST_CP"
