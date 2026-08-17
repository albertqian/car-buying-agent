"""
car_scraper.py
Scrapes Craigslist and Cars.com for car listings.
Writes results to data/results.json for Streamlit to consume.

Both sources are server-side rendered and scraper-tolerant at reasonable
request rates. Cars.com embeds structured JSON-LD in the page, giving us
clean title, price, mileage, and MPG data without fragile CSS selectors.
"""

import json
import time
import random
import requests
import argparse
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

MAKES = {
    "honda": "Honda",
    "hyundai": "Hyundai",
    "ford": "Ford",
    "gm": "GMC",
    "toyota": "Toyota",
}

# Craigslist city slugs — extend as needed
CL_CITIES = {
    "los angeles": "losangeles",
    "new york":    "newyork",
    "chicago":     "chicago",
    "houston":     "houston",
    "phoenix":     "phoenix",
    "seattle":     "seattle",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

OUTPUT_PATH = Path("data/results.json")

# ── Craigslist ────────────────────────────────────────────────────────────────

def scrape_craigslist(city_slug: str, make: str, max_price: int, min_mpg: int) -> list[dict]:
    """Scrape Craigslist cars+trucks for a given city and make."""
    results = []
    url = (
        f"https://{city_slug}.craigslist.org/search/cta"
        f"?query={make}&max_price={max_price}&auto_make_model={make}"
        f"&srchType=T&purveyor=owner"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[CL] Failed to fetch {city_slug}/{make}: {e}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    listings = soup.select("li.cl-search-result")

    for listing in listings[:20]:  # cap per make/city
        try:
            title_el = listing.select_one("a.cl-app-anchor span.label")
            price_el = listing.select_one(".priceinfo")
            meta_el  = listing.select_one(".meta")

            title = title_el.get_text(strip=True) if title_el else "Unknown"
            price_raw = price_el.get_text(strip=True) if price_el else "$0"
            price = int(price_raw.replace("$", "").replace(",", "")) if price_raw else 0
            meta  = meta_el.get_text(strip=True) if meta_el else ""

            # Craigslist doesn't surface MPG — we flag it as unknown
            results.append({
                "source":    "Craigslist",
                "title":     title,
                "make":      make.title(),
                "price":     price,
                "mileage":   extract_mileage(meta),
                "mpg":       None,          # CL doesn't expose MPG
                "location":  city_slug.replace("losangeles", "Los Angeles")
                                       .replace("newyork", "New York")
                                       .title(),
                "url":       listing.select_one("a.cl-app-anchor")["href"]
                             if listing.select_one("a.cl-app-anchor") else "",
                "scraped_at": datetime.now().isoformat(),
            })
        except Exception as e:
            print(f"[CL] Parse error: {e}")
            continue

    return results


def extract_mileage(meta_text: str) -> int | None:
    """Pull mileage from Craigslist meta string like '2018 · 45,000mi'."""
    import re
    match = re.search(r"([\d,]+)\s*mi", meta_text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None

# ── Cars.com ──────────────────────────────────────────────────────────────────

# Cars.com make slugs (their URL format requires exact strings)
CARS_COM_MAKES = {
    "honda":   "honda",
    "hyundai": "hyundai",
    "ford":    "ford",
    "gm":      "gmc",
    "toyota":  "toyota",
}

def scrape_cars_com(zip_code: str, make: str, max_price: int, min_mpg: int) -> list[dict]:
    """
    Scrape Cars.com used listings for a given make, ZIP, and price cap.
    Cars.com is server-side rendered and embeds JSON-LD structured data,
    making it reliable without fragile CSS selector chains.
    """
    results = []
    make_slug = CARS_COM_MAKES.get(make.lower(), make.lower())
    url = (
        f"https://www.cars.com/shopping/results/"
        f"?makes[]={make_slug}"
        f"&maximum_price={max_price}"
        f"&zip={zip_code}"
        f"&maximum_distance=150"
        f"&stock_type=used"
        f"&sort=best_match_desc"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[CC] Request failed for {make}: {e}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Primary path: JSON-LD structured data ─────────────────────────────────
    # Cars.com embeds ItemList > Car entries with clean structured fields
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
            # Top-level ItemList
            items = []
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                items = [e.get("item", e) for e in data.get("itemListElement", [])]
            elif isinstance(data, list):
                items = data

            for item in items:
                if item.get("@type") != "Car":
                    continue
                price_raw = item.get("offers", {}).get("price", 0)
                mpg_raw   = item.get("fuelEfficiency", "")
                mileage_raw = (
                    item.get("mileageFromOdometer", {}).get("value")
                    if isinstance(item.get("mileageFromOdometer"), dict)
                    else item.get("mileageFromOdometer")
                )
                results.append({
                    "source":    "Cars.com",
                    "title":     item.get("name", "Unknown"),
                    "make":      make.title(),
                    "price":     int(float(price_raw)) if price_raw else 0,
                    "mileage":   int(mileage_raw) if mileage_raw else None,
                    "mpg":       parse_mpg(mpg_raw),
                    "location":  zip_code,
                    "url":       item.get("url", ""),
                    "scraped_at": datetime.now().isoformat(),
                })
        except (json.JSONDecodeError, AttributeError, ValueError):
            continue

    # ── Fallback: HTML listing cards ──────────────────────────────────────────
    # Used if JSON-LD is absent or empty. Cars.com card structure as of 2024.
    if not results:
        cards = soup.select("div.vehicle-card")
        for card in cards[:25]:
            try:
                title_el  = card.select_one(".vehicle-card-main .title")
                price_el  = card.select_one(".primary-price")
                miles_el  = card.select_one(".mileage")
                location_el = card.select_one(".dealer-name, .miles-from")
                link_el   = card.select_one("a.vehicle-card-link")

                title    = title_el.get_text(strip=True)   if title_el    else "Unknown"
                price    = parse_price(price_el.get_text() if price_el    else "0")
                mileage  = extract_mileage(miles_el.get_text() if miles_el else "")
                location = location_el.get_text(strip=True) if location_el else zip_code
                url      = "https://www.cars.com" + link_el["href"] if link_el else ""

                results.append({
                    "source":    "Cars.com",
                    "title":     title,
                    "make":      make.title(),
                    "price":     price,
                    "mileage":   mileage,
                    "mpg":       None,   # not in card view; only in JSON-LD
                    "location":  location,
                    "url":       url,
                    "scraped_at": datetime.now().isoformat(),
                })
            except Exception as e:
                print(f"[CC] Card parse error: {e}")
                continue

    print(f"[CC] {make.title()}: {len(results)} listings found")
    return results


def parse_price(text: str) -> int:
    import re
    match = re.search(r"[\d,]+", text.replace("$", ""))
    return int(match.group().replace(",", "")) if match else 0


def parse_mpg(text: str) -> int | None:
    import re
    match = re.search(r"(\d+)\s*mpg", str(text), re.IGNORECASE)
    return int(match.group(1)) if match else None

# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_scraper(
    city: str,
    zip_code: str,
    max_price: int,
    min_mpg: int,
    makes: list[str],
):
    city_slug = CL_CITIES.get(city.lower(), city.lower().replace(" ", ""))
    all_results = []

    for make in makes:
        print(f"Scraping Craigslist: {make} in {city}...")
        cl_results = scrape_craigslist(city_slug, make, max_price, min_mpg)
        all_results.extend(cl_results)
        time.sleep(random.uniform(1.5, 3.0))  # polite delay

        print(f"Scraping Cars.com: {make} near {zip_code}...")
        cc_results = scrape_cars_com(zip_code, make, max_price, min_mpg)
        all_results.extend(cc_results)
        time.sleep(random.uniform(2.0, 4.0))

    # Filter: price cap, MPG minimum (only where MPG is known)
    filtered = [
        r for r in all_results
        if r["price"] <= max_price and r["price"] > 0
        and (r["mpg"] is None or r["mpg"] >= min_mpg)
    ]

    # Deduplicate by title + price
    seen = set()
    deduped = []
    for r in filtered:
        key = (r["title"].lower(), r["price"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated": datetime.now().isoformat(),
        "params": {
            "city": city,
            "zip_code": zip_code,
            "max_price": max_price,
            "min_mpg": min_mpg,
            "makes": makes,
        },
        "count": len(deduped),
        "listings": deduped,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\n✓ Done. {len(deduped)} listings written to {OUTPUT_PATH}")
    return payload


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Car lead scraper")
    parser.add_argument("--city",      default="los angeles",  help="City name")
    parser.add_argument("--zip",       default="90001",        help="ZIP code for Autotrader radius")
    parser.add_argument("--max-price", default=30000, type=int, help="Max price USD")
    parser.add_argument("--min-mpg",   default=25,   type=int, help="Min MPG (applied where known)")
    parser.add_argument("--makes",     default="honda,toyota,hyundai,ford,gm",
                        help="Comma-separated list of makes")
    args = parser.parse_args()

    run_scraper(
        city=args.city,
        zip_code=args.zip,
        max_price=args.max_price,
        min_mpg=args.min_mpg,
        makes=[m.strip() for m in args.makes.split(",")],
    )
