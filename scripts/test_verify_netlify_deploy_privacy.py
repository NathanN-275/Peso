from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from io import BytesIO, StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import BaseHandler, ProxyHandler, build_opener
from urllib.response import addinfourl

from verify_netlify_deploy_privacy import NoRedirect, main


APP = "https://0123456789abcdef01234567--peso-webapp.netlify.app"
PREVIEW = "https://abcdef0123456789abcdef01--peso-public-beta.netlify.app"
APP_ASSET = "/app/_expo/static/js/web/index-app123.js"
PREVIEW_ASSET = "/app/fonts/font-preview456.woff2"


def inventory(origin=APP, asset=APP_ASSET):
    return {"deploys": [{"origin": origin, "routes": ["/", "/app/"], "assets": [asset]}]}


class UnreadBody(BytesIO):
    def read(self, *args):
        raise AssertionError("Privacy verifier must not read bodies.")


class FixtureHttps(BaseHandler):
    def __init__(self, statuses):
        self.statuses = statuses
        self.requests = []

    def default_open(self, request):
        self.requests.append(request)
        status = self.statuses[request.full_url]
        if status is None:
            raise URLError("internal transport detail")
        headers = Message()
        if status == 302:
            headers["Location"] = "https://example.invalid/private-redirect"
        response = addinfourl(UnreadBody(b"private response content"), headers, request.full_url, status)
        response.msg = "fixture response"
        return response


class NetlifyDeployPrivacyTests(unittest.TestCase):
    def run_inventory(self, value, statuses):
        fixture = FixtureHttps(statuses)
        opener = build_opener(ProxyHandler({}), NoRedirect(), fixture)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            raw_inventory = value if isinstance(value, str) else json.dumps(value)
            path.write_text(raw_inventory, encoding="utf-8")
            stdout, stderr = StringIO(), StringIO()
            with (patch("verify_netlify_deploy_privacy.build_opener", return_value=opener) as build,
                  redirect_stdout(stdout), redirect_stderr(stderr)):
                status = main([str(path)])
        if status == 2:
            build.assert_not_called()
        else:
            build.assert_called_once()
            self.assertEqual(build.call_args.args[0].proxies, {})
            self.assertIsInstance(build.call_args.args[1], NoRedirect)
        return status, stdout.getvalue(), stderr.getvalue(), fixture.requests

    def test_requires_direct_401_for_each_deploys_own_routes_and_exact_asset(self):
        value = inventory()
        value["deploys"].append({"origin": PREVIEW, "routes": ["/", "/app/login"], "assets": [PREVIEW_ASSET]})
        urls = [APP + "/", APP + "/app/", APP + APP_ASSET,
                PREVIEW + "/", PREVIEW + "/app/login", PREVIEW + PREVIEW_ASSET]
        status, stdout, stderr, requests = self.run_inventory(value, dict.fromkeys(urls, 401))
        self.assertEqual((status, stderr), (0, ""))
        result = json.loads(stdout)
        self.assertTrue(result["passed"])
        self.assertEqual(result["planned_checks"], len(urls))
        self.assertEqual(result["results"], [{"url": url, "status": 401} for url in urls])
        self.assertEqual([request.full_url for request in requests], urls)
        for request in requests:
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            for header in ("Authorization", "Cookie", "Proxy-authorization"):
                self.assertFalse(request.has_header(header))

    def test_stops_at_first_leak_missing_redirect_unexpected_status_or_transport_error(self):
        for failure in (200, 404, 302, 403, 500, None):
            with self.subTest(failure=failure):
                value = inventory()
                value["deploys"][0]["assets"].append("/app/never-probed.js")
                statuses = {APP + "/": 401, APP + "/app/": 401, APP + APP_ASSET: failure}
                status, stdout, stderr, requests = self.run_inventory(value, statuses)
                self.assertEqual((status, stderr), (1, ""))
                self.assertEqual([request.full_url for request in requests], list(statuses))
                result = json.loads(stdout)
                self.assertFalse(result["passed"])
                self.assertEqual(result["planned_checks"], 4)
                self.assertEqual(result["results"][-1], {"url": APP + APP_ASSET, "status": failure})
                for detail in ("private response content", "private-redirect", "internal transport detail"):
                    self.assertNotIn(detail, stdout)

    def test_duplicate_routes_field_blocks_all_requests(self):
        value = json.dumps(inventory()).replace('"routes": ["/", "/app/"]',
                                                '"routes": ["/", "/app/"], "routes": ["/"]')
        code, stdout, stderr, requests = self.run_inventory(value, {})
        self.assertEqual((code, stdout, requests), (2, "", []))
        self.assertIn("No requests were sent.", stderr)

    def test_invalid_inventory_anywhere_blocks_all_requests(self):
        for entry in (
            {"origin": APP.replace("https:", "http:"), "routes": ["/"], "assets": [APP_ASSET]},
            {"origin": "https://peso-webapp.netlify.app", "routes": ["/"], "assets": [APP_ASSET]},
            {"origin": APP + ".example.invalid", "routes": ["/"], "assets": [APP_ASSET]},
            {"origin": PREVIEW, "routes": ["/"], "assets": []},
            {"origin": PREVIEW, "routes": ["/"], "assets": ["//example.invalid/a.js"]},
            {"origin": PREVIEW, "routes": ["/"], "assets": ["/app/../a.js"]},
            {"origin": PREVIEW, "routes": ["/"], "assets": ["/app/build.js?token=private"]},
            {"origin": PREVIEW, "routes": ["/"], "assets": ["/app/build.js#fragment"]},
        ):
            with self.subTest(entry=entry):
                value = inventory()
                value["deploys"].append(entry)
                status, stdout, stderr, requests = self.run_inventory(value, {})
                self.assertEqual((status, stdout, requests), (2, "", []))
                self.assertEqual(stderr, "Invalid Netlify privacy inventory. No requests were sent.\n")


if __name__ == "__main__":
    unittest.main()
