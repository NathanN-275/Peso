# Public beta security checkpoint — September 22, 2026

Candidate: `d820b4bf7a272d2d3adbfaabf1c900f8f1343489`, compared with
`4572479745a85abca43e75c9f16fb17418d52bdf`. This is incomplete release evidence,
not security acceptance or permission to launch.

## Completed checks

- `gitleaks git --redact --log-opts=<base>..<candidate>` scanned all four candidate
  commits (~78 KB); no leaks found. This does not verify historical credential
  rotation or remote retained-object removal.
- `npm run audit:ci` passed its existing high/critical policy. It retained the
  recorded exceptions for brace-expansion 1.1.16 and image-size 1.2.1. The result
  is not a zero-vulnerability claim or fresh approval of those exceptions.
- `python3 scripts/supabase_security_audit.py` passed.
- Direct pinned backend dependency check with `pip_audit --no-deps --disable-pip`
  found no known vulnerabilities among 13 pins. This intentionally excludes
  transitive resolution and does not replace the full Linux deployment audit.

## Incomplete checks and recovery evidence

The normal `pip_audit -r backend/requirements.txt` failed resolving
`mediapipe==0.10.30` on this Mac. Preserve that failure and run the complete audit
on the Linux deployment platform. Docker Desktop status returned unavailable;
local startup is being attempted. No hosted service was resumed.

Codex Security scan `8e9bd9f9-fe7b-412e-a9ae-1f0c5152b19a` passed all three
capability checks and retained a source-backed architecture/threat-model draft.
Its inventory MCP failed twice reading the committed budget-admission blob.
The same inventory helper succeeded in the terminal. Investigation found the
helper uses `git cat-file --batch -Z`: system Apple Git 2.39.5 rejects that option,
while shell Git 2.51.0 and bundled Git 2.53.0 support it. The MCP process PATH has
not been verified, so the version mismatch remains a hypothesis, not a confirmed
root cause. Resume the same scan after recovery; do not create a replacement or
report an empty findings array as completed review. No changed-file discovery
or vulnerability validation has completed.

Architecture review confirmed that the historical `render-beta.yaml` selects
Student/staging while Nathan selected PesoDatabase. Do not apply that historical
blueprint unchanged. Actual-spend delivery, geographic data refresh, hosted Auth
hook activation, incoming proxy trust and reservation-only storage cutover are
independent, still-unverified release gates.

The original PDF is missing from its supplied Downloads path and was not found
in Downloads, Documents or Desktop. Existing recorded requirements support
continued work; the PDF must be restored for the final requirement-by-requirement
completion audit.
