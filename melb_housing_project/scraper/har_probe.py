# har_probe.py
import json, base64, os, re
from collections import Counter, defaultdict
from pathlib import Path

HAR_PATH = Path("network.har")
SAMPLES_DIR = Path("har_samples")
SAMPLES_DIR.mkdir(exist_ok=True)

def deep_get(d, path, default=None):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur

def get_resp_text(entry):
    content = deep_get(entry, ["response", "content"], {}) or {}
    text = content.get("text")
    if text is None:
        return None
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8", errors="ignore")
        except Exception:
            return None
    return text

def get_req_text(entry):
    post_data = deep_get(entry, ["request", "postData"], {}) or {}
    text = post_data.get("text")
    if text is None:
        return None
    # HAR request bodies are plain text; might be JSON
    return text

def main():
    if not HAR_PATH.exists():
        print("ERROR: network.har not found.")
        return

    with open(HAR_PATH, "r", encoding="utf-8") as f:
        har = json.load(f)

    entries = deep_get(har, ["log", "entries"], []) or []
    if not entries:
        print("HAR has no entries.")
        return

    host_counts = Counter()
    post_hosts = Counter()
    graphql_posts = 0
    json_resps = 0
    saved = 0
    opnames = Counter()
    content_types = Counter()

    for i, e in enumerate(entries):
        url = deep_get(e, ["request", "url"], "") or ""
        method = deep_get(e, ["request", "method"], "") or ""
        host = ""
        try:
            host = url.split("/")[2]
        except Exception:
            pass

        host_counts[host] += 1
        if method == "POST":
            post_hosts[host] += 1

        ct = deep_get(e, ["response", "content", "mimeType"]) or ""
        content_types[ct] += 1

        if method == "POST" and ("/graphql" in url or "realestate.com.au" in host):
            # Look for GraphQL opName in request body if any
            req_text = get_req_text(e)
            if req_text:
                try:
                    req_json = json.loads(req_text)
                    op = req_json.get("operationName")
                    if op:
                        opnames[op] += 1
                except Exception:
                    pass

            graphql_posts += 1

            # Save first few request/response samples to inspect
            if saved < 10:
                resp_text = get_resp_text(e)
                # Save raw response text (even if not JSON) for manual inspection
                base = SAMPLES_DIR / f"sample_{saved:02d}"
                if req_text:
                    (base.with_suffix(".req.txt")).write_text(req_text, encoding="utf-8", errors="ignore")
                if resp_text:
                    (base.with_suffix(".resp.txt")).write_text(resp_text, encoding="utf-8", errors="ignore")
                    # Count as JSON if parses
                    try:
                        json.loads(resp_text)
                        json_resps += 1
                    except Exception:
                        pass
                saved += 1

    print("\n=== HAR SUMMARY ===")
    print(f"Total entries: {len(entries)}")
    print(f"Unique hosts: {len(host_counts)}")
    print("Top hosts:")
    for h, c in host_counts.most_common(8):
        print(f"  {h:40s} {c}")

    print("\nPOST requests by host:")
    for h, c in post_hosts.most_common(8):
        print(f"  {h:40s} {c}")

    print(f"\nGraphQL/REA-ish POSTs seen: {graphql_posts}")
    print(f"Sample files saved to: {SAMPLES_DIR.resolve()}")
    print("\nOperation names observed (from request bodies):")
    if opnames:
        for op, c in opnames.most_common():
            print(f"  {op:30s} {c}")
    else:
        print("  (none found)")

    print("\nResponse content types observed (rough):")
    for t, c in content_types.most_common(8):
        print(f"  {t or '(none)'}: {c}")

if __name__ == "__main__":
    main()
