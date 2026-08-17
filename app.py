"""
app.py — Car Leads Dashboard
Reads data/results.json committed by GitHub Actions.
Refresh Now button fires a repository_dispatch to trigger a new scrape.
"""

import json
import os
import time
import requests
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Car Leads",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject custom CSS ─────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* Dashboard header */
  .dash-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 0 0 6px 0;
    border-bottom: 2px solid #18181b;
    margin-bottom: 24px;
  }
  .dash-header h1 {
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #18181b;
    margin: 0;
  }
  .dash-header .subtitle {
    font-size: 0.85rem;
    color: #71717a;
    font-weight: 400;
  }

  /* Stat pills */
  .stat-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
  .stat-pill {
    background: #f4f4f5;
    border-radius: 8px;
    padding: 10px 18px;
    min-width: 110px;
  }
  .stat-pill .label { font-size: 0.7rem; color: #71717a; text-transform: uppercase; letter-spacing: 0.07em; }
  .stat-pill .value { font-size: 1.4rem; font-weight: 700; color: #18181b; line-height: 1.1; }

  /* Source badge */
  .badge-cl { background:#e0f2fe; color:#0369a1; border-radius:4px; padding:2px 7px; font-size:0.72rem; font-weight:600; }
  .badge-at { background:#fef3c7; color:#92400e; border-radius:4px; padding:2px 7px; font-size:0.72rem; font-weight:600; }

  /* Dataframe tweak */
  [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

  /* Sidebar */
  section[data-testid="stSidebar"] { background: #fafafa; border-right: 1px solid #e4e4e7; }
  section[data-testid="stSidebar"] .stSelectbox label,
  section[data-testid="stSidebar"] .stSlider label { font-size: 0.82rem; font-weight: 600; color: #3f3f46; }

  /* Refresh button */
  div[data-testid="stButton"] button {
    background: #18181b;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    font-size: 0.85rem;
    padding: 0.45rem 1.2rem;
    transition: background 0.15s;
  }
  div[data-testid="stButton"] button:hover { background: #3f3f46; }

  .timestamp { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #71717a; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

DATA_PATH    = Path("data/results.json")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")          # set in Streamlit secrets
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "owner/repo") # e.g. "albertlisa/car-leads"

MAKE_OPTIONS  = ["All", "Honda", "Toyota", "Hyundai", "Ford", "GMC"]
PRICE_MAX     = 60_000
MPG_MIN_FLOOR = 15

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)  # re-reads from disk every 60s automatically
def load_data() -> dict:
    if not DATA_PATH.exists():
        return {"listings": [], "last_updated": None, "params": {}, "count": 0}
    with open(DATA_PATH) as f:
        return json.load(f)


def listings_to_df(listings: list) -> pd.DataFrame:
    if not listings:
        return pd.DataFrame()
    df = pd.DataFrame(listings)
    # Friendly display columns
    df["Price"]    = df["price"].apply(lambda x: f"${x:,}" if x else "—")
    df["Mileage"]  = df["mileage"].apply(lambda x: f"{x:,} mi" if x else "—")
    df["MPG"]      = df["mpg"].apply(lambda x: f"{x} mpg" if x else "—")
    df["Source"]   = df["source"]
    df["Make"]     = df["make"]
    df["Title"]    = df["title"]
    df["Location"] = df["location"]
    df["Link"]     = df["url"].apply(lambda u: f"[View →]({u})" if u else "—")
    return df[["Source", "Make", "Title", "Price", "Mileage", "MPG", "Location", "Link"]]

# ── GitHub Actions dispatch (Refresh Now) ────────────────────────────────────

def trigger_refresh(city: str, zip_code: str, max_price: int, min_mpg: int, makes: list[str]) -> bool:
    if not GITHUB_TOKEN or GITHUB_REPO == "owner/repo":
        st.warning("Set GITHUB_TOKEN and GITHUB_REPO in Streamlit secrets to enable on-demand refresh.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    payload = {
        "event_type": "refresh",
        "client_payload": {
            "city":      city,
            "zip_code":  zip_code,
            "max_price": str(max_price),
            "min_mpg":   str(min_mpg),
            "makes":     ",".join([m.lower() for m in makes]),
        },
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json=payload,
        timeout=8,
    )
    return resp.status_code == 204

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🔍 Search Parameters")
    st.caption("These filters apply to the current results. To run a new scrape with new parameters, click **Refresh Now**.")

    selected_makes = st.multiselect(
        "Makes",
        options=["Honda", "Toyota", "Hyundai", "Ford", "GMC"],
        default=["Honda", "Toyota", "Hyundai", "Ford", "GMC"],
    )

    max_price_filter = st.slider(
        "Max Price",
        min_value=5_000,
        max_value=30_000,
        value=30_000,
        step=500,
        format="$%d",
    )

    min_mpg_filter = st.slider(
        "Min MPG (known listings only)",
        min_value=MPG_MIN_FLOOR,
        max_value=50,
        value=MPG_MIN_FLOOR,
        step=1,
    )

    show_unknown_mpg = st.checkbox("Include listings with unknown MPG", value=True)

    st.divider()
    st.markdown("### 🔄 On-Demand Refresh")
    st.caption("Triggers a new GitHub Actions scrape. Results appear in ~2–3 minutes after the workflow completes.")

    scrape_city    = st.text_input("City",     value="los angeles")
    scrape_zip     = st.text_input("ZIP Code", value="90001")
    scrape_price   = st.number_input("Price Cap", value=30000, step=1000)
    scrape_mpg     = st.number_input("Min MPG",   value=25,    step=1)
    scrape_makes   = st.multiselect(
        "Makes to scrape",
        options=["honda", "toyota", "hyundai", "ford", "gm"],
        default=["honda", "toyota", "hyundai", "ford", "gm"],
    )

    refresh_clicked = st.button("🔄 Refresh Now", use_container_width=True)

# ── Main area ─────────────────────────────────────────────────────────────────

st.markdown("""
<div class="dash-header">
  <h1>🚗 Car Leads</h1>
  <span class="subtitle">Daily scrape · Craigslist + Cars.com · Under $30k</span>
</div>
""", unsafe_allow_html=True)

# Handle refresh trigger
if refresh_clicked:
    with st.spinner("Dispatching scrape job to GitHub Actions..."):
        success = trigger_refresh(
            city=scrape_city,
            zip_code=scrape_zip,
            max_price=int(scrape_price),
            min_mpg=int(scrape_mpg),
            makes=scrape_makes,
        )
    if success:
        st.success("✓ Scrape job triggered. Results will update in 2–3 minutes. Reload this page after the workflow finishes.")
    else:
        st.error("Failed to trigger scrape. Check GITHUB_TOKEN and GITHUB_REPO in your Streamlit secrets.")

# Load data
data = load_data()
listings = data.get("listings", [])
last_updated = data.get("last_updated")
params = data.get("params", {})

# Stat pills
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Leads", data.get("count", 0))
with col2:
    cl_count = sum(1 for l in listings if l.get("source") == "Craigslist")
    st.metric("Craigslist", cl_count)
with col3:
    at_count = sum(1 for l in listings if l.get("source") == "Cars.com")
    st.metric("Cars.com", at_count)
with col4:
    if last_updated:
        dt = datetime.fromisoformat(last_updated)
        st.metric("Last Updated", dt.strftime("%-I:%M %p"))
    else:
        st.metric("Last Updated", "Never")

if last_updated:
    st.markdown(f'<span class="timestamp">Last scraped: {last_updated}</span>', unsafe_allow_html=True)

st.divider()

# Apply filters
filtered = listings
if selected_makes:
    filtered = [l for l in filtered if l.get("make", "").title() in selected_makes]
filtered = [l for l in filtered if l.get("price", 0) <= max_price_filter]
if not show_unknown_mpg:
    filtered = [l for l in filtered if l.get("mpg") is not None]
filtered = [l for l in filtered if l.get("mpg") is None or l.get("mpg", 0) >= min_mpg_filter]

if not filtered:
    st.info("No listings match your current filters. Try broadening your search or running a new scrape.")
else:
    df = listings_to_df(filtered)
    st.markdown(f"**{len(filtered)} listings** match your filters")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="View →"),
            "Price": st.column_config.TextColumn("Price"),
        },
    )

    # Price distribution chart
    st.markdown("#### Price Distribution")
    price_df = pd.DataFrame({"Price": [l["price"] for l in filtered if l.get("price")]})
    st.bar_chart(price_df["Price"].value_counts(bins=10).sort_index())
