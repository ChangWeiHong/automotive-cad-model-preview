# CAD Viewer backend + client (the same `cadgen viewer` used locally),
# serving the repo's models/ directory. Build context: the repo root.
FROM python:3.11-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libglu1-mesa libxrender1 libxext6 libsm6 libfontconfig1 libgomp1 nodejs \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cadgen==0.7.6

ENV CADGEN_CACHE_DIR=/srv/cadgen-cache \
    CADGEN_DAEMON=0 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/models
COPY models/ /srv/models/

# Compile every STEP at build time so the first visitor never waits.
RUN find . -type f \( -iname '*.step' -o -iname '*.stp' \) -print0 \
  | xargs -0 -r -n1 sh -c 'echo "compiling $0" && cadgen step compile "$0"'

EXPOSE 8080
CMD ["cadgen", "viewer", "--host", "0.0.0.0", "--port", "8080", "--no-registry"]
