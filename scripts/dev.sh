#!/usr/bin/env bash
# Run the same viewer locally on http://127.0.0.1:3256 (needs `pip install cadgen==0.7.6`).
set -euo pipefail
cd "$(dirname "$0")/../models"
exec cadgen viewer --host 127.0.0.1 --port "${PORT:-3256}"
