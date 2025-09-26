# har_grep_json.py
import json, re, base64
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pandas as pd

HAR = Path("network.har")
OUT_CSV = Path("melbourne_housing.csv")

PRICE_RE = re.compile(r"(\d[\d,\.]+)")
LIKELY_KEYS = {"address","displayAddress","suburb","location","price","sold","soldDetails","bedrooms","bathrooms","carspaces","features","url","href","listingId","id","propertyType","landSize","land"}

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
    # Must share at least a few “listing-ish” keys somewhere in the dict
    if keys & LIKELY_KEYS:
        # Give extra credit if it has some core things
        score = 0
        for k in ["address","displayAddress","price","bedrooms","bathrooms","suburb","location","soldDetails"]:
            if k in keys: score += 1
        return score >= 2
    return False

def iter_arrays(obj: Any, path: Tuple[str,...]=()):
    if isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from iter_arrays(v, path + (f"[{i}]",))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_arrays(v, path + (k,))

def flatten_item(item: Dict[str, Any]) -> Dict[str, Any]:
    # Robust flatten similar to earlier scripts
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

    entries = deep_get(har, ["log","entries"]) or []
    candidates: List[Dict[str, Any]] = []
    arrays_checked = 0
    arrays_matched = 0

    for e in entries:
        # only look at JSON-ish responses
        mime = deep_get(e, ["response","content","mimeType"]) or ""
        if "json" not in mime:
            continue
        text = body_text_from_har_entry(e)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except Exception:
            continue

        # scan all arrays inside the JSON
        for path, arr in iter_arrays(payload):
            if not isinstance(arr, list):
                continue
            arrays_checked += 1
            # If the array contains dicts that look like listings, keep them
            dicts = [x for x in arr if isinstance(x, dict)]
            if not dicts:
                continue
            sample = dicts[0]
            if looks_like_listing_dict(sample):
                arrays_matched += 1
                candidates.extend(dicts)

    if not candidates:
        print("[WARN] No listing-like arrays found in HAR JSON bodies.")
        print("Try re-capturing with longer waits, or send me the first 50 lines of a sample JSON to map keys exactly.")
        return

    # Deduplicate-ish by id/address
    rows = [flatten_item(item) for item in candidates]
    df = pd.DataFrame(rows)
    # drop rows that are empty in key fields
    if "id" in df.columns:
        df = df.drop_duplicates(subset=["id"], keep="first")
    else:
        df = df.drop_duplicates(subset=["address_display","suburb"], keep="first")

    df["sold_price"] = df["sold_price_display"].apply(parse_price)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"[DONE] Arrays checked: {arrays_checked}, matched: {arrays_matched}")
    print(f"[DONE] Wrote {len(df)} rows → {OUT_CSV.resolve()}")

if __name__ == "__main__":
    main()
