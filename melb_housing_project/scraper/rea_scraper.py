"""
realestate.com.au scraper — for Essendon, Bentleigh, Burwood
⚠️ Educational use only. Respect robots.txt and Terms of Use.

Quick start:
    cd scraper
    pip install selenium webdriver-manager pandas
    python rea_scraper.py

Output:
    ../data/melbourne_housing.csv
"""

import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# =========================
# CONFIG
# =========================
SEARCH_URLS = [
    "https://www.realestate.com.au/sold/in-essendon,+vic+3040/list-1",
    "https://www.realestate.com.au/sold/in-bentleigh,+vic+3204/list-1",
    "https://www.realestate.com.au/sold/in-burwood,+vic+3125/list-1",
]

PAGES_PER_SUBURB = 6
PAUSE = 2.0
DETAIL_PAUSE = 1.5
HEADLESS = False

OUT_CSV = Path(__file__).resolve().parents[1] / "data" / "melbourne_housing.csv"

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
    agency: str = ""
    url: str = ""

# =========================
# BROWSER
# =========================
def get_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1400,1000")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

# =========================
# HELPERS
# =========================
def extract_first_number(text: str) -> Optional[float]:
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", (text or "").replace(",", ""))
    return float(m.group(1)) if m else None

def safe_int(x):
    try:
        return int(float(x))
    except:
        return None

# =========================
# PARSERS
# =========================
def parse_list_card(card) -> Listing:
    """Parse listing card from suburb results page with multiple fallbacks."""
    title = ""
    try:
        title = card.find_element(By.CSS_SELECTOR, "[data-testid*='address']").text
    except:
        try:
            title = card.text.split("\n")[0]
        except:
            title = ""

    url = ""
    try:
        url_el = card.find_element(By.TAG_NAME, "a")
        url = url_el.get_attribute("href")
    except:
        pass

    bedrooms = bathrooms = car_spaces = None
    try:
        feat = card.find_element(By.CSS_SELECTOR, "[data-testid*='property-features']").text.lower()
    except:
        feat = card.text.lower()

    if "bed" in feat:
        bedrooms = extract_first_number(feat)
    if "bath" in feat:
        bathrooms = extract_first_number(feat)
    if "car" in feat:
        car_spaces = extract_first_number(feat)

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
        bedrooms=safe_int(bedrooms),
        bathrooms=safe_int(bathrooms),
        car_spaces=safe_int(car_spaces),
        url=url,
    )

def parse_detail_page(driver: webdriver.Chrome, listing: Listing) -> Listing:
    """Extract sold price, date, property type, land size from detail page."""
    if not listing.url:
        return listing

    driver.get(listing.url)
    time.sleep(DETAIL_PAUSE)

    # Sold price
    price_text = ""
    for selector in [
        "[data-testid='listing-summary-property-price']",
        "[data-testid='listing-details__summary-title']",
    ]:
        try:
            price_text = driver.find_element(By.CSS_SELECTOR, selector).text
            break
        except:
            continue
    if not price_text:
        try:
            price_text = driver.find_element(By.XPATH, "//*[contains(text(),'$')]").text
        except:
            pass
    if price_text:
        print("PRICE FOUND:", price_text)
        maybe = extract_first_number(price_text)
        if maybe:
            listing.sold_price = maybe

    # Sale date
    try:
        el = driver.find_element(By.XPATH, "//*[contains(text(),'Sold on')]")
        listing.sale_date = el.text.replace("Sold on", "").strip()
    except:
        pass

    # Property type & land size
    try:
        info_nodes = driver.find_elements(By.XPATH,
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'property type') "
            "or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'land size')]"
        )
        for el in info_nodes:
            txt = el.text.strip()
            if "property type" in txt.lower() and ":" in txt:
                listing.property_type = txt.split(":", 1)[1].strip()
            if "land size" in txt.lower():
                ls = extract_first_number(txt)
                if ls:
                    listing.land_size_sqm = ls
    except:
        pass

    # Agency
    try:
        agency_el = driver.find_element(By.CSS_SELECTOR, "[data-testid='listing-details__agent-brand-name']")
        listing.agency = agency_el.text.strip()
    except:
        pass

    return listing

# =========================
# SCRAPER
# =========================
def scrape_search(driver: webdriver.Chrome, base_url: str):
    found = []
    for page in range(1, PAGES_PER_SUBURB + 1):
        url = base_url.replace("list-1", f"list-{page}")
        driver.get(url)

        # wait for page to load and scroll
        time.sleep(PAUSE)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # Try multiple selectors for cards
        cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid*='listing']")
        if not cards:
            cards = driver.find_elements(By.CSS_SELECTOR, "article")
        if not cards:
            cards = driver.find_elements(By.XPATH, "//a[contains(@href,'/property-')]")

        print(f"[DEBUG] Found {len(cards)} cards on {url}")

        for card in cards:
            try:
                li = parse_list_card(card)
                found.append(li)
            except Exception as e:
                print("Card parse error:", e)

        time.sleep(PAUSE / 2)
    return found

def run() -> pd.DataFrame:
    driver = get_driver(headless=HEADLESS)
    all_listings = []
    try:
        for s_url in SEARCH_URLS:
            print(f"[INFO] Scraping: {s_url}")
            batch = scrape_search(driver, s_url)
            print(f"[INFO] Cards: {len(batch)}")

            for i, li in enumerate(batch, 1):
                if not li.url:
                    continue
                try:
                    parse_detail_page(driver, li)
                except Exception as e:
                    print(f" Detail parse fail ({i}/{len(batch)}): {e}")
                time.sleep(DETAIL_PAUSE)
            all_listings.extend(batch)
    finally:
        driver.quit()

    return pd.DataFrame([asdict(x) for x in all_listings])

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    df = run()

    cols = [
        "suburb","address","property_type","bedrooms","bathrooms","car_spaces",
        "land_size_sqm","building_size_sqm","sale_date","sold_price",
        "agency","url"
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"[DONE] Saved {len(df)} rows to {OUT_CSV.resolve()}")
