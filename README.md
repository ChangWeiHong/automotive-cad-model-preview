# Automotive CAD Model Preview

Temporary showcase: STEP models opened in the **CAD Viewer** (`cadgen viewer`,
the same viewer used locally), hosted on Fly.io (page and backend in one app).
Everything is deployed from a local machine; there is no CI.

## Preview URLs

URL format: `https://awantech-cad-viewer.fly.dev/?file=STEP%2F<name>.step`. This is the same as the
local viewer, e.g. `http://127.0.0.1:3256/?file=STEP%2Fmyvi_v2.step`.

| Model | URL |
| --- | --- |
<!-- models:start -->
| `myvi_v2` | https://awantech-cad-viewer.fly.dev/?file=STEP%2Fmyvi_v2.step |
| `myvi` | https://awantech-cad-viewer.fly.dev/?file=STEP%2Fmyvi.step |
<!-- models:end -->

`scripts/add-step.sh` adds a row here automatically.

## Add a STEP file

```bash
scripts/add-step.sh ~/Downloads/new-part.step new_part   # 1. copy into models/STEP + add URL row
scripts/deploy.sh                                        # 2. build cache locally + redeploy (~5 min)
git add -A && git commit -m "Add new_part" && git push   # 3. save it
```

Then open `https://awantech-cad-viewer.fly.dev/?file=STEP%2Fnew_part.step`.

- The name becomes the URL: letters, digits, `.`, `_`, `-`.
- STEP files are stored with **Git LFS** (`.gitattributes`). GitHub rejects
  normal files over 100 MB.
- `scripts/deploy.sh` runs `scripts/build.sh` first. That builds the whole
  viewer cache **on this machine**: STEP compile, surface data, and browser
  meshes (each model is opened once in a headless browser). The Fly image only
  copies that cache, so the server computes nothing.

## Deploy (local)

One-time setup:

```bash
fly auth login          # Fly org: Willstack.ai (willstack-ai-293)
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python "cadgen[snapshot]==0.7.6"
.venv/bin/python -m playwright install chromium
```

Deploy:

```bash
scripts/deploy.sh       # builds + deploys the viewer; prints every model URL
```

## Tear down after the demo

```bash
scripts/teardown.sh     # destroys the Fly app (asks first)
```

## Cache

- The cache lives on the **server**, not in visitors' browsers, so every
  visitor shares it.
- It is stored on a Fly volume (`cad_cache`, mounted at `/data`). That keeps
  it across restarts and redeploys.
- Each deploy merges the freshly built cache into the volume without deleting
  anything.
- It never expires: `CADGEN_STORE_MAX=1000GB` stops cadgen from evicting
  entries, and the machine never auto-stops.

## Run locally

```bash
pip install cadgen==0.7.6
scripts/dev.sh          # http://127.0.0.1:3256/?file=STEP%2Fmyvi_v2.step
```

## Layout

```
models/STEP/        STEP files served by the viewer (Git LFS)
apps/viewer/        Dockerfile + fly.toml: `cadgen viewer` on Fly.io (app awantech-cad-viewer, region sin)
scripts/            add-step.sh, build.sh (+ warm.py), deploy.sh, teardown.sh, dev.sh
build/              locally built viewer cache (git-ignored, shipped in the image)
cad/myvi/           Perodua Myvi model sources (build123d/cadgen)
```

## Notes

- **Not authenticated.** The viewer is open to anyone with the URL. That is
  fine for a short demo; tear it down afterwards.
- Viewer machine: 4 dedicated CPUs, 8 GB RAM, always on
  (`auto_stop_machines = "off"`). Cache: 10 GB Fly volume.
- Rebuild the Myvi STEP from source: `python cad/myvi/src/myvi_v2.py`. Needs
  `cad/myvi/requirements.txt`. The source FBX is not committed (licence).
