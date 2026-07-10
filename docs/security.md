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
