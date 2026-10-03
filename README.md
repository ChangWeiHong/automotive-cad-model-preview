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
scripts/deploy.sh                                        # 2. redeploy the viewer (~5-10 min)
git add -A && git commit -m "Add new_part" && git push   # 3. save it
```

Then open `https://awantech-cad-viewer.fly.dev/?file=STEP%2Fnew_part.step`.

- The name becomes the URL: letters, digits, `.`, `_`, `-`.
- STEP files are stored with **Git LFS** (`.gitattributes`). GitHub rejects
  normal files over 100 MB.
- Every STEP is compiled during the Fly image build, so viewers never wait.
  Big files make the deploy slower, not the page.

## Deploy (local)

One-time login:

```bash
fly auth login          # Fly org: Willstack.ai (willstack-ai-293)
```

Deploy:

```bash
scripts/deploy.sh       # builds + deploys the viewer; prints every model URL
```

## Tear down after the demo

```bash
scripts/teardown.sh     # destroys the Fly app (asks first)
```

## Run locally

```bash
pip install cadgen==0.7.6
scripts/dev.sh          # http://127.0.0.1:3256/?file=STEP%2Fmyvi_v2.step
```

## Layout

```
models/STEP/        STEP files served by the viewer (Git LFS)
apps/viewer/        Dockerfile + fly.toml: `cadgen viewer` on Fly.io (app awantech-cad-viewer, region sin)
scripts/            add-step.sh, deploy.sh, teardown.sh, dev.sh
cad/myvi/           Perodua Myvi model sources (build123d/cadgen)
```

## Notes

- **Not authenticated.** The viewer is open to anyone with the URL. That is
  fine for a short demo; tear it down afterwards.
- Viewer machine: 2 GB shared CPU, one machine kept warm
  (`min_machines_running = 1`).
- Rebuild the Myvi STEP from source: `python cad/myvi/src/myvi_v2.py`. Needs
  `cad/myvi/requirements.txt`. The source FBX is not committed (licence).
