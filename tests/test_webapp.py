import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from propertyroi.webapp import Handler


class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get(self, path, headers=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_health(self):
        status, body = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_index_served(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"PropertyROI", body)

    def test_scan(self):
        status, body = self._get("/api/scan?zip=44107&limit=2")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["count"], 2)
        self.assertIn("metrics", data["deals"][0])
        # Sorted best-first.
        self.assertGreaterEqual(
            data["deals"][0]["metrics"]["score"], data["deals"][1]["metrics"]["score"]
        )

    def test_analyze_found_and_not_found(self):
        # Grab a real id from a scan first.
        _, body = self._get("/api/scan?zip=44107&limit=1")
        lid = json.loads(body)["deals"][0]["listing"]["id"]
        status, body = self._get(f"/api/analyze?id={lid}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["listing"]["id"], lid)

        status, body = self._get("/api/analyze?id=DOES_NOT_EXIST")
        self.assertEqual(status, 404)

    def test_analyze_requires_id(self):
        status, _ = self._get("/api/analyze")
        self.assertEqual(status, 400)

    def test_test_endpoint(self):
        status, body = self._get("/api/test")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertGreater(data["n"], 0)
        self.assertIn("mape", data)
        self.assertIn("predictions", data)

    def test_unknown_route(self):
        status, _ = self._get("/api/nope")
        self.assertEqual(status, 404)

    def test_bad_provider_key_returns_400(self):
        # zillow needs RAPIDAPI_KEY; without it the provider raises ValueError -> 400.
        status, body = self._get("/api/scan?provider=zillow&zip=78704")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))

    def test_json_scan_with_key_headers_still_works(self):
        # Supplying a key header must not break the offline json provider.
        status, body = self._get("/api/scan?zip=44107&limit=1", headers={"X-RapidAPI-Key": "abc"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["count"], 1)


class TestBuildProvider(unittest.TestCase):
    def test_credentials_injected(self):
        from propertyroi.webapp import build_provider
        z = build_provider("zillow", {"rapidapi_key": "abc123"})
        self.assertEqual(z.api_key, "abc123")
        m = build_provider("mvba", {"mvba_url": "https://x/y"})
        self.assertEqual(m.url, "https://x/y")

    def test_comma_list_with_creds(self):
        from propertyroi.providers.combined import CombinedProvider
        from propertyroi.webapp import build_provider
        p = build_provider("zillow,mvba", {"rapidapi_key": "k", "mvba_url": "https://x"})
        self.assertIsInstance(p, CombinedProvider)
        self.assertEqual(len(p.providers), 2)

    def test_blank_creds_use_env_path(self):
        from propertyroi.providers import JsonProvider
        from propertyroi.webapp import build_provider
        self.assertIsInstance(build_provider("json", {}), JsonProvider)

    def test_missing_key_still_errors(self):
        import os

        from propertyroi.webapp import build_provider
        old = os.environ.pop("RAPIDAPI_KEY", None)
        try:
            with self.assertRaises((ValueError, SystemExit)):
                build_provider("zillow", {})
        finally:
            if old is not None:
                os.environ["RAPIDAPI_KEY"] = old


if __name__ == "__main__":
    unittest.main()
