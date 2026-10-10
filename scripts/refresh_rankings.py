#!/usr/bin/env python3
"""Rebuild data/zip_market_stats.csv from current free national data.

Home values come from Zillow's free **ZHVI by ZIP** research CSV; rents come from
HUD **Fair Market Rents** (free API, per ZIP) or a rents CSV you supply. The
result drives the "Top ROI ZIPs" rankings and metro search.

Both sources are free:
  * Zillow ZHVI by ZIP (download the "ZIP Code" CSV, Home Values):
      https://www.zillow.com/research/data/
  * HUD Fair Market Rents API (free token):
      https://www.huduser.gov/portal/dataset/fmr-api.html

Examples
--------
    # Rents from HUD (needs a free HUD_API_TOKEN); slower (one call per ZIP).
    python scripts/refresh_rankings.py --zhvi Zip_zhvi.csv --hud-token $HUD_API_TOKEN \
        --limit-zips 2000 --out data/zip_market_stats.csv

    # Rents from a CSV you already have (columns: zip, rent).
    python scripts/refresh_rankings.py --zhvi Zip_zhvi.csv --rents rents.csv

Run this on a machine with internet (e.g. your Pi), not in a restricted sandbox.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.request


def latest_value_column(header):
    """ZHVI columns end with dated value columns like '2026-09-30'; return the last."""
    dated = [c for c in header if len(c) >= 7 and c[:4].isdigit() and "-" in c]
    return dated[-1] if dated else None


def read_zhvi(path):
    """Yield dict(zip, city, state, metro, price) from a Zillow ZHVI ZIP CSV."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        valcol = latest_value_column(reader.fieldnames or [])
        if not valcol:
            sys.exit("Could not find a dated value column in the ZHVI CSV.")
        for r in reader:
            price = r.get(valcol)
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            yield {
                "zip": str(r.get("RegionName") or "").zfill(5),
                "city": r.get("City", ""),
                "state": r.get("State", ""),
                "metro": r.get("Metro") or r.get("CountyName") or "",
                "price": price,
            }


def rents_from_csv(path):
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            z = str(r.get("zip") or r.get("zip_code") or "").zfill(5)
            try:
                out[z] = float(str(r.get("rent") or r.get("median_rent")).replace(",", ""))
            except (TypeError, ValueError):
                continue
    return out


def hud_rent(zip_code, token, timeout=20):
    url = f"https://www.huduser.gov/hudapi/public/fmr/data/{zip_code}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    bd = (data.get("data") or {}).get("basicdata")
    if isinstance(bd, list):
        bd = bd[0] if bd else {}
    if not isinstance(bd, dict):
        return None
    for key in ("Two-Bedroom", "Three-Bedroom", "One-Bedroom"):
        v = bd.get(key)
        if v:
            try:
                return float(str(v).replace(",", ""))
            except ValueError:
                pass
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zhvi", required=True, help="Zillow ZHVI by-ZIP CSV path")
    ap.add_argument("--rents", help="rents CSV (columns: zip, rent) — alternative to HUD")
    ap.add_argument("--hud-token", default=os.environ.get("HUD_API_TOKEN"), help="HUD API token for rents")
    ap.add_argument("--out", default="data/zip_market_stats.csv")
    ap.add_argument("--limit-zips", type=int, help="cap ZIPs processed (HUD is one call each)")
    args = ap.parse_args(argv)

    if not args.rents and not args.hud_token:
        ap.error("provide --rents CSV or --hud-token for rent data")

    rents = rents_from_csv(args.rents) if args.rents else {}
    rows, n = [], 0
    for z in read_zhvi(args.zhvi):
        if args.limit_zips and n >= args.limit_zips:
            break
        rent = rents.get(z["zip"])
        if rent is None and args.hud_token:
            try:
                rent = hud_rent(z["zip"], args.hud_token)
            except Exception:
                rent = None
        if not rent:
            continue
        rows.append([z["zip"], z["city"], z["state"], z["metro"],
                     int(z["price"]), int(rent), "live"])
        n += 1

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zip", "city", "state", "metro", "median_price", "median_rent", "as_of"])
        w.writerows(rows)
    print(f"wrote {len(rows)} ZIPs to {args.out}")


if __name__ == "__main__":
    main()
