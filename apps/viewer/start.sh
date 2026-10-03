#!/bin/sh
# Merge the build-time seed cache into the persistent volume without
# overwriting anything already there (the store is content-addressed), then
# serve the viewer.
set -e
mkdir -p "$CADGEN_CACHE_DIR"
cp -an /srv/cache-seed/. "$CADGEN_CACHE_DIR"/
echo "cache: $(du -sh "$CADGEN_CACHE_DIR" | cut -f1) at $CADGEN_CACHE_DIR"
cd /srv/models
exec cadgen viewer --host 0.0.0.0 --port 8080 --no-registry
