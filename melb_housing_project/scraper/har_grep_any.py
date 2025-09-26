# har_grep_any.py
import json, re, base64
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pandas as pd

HAR = Path("network.har")
OUT_CSV = Path("melbourne_housing.csv")

PRICE_RE = re.compile(r"(\d[\d,\.]+)")
LIKELY_KEYS = {
    "address","displayAddress","suburb","location","price","sold","soldDetails",
    "bedrooms","bathrooms","carspaces","features","url","href","listingId","id",
    "propertyType","landSize","land"
}

# --- helpers ---
def deep_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def body_text_from_har_entry(entry: Dict[str, Any]) -> str | None:
    content = deep_get(entry, ["response","content"]) or {}
    text = content.get("text")
    if text is None:
        return None
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8","ignore")
        except Exception:
            return None
    return text

def looks_like_listing_dict(d: Dict[str, Any]) -> bool:
    if not isinstance(d, dict): return False
    keys = set(d.keys())
    if keys & LIKELY_KEYS:
        score = 0
        for k in ["address","displayAddress","price","bedrooms","bathrooms","suburb","location","soldDetails"]:
            if k in keys: score += 1
        return score >= 2
    # also check nested address/price structures
    if isinstance(d.get("address"), dict): return True
    if isinstance(d.get("soldDetails"), dict): return True
    return False

def iter_arrays(obj: Any, path: Tuple[str,...]=()):
    if isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from iter_arrays(v, path + (f"[{i}]",))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_arrays(v, path + (k,))

def try_json_load(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None

def extract_json_blobs_from_html(text: str) -> List[dict]:
    blobs: List[dict] = []

    # window.__INITIAL_STATE__ =
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});", text, re.DOTALL)
    if m:
        js = m.group(1)
        # strip trailing semicolon if outside braces
        candidate = js.strip().rstrip(";")
        obj = try_json_load(candidate)
        if obj: blobs.append(obj)

    # <script type="application/ld+json"> ... </script>
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.DOTALL|re.IGNORECASE):
        candidate = m.group(1).strip()
        obj = try_json_load(candidate)
        if obj: blobs.append(obj)

    # Generic large JSON object blocks: find { ... } likely JSON (best-effort)
    # Look for chunks starting with { and having key quotes.
    for m in re.finditer(r'(\{[^<>{}]{500,}\})', text, re.DOTALL):
        candidate = m.group(1)
        obj = try_json_load(candidate)
        if obj: blobs.append(obj)

    return blobs

def flatten_item(item: Dict[str, Any]) -> Dict[str, Any]:
    def g(*p, default=None): return deep_get(item, list(p), default)
    addr_display = g("address","display") or g("displayAddress") or ""
    suburb = g("address","suburb") or g("location","suburb") or ""
    prop_type = g("propertyType") or g("listing","propertyType") or ""
    beds = g("bedrooms") or g("features","beds")
    baths = g("bathrooms") or g("features","baths")
    cars = g("carspaces") or g("features","cars")
    land = g("land","size","value") or g("landSize")
    sold_on = g("soldDetails","soldDate") or g("soldOn") or g("soldDate") or ""
    price_disp = g("price","display") or g("soldDetails","displayPrice") or g("priceText") or ""
    url = g("url") or g("href") or ""
    lid = g("id") or g("listingId") or ""
    return {
        "suburb": suburb,
        "address_display": addr_display,
        "property_type": prop_type,
        "bedrooms": beds,
        "bathrooms": baths,
        "car_spaces": cars,
        "land_size_sqm": land,
        "sale_date": sold_on,
        "sold_price_display": price_disp,
        "id": lid,
        "url": url,
    }

def parse_price(text: Any):
    if not isinstance(text, str): return None
    m = PRICE_RE.search(text.replace(" ", ""))
    return float(m.group(1).replace(",", "")) if m else None

def main():
    if not HAR.exists():
        print("ERROR: network.har not found")
        return

    with open(HAR, "r", encoding="utf-8") as f:
        har = json.load(f)

    entries = (har.get("log", {}) or {}).get("entries", []) or []
    rows: List[Dict[str, Any]] = []
    arrays_checked = arrays_matched = 0
    html_checked = js_checked = 0

    for e in entries:
        mime = deep_get(e, ["response","content","mimeType"]) or ""
        text = body_text_from_har_entry(e)
        if not text:
            continue

        # Case 1: JSON bodies
        if "json" in mime:
            payload = try_json_load(text)
            if not isinstance(payload, (dict, list)):
                continue
            for path, arr in iter_arrays(payload):
                if not isinstance(arr, list): continue
                arrays_checked += 1
                dicts = [x for x in arr if isinstance(x, dict)]
                if not dicts: continue
                if looks_like_listing_dict(dicts[0]):
                    arrays_matched += 1
                    rows.extend(flatten_item(d) for d in dicts)

        # Case 2: HTML with embedded JSON
        elif "html" in mime:
            html_checked += 1
            blobs = extract_json_blobs_from_html(text)
            for blob in blobs:
                for path, arr in iter_arrays(blob):
                    if not isinstance(arr, list): continue
                    dicts = [x for x in arr if isinstance(x, dict)]
                    if not dicts: continue
                    if looks_like_listing_dict(dicts[0]):
                        arrays_matched += 1
                        rows.extend(flatten_item(d) for d in dicts)

        # Case 3: JS with embedded JSON
        elif "javascript" in mime:
            js_checked += 1
            blobs = extract_json_blobs_from_html(text)  # reuse same heuristics
            for blob in blobs:
                for path, arr in iter_arrays(blob):
                    if not isinstance(arr, list): continue
                    dicts = [x for x in arr if isinstance(x, dict)]
                    if not dicts: continue
                    if looks_like_listing_dict(dicts[0]):
                        arrays_matched += 1
                        rows.extend(flatten_item(d) for d in dicts)

    if not rows:
        print("[WARN] Still no listing-like data found.")
        print("Try re-capturing (longer waits), or send the first ~60 lines of one HTML response (we'll target exact keys).")
        return

    df = pd.DataFrame(rows)
    # Deduplicate
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="first")
    else:
        df = df.drop_duplicates(subset=["address_display","suburb"], keep="first")

    df["sold_price"] = df["sold_price_display"].apply(parse_price)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")

    print(f"[DONE] Arrays checked: {arrays_checked}, matched: {arrays_matched}, HTML scanned: {html_checked}, JS scanned: {js_checked}")
    print(f"[DONE] Wrote {len(df)} rows → {OUT_CSV.resolve()}")

if __name__ == "__main__":
    main()
