"""Open every model in a headless browser against a running CAD Viewer so the
viewer derives surfaces and the browser writes its meshes back to the cache.

    python scripts/warm.py http://127.0.0.1:PORT STEP/a.step [STEP/b.step ...]

A model counts as warm once no /__cad or /__tess_cache traffic has happened for
QUIET seconds (or after MAX seconds).
"""
import sys
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright

QUIET, MAX = 8.0, 300.0


def warm(page, base, rel):
    last = [time.time()]
    count = [0]

    def on_request(req):
        if "/__cad/" in req.url or "/__tess_cache/" in req.url:
            if "/__cad/preview" not in req.url and "/__cad/catalog" not in req.url:
                last[0] = time.time()
                count[0] += 1

    page.on("request", on_request)
    t0 = time.time()
    page.goto(f"{base}/?file={quote(rel, safe='')}", wait_until="domcontentloaded")
    while time.time() - t0 < MAX:
        page.wait_for_timeout(1000)
        if count[0] and time.time() - last[0] > QUIET:
            break
    page.remove_listener("request", on_request)
    print(f"warmed {rel}: {count[0]} requests in {time.time() - t0:.0f}s", flush=True)


def main():
    base, files = sys.argv[1].rstrip("/"), sys.argv[2:]
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        for rel in files:
            warm(page, base, rel)
        browser.close()


if __name__ == "__main__":
    main()
