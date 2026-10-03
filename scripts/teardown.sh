#!/usr/bin/env bash
# Bring the showcase down after the demo: destroys the Fly app (asks first).
# The repo itself is left untouched.
set -euo pipefail
cd "$(dirname "$0")/.."
APP="$(sed -n 's/^app = "\(.*\)"/\1/p' apps/viewer/fly.toml)"
read -r -p "Destroy Fly app '$APP'? [y/N] " a
[ "$a" = y ] && fly apps destroy "$APP" --yes
echo "done"
