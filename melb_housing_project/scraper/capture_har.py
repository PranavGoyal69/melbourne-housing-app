# capture_har.py
# Records ALL network traffic while you browse suburb SOLD pages, into network.har

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SUBURBS = [
    ("Essendon", "vic", "3040"),
    ("Bentleigh", "vic", "3204"),
    ("Burwood", "vic", "3125"),
]
PAGES_PER_SUBURB = 6
SCROLL_ROUNDS = 10
SCROLL_PAUSE = 1.2
POST_SCROLL_IDLE = 4.0

def suburb_url(name: str, state: str, pc: str, n: int) -> str:
    slug = f"in-{name.lower().replace(' ', '+')},+{state.lower()}+{pc}"
    return f"https://www.realestate.com.au/sold/{slug}/list-{n}"

def main():
    har_path = Path("network.har")
    if har_path.exists():
        har_path.unlink()  # start fresh

    with sync_playwright() as p:
        # Use your installed Edge/Chrome channel if you prefer:
        # browser = p.chromium.launch(channel="msedge", headless=False)
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])

        # IMPORTANT: record_har_path + include content
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            record_har_path=str(har_path),
            record_har_omit_content=False,   # we want full bodies
        )
        page = context.new_page()

        for suburb, state, pc in SUBURBS:
            print(f"\n[INFO] Suburb: {suburb} {pc}")
            for n in range(1, PAGES_PER_SUBURB + 1):
                url = suburb_url(suburb, state, pc, n)
                print(f"  → {url}")
                page.goto(url, wait_until="domcontentloaded")
                # Scroll multiple times to trigger XHRs
                for _ in range(SCROLL_ROUNDS):
                    page.mouse.wheel(0, 1800)
                    time.sleep(SCROLL_PAUSE)
                time.sleep(POST_SCROLL_IDLE)

        context.close()   # <-- flush HAR to disk
        browser.close()

    print(f"\n[DONE] HAR saved → {har_path.resolve()}")

if __name__ == "__main__":
    main()
