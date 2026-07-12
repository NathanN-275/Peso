# Security Operations

## GitHub Secret Scanning

Enable these repository settings before merging production deployments:

- `Settings > Code security and analysis > Secret scanning`: enabled.
- `Settings > Code security and analysis > Push protection`: enabled.
- `Settings > Code security and analysis > Dependabot alerts`: enabled.
- `Settings > Code security and analysis > Dependabot security updates`: enabled.

The `Security Checks` GitHub Actions workflow also runs Gitleaks on pushes and pull requests. GitHub push protection should still be enabled because it blocks secrets before they enter history.

## Local Security Checks

Run these before deploying backend security-sensitive changes:

```sh
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/peso-pycache .venv/bin/python -m unittest discover -s tests
npm run typecheck
npm run test:policy
python3 scripts/supabase_security_audit.py
npm audit --audit-level=high
```

Run Python dependency auditing when `pip-audit` is available. The protobuf advisory is currently ignored because `mediapipe==0.10.21` requires `protobuf<5`, while the available advisory fix starts at `5.29.6`; revisit this ignore when MediaPipe publishes a compatible release.

```sh
pip-audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-1805
```

## Dependency Review Checklist

Use this checklist for every Python or Node package update:

- Audit result: run `npm audit --audit-level=high` for Node and `pip-audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-1805` for Python when `pip-audit` is available.
- Lockfile diff: review new packages, removed packages, install scripts, native modules, and transitive dependency changes.
- Runtime risk: identify whether the dependency runs in the Expo client, FastAPI backend request path, build tooling, CI only, or local development only.
- Production exposure: note whether the package handles auth, storage paths, media files, request parsing, subprocess execution, or network calls.
- Advisory handling: document any ignored advisory with the package constraint, affected runtime, exploitability in this app, and revisit trigger.

Current tracked advisory exceptions:

- Python: `PYSEC-2026-1805` for protobuf remains ignored only because `mediapipe==0.10.21` requires `protobuf<5` while the available fix starts at `5.29.6`.
- Node: Expo transitive moderate advisories are not ignored in CI because CI fails only on high severity and above. Revisit them on each Expo SDK update and document any advisory that becomes high severity or ships in production runtime code.

## Request Provenance

See [request-inventory.md](/Users/nathan/Downloads/peso-app/docs/request-inventory.md) for the current frontend-to-backend and frontend-to-Supabase request inventory, HTTP policy, and client/server field boundary.
