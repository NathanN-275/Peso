"""Verify anonymous denial on an explicit inventory of historical Netlify deploys."""

import argparse
from datetime import datetime, timezone
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


DEPLOY_ORIGIN = re.compile(
    r"https://[0-9a-f]{24}--(?:peso-webapp|peso-marketing|peso-public-beta|peso-staging-web)\.netlify\.app"
)
EXACT_PATH = re.compile(r"/[A-Za-z0-9._~@+/-]*")
EXPECTED_STATUS = 401


def unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Inventory contains duplicate fields.")
    return fields


def inventory_urls(inventory):
    if not isinstance(inventory, dict) or set(inventory) != {"deploys"}:
        raise ValueError("Expected a deploys inventory.")
    deploys = inventory["deploys"]
    if not isinstance(deploys, list) or not deploys:
        raise ValueError("The inventory must contain at least one deploy.")

    origins = set()
    urls = []
    for deploy in deploys:
        if not isinstance(deploy, dict) or set(deploy) != {"origin", "routes", "assets"}:
            raise ValueError("Each deploy requires an origin, routes, and assets.")
        origin = deploy["origin"]
        if not isinstance(origin, str) or not DEPLOY_ORIGIN.fullmatch(origin) or origin in origins:
            raise ValueError("Deploy origins must be distinct Peso HTTPS permalinks.")
        origins.add(origin)

        routes, assets = deploy["routes"], deploy["assets"]
        if not isinstance(routes, list) or not isinstance(assets, list) or not routes or not assets:
            raise ValueError("Each deploy requires nonempty routes and assets lists.")
        paths = routes + assets
        for path in paths:
            if (not isinstance(path, str) or not EXACT_PATH.fullmatch(path)
                    or "//" in path or {".", ".."}.intersection(path.split("/"))):
                raise ValueError("Use exact root-relative paths without query, fragment, or path rewriting.")
        if any(path.endswith("/") for path in assets) or len(set(paths)) != len(paths):
            raise ValueError("Use distinct paths and name each exact asset file.")
        urls.extend(origin + path for path in paths)
    return urls


class NoRedirect(HTTPRedirectHandler):
    def http_error_302(self, request, response, code, message, headers):
        raise HTTPError(request.full_url, code, message, headers, response)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def fetch_status(opener, url):
    try:
        with opener.open(Request(url, method="GET"), timeout=10) as response:
            return response.status
    except HTTPError as error:
        with error:
            return error.code
    except (OSError, HTTPException):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path, help="Reviewed JSON inventory of protected deploy routes and assets")
    args = parser.parse_args(argv)
    try:
        urls = inventory_urls(json.loads(args.inventory.read_text(encoding="utf-8"), object_pairs_hook=unique_fields))
    except (OSError, ValueError, RecursionError):
        print("Invalid Netlify privacy inventory. No requests were sent.", file=sys.stderr)
        return 2

    opener = build_opener(ProxyHandler({}), NoRedirect())
    checked_at = datetime.now(timezone.utc).isoformat()
    results = []
    for url in urls:
        status = fetch_status(opener, url)
        results.append({"url": url, "status": status})
        if status != EXPECTED_STATUS:
            break
    passed = len(results) == len(urls) and results[-1]["status"] == EXPECTED_STATUS
    print(json.dumps({"checked_at_utc": checked_at, "expected_status": EXPECTED_STATUS,
                      "planned_checks": len(urls), "passed": passed, "results": results}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
