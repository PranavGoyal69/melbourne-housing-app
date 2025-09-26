"""
realestate.com.au scraper (sample) — EDUCATIONAL USE ONLY.
Respect robots.txt and Terms of Use. Go slow, avoid heavy requests.

What it does:
- Visits suburb "sold" search pages (you set the URLs).
- Collects listing cards and follows into each listing page (optional) to
  extract richer fields like sold price, sale date, property type, land size.

Setup:
    pip install selenium webdriver-manager pandas

Run:
    python rea_scraper.py

Output:
    ./melbourne_housing_raw.csv

Note:
- The site’s HTML changes frequently. You may need to tweak CSS selectors.
- Increase PAGES_PER_SUBURB to reach ~50+ per suburb.
"""

import time
import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# =========================
# CONFIG
# =========================

# Copy suburb "Sold" results URLs from realestate.com.au (with your filters applied).
# Use the page token 'list-1' below; the script will replace it with 'list-2', 'list-3', ...
SEARCH_URLS = [
    # EXAMPLES — replace with your three target suburbs
    "https://www.realestate.com.au/sold/in-tarneit,+vic+3029/list-1",
    "https://www.realestate.com.au/sold/in-carlton,+vic+3053/list-1",
    "https://www.realestate.com.au/sold/in-brighton,+vic+3186/list-1",
]

PAGES_PER_SUBURB = 3      # bump to 4–6+ to approach ~50 listings per suburb
PAUSE = 2.0               # seconds between actions
DETAIL_PAUSE = 1.5        # extra pause on detail page (be gentle)
HEADLESS = False          # True to hide browser

OUT_CSV = Path("./melbourne_housing_raw.csv")

# =========================
# DATA MODEL
# =========================

@dataclass
class Listing:
    suburb: str = ""
    address: str = ""
    property_type: str = ""
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    car_spaces: Optional[int] = None
    land_size_sqm: Optional[float] = None
    building_size_sqm: Optional[float] = None
    sale_date: str = ""
    sold_price: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    postcode: str = ""
    agency: str = ""
    year_built: Optional[int] = None
    has_garage: Optional[int] = None  # 1/0
    has_aircon: Optional[int] = None  # 1/0
    has_heating: Optional[int] = None # 1/0
    nearby_schools_count: Optional[int] = None
    distance_to_cbd_km: Optional[float] = None
    lot_frontage_m: Optional[float] = None
    notes: str = ""
    url: str = ""

# =========================
# BROWSER
# =========================

def get_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

# =========================
# HELPERS
# =========================

def to_int_safe(text: str) -> Optional[int]:
    try:
        return int(text.strip())
    except:
        return None

def to_float_safe(text: str) -> Optional[float]:
    try:
        return float(text.strip().replace(",", ""))
    except:
        return None

def extract_number(text: str) -> Optional[float]:
    """Extract first number from a string."""
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    return float(m.group(1)) if m else None

# =========================
# PARSERS
# =========================

def parse_list_card(card) -> Listing:
    """
    Parse listing card on the suburb results page.
    CSS selectors may need tweaks over time.
    """
    # Address/title
    try:
        title = card.find_element(By.CSS_SELECTOR, "[data-testid='listing-card-address']").text
    except:
        title = ""

    # Link
    try:
        url_el = card.find_element(By.CSS_SELECTOR, "a[data-testid='listing-card-link']")
        url = url_el.get_attribute("href")
    except:
        url = ""

    # Meta: usually shows bedrooms, bathrooms, car
    bedrooms = bathrooms = car_spaces = None
    try:
        meta = card.find_element(By.CSS_SELECTOR, "[data-testid='property-features']").text
        # naive parse
        # e.g., "3 bed 2 bath 1 car"
        for token in meta.split():
            lower = token.lower()
            if "bed" in lower:
                bedrooms = extract_number(meta)
            if "bath" in lower:
                bathrooms = extract_number(meta.split("bath")[0].split()[-1]) or bathrooms
            if "car" in lower:
                car_spaces = extract_number(meta.split("car")[0].split()[-1]) or car_spaces
    except:
        pass

    # Suburb heuristic from title "12 Smith St, Tarneit, Vic 3029"
    suburb = ""
    try:
        parts = [p.strip() for p in title.split(",")]
        if len(parts) >= 2:
            suburb = parts[-2]
    except:
        pass

    return Listing(
        suburb=suburb,
        address=title,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        car_spaces=car_spaces,
        url=url,
    )

def parse_detail_page(driver: webdriver.Chrome, listing: Listing) -> Listing:
    """
    Open the listing detail page and extract richer fields:
    sold price, sale date, property type, land size, etc.
    All selectors are best-effort and may require adjusting.
    """
    if not listing.url:
        return listing

    driver.get(listing.url)
    time.sleep(DETAIL_PAUSE)

    # Sold price & sale date — often contained in a 'Sold on' or 'Price' block
    # Try multiple patterns to be resilient.
    try:
        # e.g., data-testid='listing-summary-property-price'
        price_block = driver.find_element(By.CSS_SELECTOR, "[data-testid='listing-summary-property-price']").text
        # Examples: "$650,000", "$1,250,000"
        price_num = extract_number(price_block)
        if price_num and "$" in price_block:
            # assume it's already dollars
            listing.sold_price = price_num
    except:
        pass

    # Sale date
    try:
        # e.g., "Sold on 15 Aug 2024"
        sold_on = driver.find_element(By.XPATH, "//*[contains(text(),'Sold on')]").text
        # crude capture of date portion
        listing.sale_date = sold_on.replace("Sold on", "").strip()
    except:
        pass

    # Property attributes block
    # Try to find a summary specs area with "Property type", "Land size", etc.
    try:
        specs = driver.find_elements(By.XPATH, "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'),'property type') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'),'land size')]")
        for el in specs:
            txt = el.text.lower()
            if "property type" in txt:
                # e.g., "Property type: House"
                if ":" in el.text:
                    listing.property_type = el.text.split(":", 1)[1].strip()
            if "land size" in txt:
                ls = extract_number(el.text)
                if ls:
                    # Some listings say "Land size: 400 m²" — we keep sqm
                    listing.land_size_sqm = ls
    except:
        pass

    # Agency (optional)
    try:
        # e.g., footer/agent badge
        agency_el = driver.find_element(By.CSS_SELECTOR, "[data-testid='listing-details__agent-brand-name']")
        listing.agency = agency_el.text.strip()
    except:
        pass

    # Try lat/long if embedded in meta tags or scripts (lightweight best-effort)
    # Skipping heavy script parsing to keep this example simple.

    return listing

# =========================
# SCRAPE RUNNERS
# =========================

def scrape_suburb_list(driver: webdriver.Chrome, base_url: str) -> List[Listing]:
    results: List[Listing] = []
    for page in range(1, PAGES_PER_SUBURB + 1):
        url = base_url.replace("list-1", f"list-{page}")
        driver.get(url)
        time.sleep(PAUSE)

        cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='listing-card']")
        for card in cards:
            try:
                li = parse_list_card(card)
                results.append(li)
            except Exception as e:
                print("Card parse error:", e)
        time.sleep(PAUSE)
    return results

def run() -> pd.DataFrame:
    driver = get_driver(headless=HEADLESS)
    all_listings: List[Listing] = []
    try:
        for s_url in SEARCH_URLS:
            print(f"[INFO] Scraping search: {s_url}")
            batch = scrape_suburb_list(driver, s_url)
            print(f"[INFO] Found {len(batch)} cards on configured pages.")
            # OPTIONAL: follow into each card for richer data (price, date, type, land size)
            for i, li in enumerate(batch, 1):
                if not li.url:
                    continue
                try:
                    li = parse_detail_page(driver, li)
                except Exception as e:
                    print(f" Detail parse failed ({i}/{len(batch)}):", e)
                # small courteous pause between detail pages
                time.sleep(DETAIL_PAUSE)
            all_listings.extend(batch)
    finally:
        driver.quit()

    rows = [asdict(x) for x in all_listings]
    df = pd.DataFrame(rows)
    return df

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    df = run()

    # Ensure consistent column order (good for your ML template)
    cols = [
        "suburb","address","property_type","bedrooms","bathrooms","car_spaces",
        "land_size_sqm","building_size_sqm","sale_date","sold_price","latitude",
        "longitude","postcode","agency","year_built","has_garage","has_aircon","has_heating",
        "nearby_schools_count","distance_to_cbd_km","lot_frontage_m","notes","url"
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    df.to_csv(OUT_CSV, index=False)
    print(f"[DONE] Saved {len(df)} rows to {OUT_CSV.resolve()}")
