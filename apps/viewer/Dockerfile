# CAD Viewer backend + client (the same `cadgen viewer` used locally),
# serving the repo's models/ directory. Build context: the repo root.
#
# Nothing is computed here: scripts/build.sh pre-builds the complete cache
# locally (compiled STEP trees, surface data and browser meshes) into
# build/cadgen-cache, which is copied in as the seed.
FROM python:3.11-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libglu1-mesa libxrender1 libxext6 libsm6 libfontconfig1 libgomp1 nodejs \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cadgen==0.7.6

ENV CADGEN_DAEMON=0 \
    PYTHONUNBUFFERED=1 \
    CADGEN_STORE_MAX=1000GB \
    CADGEN_CACHE_DIR=/data/cadgen-cache

COPY models/ /srv/models/
COPY build/cadgen-cache/ /srv/cache-seed/
COPY apps/viewer/start.sh /usr/local/bin/start.sh

EXPOSE 8080
CMD ["sh", "/usr/local/bin/start.sh"]
