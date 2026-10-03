#!/usr/bin/env bash
# Deploy from this machine (no CI): the CAD Viewer (page + backend) to Fly.io.
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

if ! fly apps list --org "$FLY_ORG" 2>/dev/null | grep -q "^$APP\b"; then
  fly apps create "$APP" --org "$FLY_ORG"
fi
# the remote builder compiles every STEP into the image (amd64, no local emulation)
fly deploy . --config apps/viewer/fly.toml --remote-only --ha=false

echo
echo "models:"
for f in models/STEP/*.step models/STEP/*.stp; do
  [ -e "$f" ] || continue
  rel="${f#models/}"
  echo "  $BASE/?file=${rel//\//%2F}"
done
