# PropertyROI

Find for-sale properties, estimate their **rental potential** from comparable
rental data, rank them by return on investment — and **measure how accurate the
rent estimator is** with a built-in tester.

Pure Python standard library. No dependencies, no API keys, runs offline against
bundled sample data. An optional live provider (RentCast) is included for real
data.

## What it does

1. **Explore for-sale listings** filtered by ZIP, price, beds, and type.
2. **Estimate rent** for each listing from nearby rental comps using a
   transparent, explainable comps model (no black box).
3. **Analyze rental potential** — gross yield, cap rate, cash flow,
   cash-on-cash return, the 1% rule — and produce a single 0–100 ROI score.
4. **Rank deals** best-first so good rentals rise to the top.
5. **Evaluate accuracy** of the rent estimator against labeled ground-truth
   rents (MAE, RMSE, MAPE, R², within-X% hit rates).

## Quick start

### Web GUI (Docker)

```bash
docker compose up --build
# then open http://localhost:8000
```

Or with plain Docker:

```bash
docker build -t propertyroi .
docker run --rm -p 8000:8000 propertyroi
```

The GUI has two tabs: **Find deals** (search + ranked results table, click a row
for a full ROI breakdown) and **Estimator accuracy** (runs the leave-one-out
tester and shows MAE / MAPE / R² plus per-property predictions). It runs on the
bundled sample data out of the box; switch data sources with the dropdown (live
sources need API keys — see below).

**Entering keys in the GUI.** Expand **API keys / sources** under the search form
to enter your RapidAPI key (Zillow/Realtor), RentCast key, and MVBA URL. They're
saved in your browser's `localStorage` (this device only) and sent with each
request as headers (`X-RapidAPI-Key`, `X-RentCast-Key`, `X-MVBA-URL`) — not query
params, so they stay out of server logs. A blank field falls back to the
server's env var. The dev server is plain HTTP, so use it on a trusted network.

### Web GUI (no Docker)

```bash
python -m propertyroi serve --port 8000    # open http://localhost:8000
```

### Make targets

```bash
make up          # docker compose up --build
make serve       # run the GUI locally (PORT=… PROVIDER=…)
make test        # run the test suite
make lint        # ruff check
make accuracy    # run the accuracy tester
make help        # list all targets
```

### Raspberry Pi (auto-updating)

CI publishes a multi-arch image (amd64 + **arm64**) to GHCR on every push to
`main`. On the Pi, run the app plus **Watchtower**, which polls the registry and
auto-pulls new versions:

```bash
# one-time
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
git clone https://github.com/bsoeder/Propertyroi.git && cd Propertyroi

# if the GHCR package is private, log in once (else skip):
#   echo <GITHUB_PAT_with_read:packages> | docker login ghcr.io -u bsoeder --password-stdin

# start the app + auto-updater (detached)
export PROPERTYROI_IMAGE=ghcr.io/bsoeder/propertyroi:latest
docker compose -f docker-compose.pi.yml up -d
```

Then open `http://<pi-ip>:8000`. Watchtower checks every 5 minutes and, when CI
publishes a new `:latest`, pulls it and restarts the container automatically —
no manual redeploy. Manage it with:

```bash
docker compose -f docker-compose.pi.yml logs -f        # watch activity
docker compose -f docker-compose.pi.yml pull           # force an update now
docker compose -f docker-compose.pi.yml down           # stop everything
```

> Prefer building on the Pi instead of pulling? Use a git-based updater: a cron
> job running `git pull && docker compose up -d --build` in the repo achieves
> the same "auto-update" without a registry.

### Command line

```bash
# Rank rental deals in a ZIP (bundled sample data)
python -m propertyroi scan --zip 44107 --limit 5

# Deep-dive a single listing
python -m propertyroi analyze --id L1019

# Measure the rent estimator's accuracy
python -m propertyroi test --verbose
```

Example scan output:

```
score  id       price          size          est. rent          cap      CoC      cash flow
 79.6  L1019   $   157,000  3bd/2ba  1704sf  rent~$ 1,970(conf 0.88)  cap  8.2%  CoC   7.9%  cf $ 289/mo 1%  44107
```

Example accuracy report (bundled data):

```
MAE                   : $191/mo
MAPE                  : 7.7%
R^2                   : 0.927
Within 10%            : 72%
```

## How rent is estimated

For a subject property the estimator:

1. selects rental comps in the same area (coordinates when available, else same
   ZIP) within a bedroom tolerance;
2. weights each comp by similarity (beds, baths, sqft, type, distance) via a
   Gaussian of feature distance;
3. adjusts each comp's rent toward the subject by blending a $/sqft-scaled rent
   with the comp's whole-unit rent, plus a small bedroom nudge;
4. returns a similarity-weighted rent, a low–high band from the weighted spread,
   and a confidence score (more/closer/tighter comps → higher confidence).

See `propertyroi/estimator.py`.

## How ROI is computed

`propertyroi/analyzer.py` turns rent + price into investor metrics using explicit
assumptions (`Assumptions`): down payment, mortgage rate/term, vacancy, operating
expense ratio, taxes, closing costs. It reports gross yield, NOI, cap rate,
monthly/annual cash flow, cash-on-cash return, the 1% rule, and a composite
score. Tune assumptions from the CLI (`--down`, `--rate`) or in code.

## The accuracy tester

`propertyroi/tester.py` runs **leave-one-out** evaluation: each labeled property
is priced using every *other* labeled property as a comp, then predictions are
compared to actual rents. Metrics: MAE, RMSE, MAPE, median APE, R², bias, and
within-5/10/20% hit rates, plus coverage. This lets you quantify quality and
track it as you change the algorithm or plug in real data.

```bash
python -m propertyroi test --data path/to/your_labeled.json --json
```

Labeled data format (`data/eval_labeled.json`): each record is a listing plus an
`actual_rent` field.

## Using real data (Zillow, Realtor.com, RentCast)

> **Note on Zillow & Realtor.com.** Neither offers a free public listings API
> (Zillow retired its public API), and scraping their sites directly violates
> their Terms of Service and is actively blocked. The supported way to get their
> data programmatically is through third-party **RapidAPI** marketplace
> endpoints that mirror them, which require your own API key. PropertyROI does
> **not** scrape — these providers call those APIs.

```bash
# Zillow or Realtor.com via RapidAPI
export RAPIDAPI_KEY=your_rapidapi_key
python -m propertyroi scan --zip 78704 --provider zillow
python -m propertyroi scan --zip 78704 --provider realtor

# Pull from BOTH at once, merged and de-duplicated
python -m propertyroi scan --zip 78704 --provider combined

# RentCast (separate key)
export RENTCAST_API_KEY=your_key
python -m propertyroi scan --zip 78704 --provider rentcast
```

In Docker, select the default data source with `PROPERTYROI_PROVIDER` and pass
the keys through:

```bash
docker run --rm -p 8000:8000 \
  -e PROPERTYROI_PROVIDER=combined \
  -e RAPIDAPI_KEY=your_rapidapi_key \
  propertyroi
```

(`docker-compose.yml` reads these from your shell/`.env` automatically.)

### MVBA tax-sale land

MVBA (McCreary, Veselka, Bragg & Allen) runs Texas delinquent-property **tax
sales** — often raw land — published at `mvbalaw.com/tax-sales/`. That page is a
**county index** linking to per-county **bid sheets** (usually PDFs). The `mvba`
provider adapts to whatever `MVBA_SALES_URL` points at:

- an **index page** → it crawls the county bid-sheet links and parses each one;
- a **bid sheet** → an HTML `<table>`, a JSON feed, or a **PDF** is parsed into
  land listings (columns mapped by fuzzy header name: minimum bid, adjudged
  value, acreage, legal description, county, sale date, account/cause no.).

```bash
export MVBA_SALES_URL="https://mvbalaw.com/tax-sales/"   # index, a sheet, or a feed
python -m propertyroi scan --provider mvba

# Realtor.com residential AND MVBA land in one ranked list:
export RAPIDAPI_KEY=your_rapidapi_key
python -m propertyroi scan --provider realtor,mvba
```

Any comma-separated combo works (`zillow,mvba`, `realtor,mvba`, …) and merges via
`CombinedProvider`, skipping a source that errors.

**PDF bid sheets** need the optional `pdfplumber` dependency
(`pip install "propertyroi[mvba]"` or `pip install pdfplumber`). It's already
included in the Docker image, so the containerized app (and the Pi) parse PDFs
out of the box; HTML/JSON sources work without it.

**Land scoring (side by side).** Raw land has no rent, so rental ROI is
meaningless for it. For land / tax-sale listings the app computes land-specific
metrics — **discount to adjudged value** and **price per acre** — and ranks them
by a `land_score`, while still reporting the rental `rental_score` alongside
(≈0 with no comps). Residential listings continue to rank by rental ROI. Each
row/detail view adapts to the listing type.

Each provider maps its source's sale and rental listings onto the same models,
so the estimator, analyzer, and tester all work unchanged. Any provider
implementing `propertyroi.providers.base.DataProvider` can be swapped in.

### Configuring the RapidAPI hosts

RapidAPI hosts many Zillow/Realtor listings with slightly different response
shapes. The defaults target common ones (`zillow-com1.p.rapidapi.com`,
`us-real-estate.p.rapidapi.com`); override via env vars if you subscribed to a
different listing:

| Variable | Purpose | Default |
|---|---|---|
| `RAPIDAPI_KEY` | Your RapidAPI key (Zillow + Realtor) | — |
| `ZILLOW_RAPIDAPI_HOST` | Zillow host | `zillow-com1.p.rapidapi.com` |
| `REALTOR_RAPIDAPI_HOST` | Realtor host | `us-real-estate.p.rapidapi.com` |
| `REALTOR_SALE_PATH` | Realtor for-sale path | `v2/for-sale` |
| `REALTOR_RENT_PATH` | Realtor for-rent path | `v2/for-rent` |
| `MVBA_SALES_URL` | MVBA/county tax-sale listing page or JSON feed | — |

The Realtor provider parses several common nesting shapes defensively, so minor
schema differences between listings do not break it.

## Programmatic use

```python
from propertyroi import Analyzer, JsonProvider, RentEstimator, Assumptions

analyzer = Analyzer(JsonProvider(), RentEstimator(), Assumptions(down_payment_pct=0.20))
for deal in analyzer.find_deals(zip_code="44107", limit=5):
    print(deal.listing.id, deal.score, deal.cap_rate, deal.monthly_cash_flow)
```

## Project layout

```
propertyroi/
  models.py          # dataclasses: Listing, RentalComp, RentEstimate, InvestmentAnalysis
  estimator.py       # comps-based rent estimation
  analyzer.py        # ROI metrics + deal ranking
  tester.py          # accuracy evaluator (leave-one-out)
  webapp.py          # stdlib web server: GUI + JSON API
  web/index.html     # single-page GUI (no external dependencies)
  cli.py             # `python -m propertyroi` commands: scan / analyze / serve / test
  providers/         # JsonProvider (default), Zillow/Realtor/RentCast/MVBA (live), CombinedProvider
data/                # sample listings, comps, labeled eval set
tests/               # unittest suite (run: python -m unittest discover -s tests)
Dockerfile           # container image (runs `serve`)
docker-compose.yml   # one-command run with env-based config
```

## Web API

The server (`python -m propertyroi serve`, port 8000) exposes:

| Endpoint | Description |
|---|---|
| `GET /` | the single-page GUI |
| `GET /api/health` | liveness + active provider |
| `GET /api/scan` | ranked deals — params: `zip`, `max_price`, `min_beds`, `type`, `limit`, `provider`, `down`, `rate` |
| `GET /api/analyze` | one listing — params: `id`, `provider`, `down`, `rate` |
| `GET /api/test` | accuracy report (JSON) against the labeled data set |

```bash
curl "http://localhost:8000/api/scan?zip=44107&limit=5"
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Disclaimer

Estimates and scores are a transparent model for research and comparison, **not
investment, financial, or appraisal advice**. Always verify with local data and
professionals before making decisions.
