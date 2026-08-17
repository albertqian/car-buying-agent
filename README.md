# Car Leads Dashboard

Daily car listing scraper (Craigslist + Autotrader) with a Streamlit frontend.
Built as a GitHub Actions + Streamlit workshop demo.

## Architecture

```
GitHub Actions (cron 9AM Pacific / on-demand dispatch)
    └── scraper.py
            ├── Craigslist (city-based search)
            └── Cars.com (zip+radius, server-side rendered, JSON-LD structured data)
            └── data/results.json  ← committed back to repo

Streamlit (app.py)
    ├── Reads data/results.json from disk
    ├── Sidebar filters (make, price, MPG)
    └── "Refresh Now" → POST /repos/{owner}/{repo}/dispatches
```

## Setup

### 1. Fork / clone this repo

```bash
git clone https://github.com/YOUR_USERNAME/car-leads
cd car-leads
```

### 2. Create `data/` directory and placeholder

```bash
mkdir -p data
echo '{"listings":[],"last_updated":null,"params":{},"count":0}' > data/results.json
git add data/results.json
git commit -m "init: add placeholder results"
git push
```

### 3. GitHub Actions permissions

In your repo: **Settings → Actions → General → Workflow permissions**
→ Set to **"Read and write permissions"** (so the workflow can commit `results.json`)

### 4. Optional: set default location as repo secret

**Settings → Secrets → Actions → New repository secret**

| Secret name      | Example value   |
|------------------|-----------------|
| `DEFAULT_CITY`   | `los angeles`   |
| `DEFAULT_ZIP`    | `90001`         |

### 5. Deploy Streamlit

**Option A — Streamlit Community Cloud (free)**
1. Push repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app → pick this repo → `app.py`
3. Add secrets under **App Settings → Secrets**:

```toml
GITHUB_TOKEN = "ghp_your_fine_grained_pat_here"
GITHUB_REPO  = "your-username/car-leads"
```

**Option B — run locally**
```bash
pip install -r requirements.txt
GITHUB_TOKEN=ghp_xxx GITHUB_REPO=you/car-leads streamlit run app.py
```

### 6. Create a GitHub Fine-Grained PAT

The Streamlit app needs a token to trigger `repository_dispatch`.

1. GitHub → **Settings → Developer Settings → Fine-grained tokens → Generate new token**
2. Permissions: **Actions: Read and Write**, **Contents: Read and Write**
3. Copy and paste into Streamlit secrets as `GITHUB_TOKEN`

---

## Running the scraper manually

```bash
python scraper.py \
  --city "los angeles" \
  --zip 90001 \
  --max-price 30000 \
  --min-mpg 25 \
  --makes honda,toyota,hyundai,ford,gm
```

---

## Known limitations (important for the workshop)

| Issue | Detail |
|---|---|
| **Craigslist rate-limits** | Don't run more than once every ~10 min or you'll get soft-blocked. |
| **MPG not on CL** | Craigslist doesn't surface MPG in search results. Listings show `—` for MPG. |
| **Cars.com JSON-LD may vary** | If Cars.com changes their structured data schema, the HTML card fallback kicks in (MPG will show `—` in that path). |
| **Production upgrade** | Swap scraper.py for the Edmunds API (requires approval) or a paid aggregator like SerpApi for guaranteed structured data. |

---

## Cron schedule

The workflow runs at **9:00 AM Pacific Time** (`0 16 * * *` UTC).

To change: edit `cron` in `.github/workflows/car_leads.yml`.

---

## Workshop discussion points

1. Why GitHub Actions vs. a dedicated cron service (Railway, Render)?
2. Scraping ethics and ToS — when to use an API vs. scrape
3. `results.json` in-repo as a poor-man's database — trade-offs vs. Supabase/SQLite
4. On-demand dispatch pattern: `repository_dispatch` as a lightweight webhook
5. Production upgrade path: Playwright for JS-rendered pages, Edmunds API, deduplication across runs
