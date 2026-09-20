"""Web GUI + JSON API for PropertyROI.

A dependency-free web server (Python standard library only) that serves a
single-page GUI and a small JSON API backed by the same analyzer, estimator, and
accuracy tester used by the CLI. This is what runs inside the Docker image.

Endpoints
---------
GET /                       -> the single-page GUI
GET /api/health            -> {"status": "ok", ...}
GET /api/scan              -> ranked deals   (params: zip, max_price, min_beds,
                              type, limit, provider, down, rate)
GET /api/analyze           -> one listing    (params: id, provider, down, rate)
GET /api/test              -> accuracy report (params: provider [json only])

The default data provider is the bundled sample JSON, so the app runs with zero
configuration. Set PROPERTYROI_PROVIDER (and the relevant API keys) to use live
data.
"""

from __future__ import annotations

import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .analyzer import Analyzer, Assumptions
from .estimator import RentEstimator
from .tester import AccuracyTester, load_labeled

_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_DEFAULT_PROVIDER = os.environ.get("PROPERTYROI_PROVIDER", "json")


def _make_provider(name: str):
    # Imported here (not top-level) so a missing API key never breaks startup.
    from .cli import _make_provider as make

    return make(name)


def _assumptions(down: Optional[str], rate: Optional[str]) -> Assumptions:
    a = Assumptions()
    if down:
        a.down_payment_pct = float(down)
    if rate:
        a.mortgage_rate = float(rate)
    return a


def _first(qs: dict, key: str) -> Optional[str]:
    v = qs.get(key)
    return v[0] if v else None


class Handler(BaseHTTPRequestHandler):
    server_version = "PropertyROI/0.1"

    # -- helpers -----------------------------------------------------------
    def _send_json(self, obj, status: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, content_type: str):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter, single-line logs
        print(f"[web] {self.address_string()} {fmt % args}")

    # -- routing -----------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if route == "/" or route == "/index.html":
                return self._send_file(os.path.join(_WEB_DIR, "index.html"), "text/html; charset=utf-8")
            if route == "/api/health":
                return self._send_json({"status": "ok", "provider": _DEFAULT_PROVIDER})
            if route == "/api/scan":
                return self._api_scan(qs)
            if route == "/api/analyze":
                return self._api_analyze(qs)
            if route == "/api/test":
                return self._api_test(qs)
            return self._send_json({"error": f"unknown route {route}"}, 404)
        except ValueError as e:
            # e.g. missing API key or bad numeric param
            self._send_json({"error": str(e)}, 400)
        except Exception as e:  # pragma: no cover - defensive
            traceback.print_exc()
            self._send_json({"error": f"internal error: {e}"}, 500)

    # -- API handlers ------------------------------------------------------
    def _api_scan(self, qs):
        provider = _first(qs, "provider") or _DEFAULT_PROVIDER
        analyzer = Analyzer(
            _make_provider(provider),
            RentEstimator(),
            _assumptions(_first(qs, "down"), _first(qs, "rate")),
        )
        limit = _first(qs, "limit")
        max_price = _first(qs, "max_price")
        min_beds = _first(qs, "min_beds")
        deals = analyzer.find_deals(
            zip_code=_first(qs, "zip"),
            max_price=float(max_price) if max_price else None,
            min_beds=int(min_beds) if min_beds else None,
            property_type=_first(qs, "type"),
            limit=int(limit) if limit else None,
        )
        self._send_json({"count": len(deals), "deals": [d.to_dict() for d in deals]})

    def _api_analyze(self, qs):
        listing_id = _first(qs, "id")
        if not listing_id:
            return self._send_json({"error": "id is required"}, 400)
        provider = _first(qs, "provider") or _DEFAULT_PROVIDER
        p = _make_provider(provider)
        analyzer = Analyzer(p, RentEstimator(), _assumptions(_first(qs, "down"), _first(qs, "rate")))
        match = next((l for l in p.search_listings(zip_code=_first(qs, "zip")) if l.id == listing_id), None)
        if match is None:
            match = next((l for l in p.search_listings() if l.id == listing_id), None)
        if match is None:
            return self._send_json({"error": f"listing {listing_id} not found"}, 404)
        self._send_json(analyzer.analyze(match).to_dict())

    def _api_test(self, qs):
        # Accuracy testing runs against the labeled data set (ships with the app).
        data_path = os.path.join(_DATA_DIR, "eval_labeled.json")
        report = AccuracyTester(RentEstimator()).evaluate(load_labeled(data_path))
        self._send_json(report.to_dict(include_predictions=True))


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"PropertyROI GUI on http://{host}:{port}  (provider: {_DEFAULT_PROVIDER})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


if __name__ == "__main__":
    serve(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )
