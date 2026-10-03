#!/usr/bin/env bash
# Build the viewer cache locally, then deploy the CAD Viewer (page + backend)
# to Fly.io. No CI. SKIP_BUILD=1 reuses the last build/cadgen-cache.
#
#   scripts/deploy.sh
#
# Needs a one-time `fly auth login` (Willstack.ai org).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

FLY_ORG="${FLY_ORG:-willstack-ai-293}"
APP="$(sed -n 's/^app = "\(.*\)"/\1/p' apps/viewer/fly.toml)"
BASE="https://$APP.fly.dev"

if ! fly status -a "$APP" >/dev/null 2>&1; then
  fly apps create "$APP" --org "$FLY_ORG"
fi
if ! fly volumes list -a "$APP" 2>/dev/null | grep -q cad_cache; then
  fly volumes create cad_cache --size 10 --region sin -a "$APP" --yes
fi
# 1. pre-build the full cache locally (compile + surfaces + meshes)
[ "${SKIP_BUILD:-0}" = 1 ] || bash scripts/build.sh
# 2. ship it: the image only copies files, the server computes nothing
fly deploy . --config apps/viewer/fly.toml --remote-only --ha=false

echo
echo "models:"
for f in models/STEP/*.step models/STEP/*.stp; do
  [ -e "$f" ] || continue
  rel="${f#models/}"
  echo "  $BASE/?file=${rel//\//%2F}"
done
