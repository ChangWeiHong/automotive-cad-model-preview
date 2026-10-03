#!/usr/bin/env bash
# Pre-build the complete viewer cache locally, so the server computes nothing:
#   1. compile every STEP
#   2. derive the surface data the viewer needs
#   3. open each model once in a headless browser to cache its meshes
# Output: build/cadgen-cache (shipped inside the Fly image by deploy.sh).
#
#   scripts/build.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
PY="$root/.venv/bin/python"
CADGEN="$root/.venv/bin/cadgen"
[ -x "$CADGEN" ] || { echo "error: run once: uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python 'cadgen[snapshot]==0.7.6' && .venv/bin/python -m playwright install chromium" >&2; exit 1; }

export CADGEN_CACHE_DIR="$root/build/cadgen-cache"
export CADGEN_DAEMON=0
export CADGEN_STORE_MAX=1000GB
mkdir -p "$CADGEN_CACHE_DIR"

cd models
files=()
while IFS= read -r f; do files+=("${f#./}"); done < <(find . -type f \( -iname '*.step' -o -iname '*.stp' \) | sort)
for f in "${files[@]}"; do
  echo "== $f"
  "$CADGEN" step compile "$f"
  "$CADGEN" glb build "$f" "$root/build/warm.glb" >/dev/null && rm -f "$root/build/warm.glb"
done

# 3. warm meshes through the real viewer + a headless browser
log="$root/build/viewer.log"
"$CADGEN" viewer --host 127.0.0.1 --ephemeral --no-registry --json > "$log" 2>&1 &
vpid=$!
trap 'kill $vpid 2>/dev/null || true' EXIT
for _ in $(seq 60); do grep -q '"url"' "$log" && break; sleep 1; done
url="$(sed -n 's/.*"url":"\([^"]*\)".*/\1/p' "$log" | head -1)"
[ -n "$url" ] || { echo "error: viewer did not start"; cat "$log"; exit 1; }
"$PY" "$root/scripts/warm.py" "$url" "${files[@]}"

echo "cache ready: $(du -sh "$CADGEN_CACHE_DIR" | cut -f1) at build/cadgen-cache"
