#!/usr/bin/env bash
# Add a STEP file to the showcase and list its preview URL in README.md.
#
#   scripts/add-step.sh path/to/part.step [name]
#
# Copies the file to models/STEP/<name>.step. Then run scripts/deploy.sh.
set -euo pipefail

[ $# -ge 1 ] || { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
src="$1"
[ -f "$src" ] || { echo "error: file not found: $src" >&2; exit 1; }

name="${2:-$(basename "$src")}"
name="${name%.*}"
name="$(printf '%s' "$name" | tr ' ' '_' | tr -cd 'A-Za-z0-9._-')"
[ -n "$name" ] || { echo "error: give a name with letters/digits" >&2; exit 1; }

root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/models/STEP/$name.step"
cp "$src" "$dest"

app="$(sed -n 's/^app = "\(.*\)"/\1/p' "$root/apps/viewer/fly.toml")"
base="https://$app.fly.dev"
row="| \`$name\` | $base/?file=STEP%2F$name.step |"
readme="$root/README.md"
if ! grep -qF "STEP%2F$name.step" "$readme"; then
  # insert the row just above the end marker of the URL table
  awk -v row="$row" '/<!-- models:end -->/ { print row } { print }' "$readme" > "$readme.tmp"
  mv "$readme.tmp" "$readme"
fi

echo "added models/STEP/$name.step ($(du -h "$dest" | cut -f1))"
echo "preview (after deploy): $base/?file=STEP%2F$name.step"
echo "next: scripts/deploy.sh"
