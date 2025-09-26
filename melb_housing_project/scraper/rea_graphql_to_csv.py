"""
Browser-assisted capture of SOLD listings from realestate.com.au
- Opens a real Chromium window (headed)
- Navigates suburb results pages (Essendon, Bentleigh, Burwood)
- Listens for GraphQL 'soldSearchByQuery' responses in-session
- Parses JSON -> CSV: melbourne_housing.csv

Educational use only. Respect the site's terms & robots.
"""

import json
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Set

import pandas as pd
from playwright.sync_api import sync_playwright, Response, Route, Page

# ------------------
# CONFIG
# ------------------
SUBURBS = [
    ("Essendon", "vic", "3040"),
    ("Bentleigh", "vic", "3204"),
    ("Burwood", "vic", "3125"),
]

# How many pages to visit per suburb (each page is /list-{n})
PAGES_PER_SUBURB = 6

# polite delays
NAV_DELAY_SEC = (1.2, 2.2)   # between page navigations
SCROLL_PAUSE = 0.8           # after each scroll

OUT_CSV = Path("melbourne_housing.csv")
RAW_DIR = Path("raw_json")   # saved JSON snapshots for debugging
RAW_DIR.mkdir(exist_ok=True)

# ------------------
# JSON utilities
# ------------------
def deep_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def find_results_block(payload_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the list of listing dicts from a GraphQL response."""
    d = payload_json.get("data", {})
    node = (
        d.get("soldSearchByQuery")
        or d.get("searchResults")
        or d.get("search")
        or d.get("listingsSearch")
        or d.get("residentialSearch")
    )
    if isinstance(node, dict):
        if isinstance(node.get("results"), dict) and isinstance(node["results"].get("items"), list):
            return node["results"]["items"]
        if isinstance(node.get("results"), list):
            return node["results"]
        if isinstance(node.get("edges"), list):
            return [e.get("node", e) for e in node["edges"]]
    # fallback: first list of dicts under data
    for v in d.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
    return []

def flatten_listing(item: Dict[str, Any]) -> Dict[str, Any]:
    g = lambda *p, default=None: deep_get(item, list(p), default)
    addr = g("address","display") or g("displayAddress") or ""
    suburb = g("address","suburb") or g("location","suburb") or ""
    prop_type = g("propertyType") or g("listing","propertyType") or ""
    beds = g("bedrooms") or g("features","beds")
    baths = g("bathrooms") or g("features","baths")
    cars = g("carspaces") or g("features","cars")
    land = g("land","size","value") or g("landSize")
    sold_on = g("soldDetails","soldDate") or g("soldOn") or g("soldDate") or ""
    price_disp = g("price","display") or g("soldDetails","displayPrice") or g("priceText") or ""
    url = g("url") or g("href") or ""
    listing_id = g("id") or g("listingId") or ""

    return {
        "suburb": suburb,
        "address_display": addr,
        "property_type": prop_type,
        "bedrooms": beds,
        "bathrooms": baths,
        "car_spaces": cars,
        "land_size_sqm": land,
        "sale_date": sold_on,
        "sold_price_display": price_disp,
        "id": listing_id,
        "url": url,
    }

PRICE_RE = re.compile(r"(\d[\d,\.]*)")

def parse_price(text: str):
    if not isinstance(text, str):
        return None
    m = PRICE_RE.search(text.replace(" ", ""))
    return float(m.group(1).replace(",", "")) if m else None

# ------------------
# Capture logic
# ------------------
def suburb_to_url(suburb: str, state: str, postcode: str, page_num: int) -> str:
    # URL format: https://www.realestate.com.au/sold/in-essendon,+vic+3040/list-1
    slug = f"in-{suburb.lower().replace(' ', '+')},+{state.lower()}+{postcode}"
    return f"https://www.realestate.com.au/sold/{slug}/list-{page_num}"

def human_pause(a: float, b: float):
    import random
    time.sleep(random.uniform(a, b))

def main():
    all_rows: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page: Page = context.new_page()

        # capture handler
        def on_response(resp: Response):
            try:
                if "lexa.realestate.com.au/graphql" not in resp.url:
                    return
                if resp.request.method != "POST":
                    return

                # inspect the request payload to filter operationName
                try:
                    req_json = resp.request.post_data_json
                except Exception:
                    req_json = None

                op_name = ""
                if isinstance(req_json, dict):
                    op_name = req_json.get("operationName") or ""
                if op_name != "soldSearchByQuery":
                    return

                data = resp.json()
                # Save raw for debugging (optional)
                RAW_DIR.mkdir(exist_ok=True)
                stamp = str(int(time.time() * 1000))
                with open(RAW_DIR / f"resp_{op_name}_{stamp}.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                items = find_results_block(data)
                for it in items:
                    row = flatten_listing(it)
                    lid = row.get("id") or ""
                    if lid and lid in seen_ids:
                        continue
                    if lid:
                        seen_ids.add(lid)
                    all_rows.append(row)
            except Exception:
                # swallow parse errors quietly; we just miss that packet
                pass

        page.on("response", on_response)

        # Visit each suburb & pages
        for suburb, state, pc in SUBURBS:
            print(f"[INFO] Suburb: {suburb} {pc}")
            for page_num in range(1, PAGES_PER_SUBURB + 1):
                url = suburb_to_url(suburb, state, pc, page_num)
                print(f"  → {url}")
                page.goto(url, wait_until="domcontentloaded")
                human_pause(*NAV_DELAY_SEC)

                # simple scroll to trigger lazy content
                for _ in range(3):
                    page.mouse.wheel(0, 1800)
                    time.sleep(SCROLL_PAUSE)

        # done
        browser.close()

    if not all_rows:
        print("\n[WARN] No rows captured. Try increasing PAGES_PER_SUBURB or scrolling more.")
        return

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["id"], keep="first")
    df["sold_price"] = df["sold_price_display"].apply(parse_price)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"\n[DONE] Saved {len(df)} unique rows → {OUT_CSV.resolve()}")
    print("  Raw JSON saved in:", RAW_DIR.resolve())

if __name__ == "__main__":
    main()
