import json, time, re, os
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd
from playwright.sync_api import sync_playwright, Response, Request, Page, BrowserContext

# -------- CONFIG --------
SUBURBS = [
    ("Essendon", "vic", "3040"),
    ("Bentleigh", "vic", "3204"),
    ("Burwood", "vic", "3125"),
]

PAGES_PER_SUBURB = 6
SCROLL_ROUNDS = 10          # more scroll passes per page
SCROLL_PAUSE = 1.2          # seconds between scrolls
POST_SCROLL_IDLE = 4.0      # wait after scrolling for late XHRs
NAV_WAIT_UNTIL = "networkidle"  # "domcontentloaded" or "networkidle"

OUT_DIR = Path("raw_json")
OUT_DIR.mkdir(exist_ok=True)

def suburb_url(name: str, state: str, pc: str, n: int) -> str:
    slug = f"in-{name.lower().replace(' ', '+')},+{state.lower()}+{pc}"
    return f"https://www.realestate.com.au/sold/{slug}/list-{n}"

def save_json(path: Path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)
    except Exception as e:
        print(f"[save_json] {path.name}: {e}")

def main():
    ops_seen = {}
    total_saved = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context: BrowserContext = browser.new_context(viewport={"width": 1400, "height": 900})
        page: Page = context.new_page()

        def dump_packet(prefix: str, req: Request, resp: Response | None):
            # Save raw request + response for every /graphql POST
            ts = str(int(time.time() * 1000))
            host = re.sub(r"\W+", "_", req.url.split('/')[2]) if "://" in req.url else "unknown"
            # Try to read request JSON
            try:
                req_json = req.post_data_json
            except Exception:
                req_json = {"raw": req.post_data()}

            op_name = ""
            if isinstance(req_json, dict):
                op_name = req_json.get("operationName") or ""
            ops_seen[op_name] = ops_seen.get(op_name, 0) + 1

            base = OUT_DIR / f"{prefix}_{host}_{op_name or 'unknown'}_{ts}"
            save_json(base.with_suffix(".req.json"), req_json)

            if resp is not None:
                try:
                    data = resp.json()
                except Exception:
                    try:
                        data = {"text": resp.text()}
                    except Exception:
                        data = {"_note": "non-json response"}
                save_json(base.with_suffix(".resp.json"), data)

            return 1

        # Hook BOTH requests and responses
        def on_request(req: Request):
            try:
                if req.method != "POST":
                    return
                if "/graphql" not in req.url:
                    return
                # we save request immediately; response will also be saved below
                # (sometimes requests fail: at least we keep the payload)
                dump_packet("rq", req, None)
            except Exception:
                pass

        def on_response(resp: Response):
            try:
                if resp.request and resp.request.method == "POST" and "/graphql" in resp.url:
                    dump_packet("rs", resp.request, resp)
            except Exception:
                pass

        context.on("request", on_request)
        context.on("response", on_response)

        # NAVIGATE & SCROLL
        for suburb, state, pc in SUBURBS:
            print(f"\n[INFO] Suburb: {suburb} {pc}")
            for n in range(1, PAGES_PER_SUBURB + 1):
                url = suburb_url(suburb, state, pc, n)
                print(f"  → {url}")
                page.goto(url, wait_until=NAV_WAIT_UNTIL)
                # slow scroll to trigger lazy loads + XHR bursts
                for _ in range(SCROLL_ROUNDS):
                    page.mouse.wheel(0, 1800)
                    time.sleep(SCROLL_PAUSE)
                time.sleep(POST_SCROLL_IDLE)

        browser.close()

    # Count files saved
    reqs = list(OUT_DIR.glob("*.req.json"))
    resps = list(OUT_DIR.glob("*.resp.json"))
    print(f"\n[INFO] Saved {len(reqs)} requests and {len(resps)} responses in {OUT_DIR.resolve()}")
    if ops_seen:
        print("[INFO] Operation names seen:")
        for k, v in ops_seen.items():
            print(f"  - {k or '<unknown>'}: {v}")
    else:
        print("[WARN] No GraphQL traffic captured. Keep the browser window focused, increase SCROLL_ROUNDS/POST_SCROLL_IDLE, and try again.")

if __name__ == "__main__":
    main()
