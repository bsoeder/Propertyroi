"""Command-line interface for PropertyROI.

Examples
--------
    # Rank rental deals in a ZIP from the bundled sample data
    python -m propertyroi scan --zip 78704 --max-price 600000 --limit 5

    # Analyze a single listing by id
    python -m propertyroi analyze --id L1004

    # Evaluate the estimator's accuracy against labeled data
    python -m propertyroi test

    # Use live RentCast data (needs RENTCAST_API_KEY)
    python -m propertyroi scan --zip 78704 --provider rentcast

    # Pull live data from Zillow or Realtor.com (needs RAPIDAPI_KEY)
    python -m propertyroi scan --zip 78704 --provider zillow
    python -m propertyroi scan --zip 78704 --provider realtor

    # Pull from Zillow AND Realtor.com at once, merged + de-duplicated
    python -m propertyroi scan --zip 78704 --provider combined
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from .analyzer import Analyzer, Assumptions
from .estimator import RentEstimator
from .providers import JsonProvider
from .tester import AccuracyTester, load_labeled


def _make_provider(name: str):
    if name == "json":
        return JsonProvider()
    if name == "rentcast":
        from .providers.rentcast import RentCastProvider

        return RentCastProvider()
    if name == "zillow":
        from .providers.zillow import ZillowProvider

        return ZillowProvider()
    if name == "realtor":
        from .providers.realtor import RealtorProvider

        return RealtorProvider()
    if name == "combined":
        # Pull from Zillow + Realtor at once (both need RAPIDAPI_KEY).
        from .providers.combined import CombinedProvider
        from .providers.realtor import RealtorProvider
        from .providers.zillow import ZillowProvider

        return CombinedProvider([ZillowProvider(), RealtorProvider()])
    raise SystemExit(f"Unknown provider: {name}")


_PROVIDER_CHOICES = ["json", "rentcast", "zillow", "realtor", "combined"]


def _fmt_analysis_row(a) -> str:
    l = a.listing
    m = a
    flag = "1%" if m.meets_one_percent_rule else "  "
    return (
        f"{a.score:5.1f}  {l.id:<7} ${l.price:>10,.0f}  {l.beds}bd/{l.baths:g}ba "
        f"{l.sqft:>5}sf  rent~${a.rent_estimate.monthly_rent:>6,.0f}"
        f"(conf {a.rent_estimate.confidence:.2f})  "
        f"cap {m.cap_rate:5.1%}  CoC {m.cash_on_cash:6.1%}  "
        f"cf ${m.monthly_cash_flow:>6,.0f}/mo {flag}  {l.location.zip_code}"
    )


def cmd_scan(args) -> int:
    try:
        provider = _make_provider(args.provider)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    analyzer = Analyzer(provider, RentEstimator(), _assumptions_from_args(args))
    deals = analyzer.find_deals(
        zip_code=args.zip,
        max_price=args.max_price,
        min_beds=args.min_beds,
        property_type=args.type,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps([d.to_dict() for d in deals], indent=2))
        return 0
    if not deals:
        print("No listings matched your filters.")
        return 0
    print(f"Found {len(deals)} listing(s), ranked by rental-ROI score:\n")
    print("score  id       price          size          est. rent          cap      CoC      cash flow")
    print("-" * 108)
    for d in deals:
        print(_fmt_analysis_row(d))
    return 0


def cmd_analyze(args) -> int:
    try:
        provider = _make_provider(args.provider)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    analyzer = Analyzer(provider, RentEstimator(), _assumptions_from_args(args))
    listings = provider.search_listings(zip_code=args.zip)
    match = next((l for l in listings if l.id == args.id), None)
    if match is None:
        # broaden search if zip not supplied / not found
        match = next((l for l in provider.search_listings() if l.id == args.id), None)
    if match is None:
        print(f"Listing {args.id} not found.", file=sys.stderr)
        return 1
    analysis = analyzer.analyze(match)
    if args.json:
        print(json.dumps(analysis.to_dict(), indent=2))
        return 0
    l = match
    print(f"Listing {l.id} - {l.address or l.location.zip_code}")
    print(f"  {l.beds}bd / {l.baths:g}ba / {l.sqft:,} sqft  {l.property_type}  built {l.year_built or '?'}")
    print(f"  List price     : ${l.price:,.0f}")
    print()
    re = analysis.rent_estimate
    print(f"  Estimated rent : ${re.monthly_rent:,.0f}/mo  (range ${re.low:,.0f}-${re.high:,.0f}, "
          f"confidence {re.confidence:.0%}, {re.comps_used} comps)")
    print(f"  Gross yield    : {analysis.gross_yield:.2%}")
    print(f"  NOI            : ${analysis.net_operating_income:,.0f}/yr")
    print(f"  Cap rate       : {analysis.cap_rate:.2%}")
    print(f"  Cash invested  : ${analysis.cash_invested:,.0f}")
    print(f"  Cash flow      : ${analysis.monthly_cash_flow:,.0f}/mo  (${analysis.annual_cash_flow:,.0f}/yr)")
    print(f"  Cash-on-cash   : {analysis.cash_on_cash:.2%}")
    print(f"  1% rule        : {'PASS' if analysis.meets_one_percent_rule else 'fail'}")
    print(f"  ROI score      : {analysis.score:.1f}/100")
    return 0


def cmd_test(args) -> int:
    labeled = load_labeled(args.data)
    tester = AccuracyTester(RentEstimator())
    report = tester.evaluate(labeled)
    if args.json:
        print(json.dumps(report.to_dict(include_predictions=args.verbose), indent=2))
        return 0
    print(report.summary())
    if args.verbose:
        print("\nPer-property predictions:")
        print(f"{'id':<8}{'actual':>9}{'pred':>9}{'err':>9}{'ape':>8}{'conf':>7}")
        for p in report.predictions:
            print(f"{p.id:<8}{p.actual:>9,.0f}{p.predicted:>9,.0f}{p.error:>9,.0f}"
                  f"{p.pct_error:>8.1%}{p.confidence:>7.2f}")
    return 0


def _assumptions_from_args(args) -> Assumptions:
    a = Assumptions()
    if getattr(args, "down", None) is not None:
        a.down_payment_pct = args.down
    if getattr(args, "rate", None) is not None:
        a.mortgage_rate = args.rate
    return a


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="propertyroi", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--provider", default="json", choices=_PROVIDER_CHOICES,
                        help="data source (default: bundled sample JSON; "
                             "zillow/realtor/combined need RAPIDAPI_KEY)")
        sp.add_argument("--down", type=float, help="down payment fraction, e.g. 0.25")
        sp.add_argument("--rate", type=float, help="mortgage annual rate, e.g. 0.07")
        sp.add_argument("--json", action="store_true", help="output raw JSON")

    sp = sub.add_parser("scan", help="find and rank rental deals")
    add_common(sp)
    sp.add_argument("--zip", help="ZIP code to search")
    sp.add_argument("--max-price", type=float, help="maximum list price")
    sp.add_argument("--min-beds", type=int, help="minimum bedrooms")
    sp.add_argument("--type", help="property type filter")
    sp.add_argument("--limit", type=int, help="max results")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("analyze", help="analyze a single listing by id")
    add_common(sp)
    sp.add_argument("--id", required=True, help="listing id")
    sp.add_argument("--zip", help="ZIP code hint")
    sp.set_defaults(func=cmd_analyze)

    sp = sub.add_parser("test", help="evaluate estimator accuracy on labeled data")
    sp.add_argument("--data", default=None, help="path to labeled JSON")
    sp.add_argument("--json", action="store_true", help="output raw JSON")
    sp.add_argument("--verbose", action="store_true", help="show per-property predictions")
    sp.set_defaults(func=cmd_test)
    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "test" and args.data is None:
        import os
        args.data = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "eval_labeled.json"
        )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
