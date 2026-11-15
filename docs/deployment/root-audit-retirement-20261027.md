# Root dependency audit treatment retirement — 2026-10-27

The root audit rejects every HIGH or CRITICAL finding. Its audit threshold
remains HIGH, and all valid lower findings remain in the raw report and decision
metadata. No advisory, package path, installed backport, caller assertion or date
can enable a HIGH exception.

The old temporary treatment expired on 2026-10-12T23:59:59Z and was never renewed.
Official Forge 1.4.2 and image-size 2.0.4 replaced their former vulnerable releases;
the reviewed Forge candidate's real registry audit returned 0 HIGH, 0 CRITICAL and
4 moderate. Braces' retained local patch grants no audit treatment. The old
allowances, private backport capability, expiry and frozen consumer scope now
serve no accepted finding and are removed together. This is retirement of
exceptions after remediation, not a new treatment or an expiry extension.
Dated historical assessments remain unchanged.

## Retained enforcement

The guard pins exact SHA256 values for the current root lockfile,
scripts/dependency-patches.js, patches/dependencies/manifest.json and the
remaining Braces and Metro patch artifacts. It executes the actual verifier
against the physical installed dependency tree; a successful registry report
cannot override missing, altered, partial, nested or symlinked patched inputs.
The pin updates bind these already-reviewed current artifacts. No stale Forge
patch or obsolete individual consumer-file pin remains.

Classification reads actual vulnerability rows and causes, rather than trusting
metadata totals or npm exit 0. Unknown severity, mismatched identity/path,
missing cause, severity masking and ungrounded dependency cycles deny. Valid
lower dependency cycles can propagate a concrete advisory; a separate
advisory-free branch cannot borrow evidence from a sibling. Every HIGH and
CRITICAL row and propagated parent blocks regardless of its former exception.

Registry subprocess calls retain a bound of 45 seconds per attempt, up to
three attempts for transient failures with delays of 1 and 2 seconds, and failure
for unusable JSON, unsupported report versions/statuses and errors attached to
otherwise usable reports. Source commit/status provenance remains required in
CI. Dirty-tree metadata is retained rather than presented as protected-release
acceptance; release guards separately establish the authorized release source.

Each run retains exact stdout/stderr, their SHA256 hashes, the usable full raw
report, reviewed input hashes, script hash, source provenance, blockers,
registry severity totals and timestamps in a decision record. Symlinked evidence
directories and reviewed inputs fail. A failed attempt is retained and cannot
silently become a clean audit. No allowance or expiry field appears in the new
decision record.

## Verification and limits

Regression checks exercise the actual CLI and physical patch verifier with only
clock, Git metadata and registry output supplied as synthetic boundaries. They
cover former exact allowances, HIGH/CRITICAL on exit 0, misleading metadata,
valid lower findings, malformed/masked graphs, pinned/symlinked/missing inputs,
installed corruption, artifact redirects, provenance, retry recovery/exhaustion,
nontransient errors, dates across the former expiry, raw evidence and hashes.
The full candidate also runs its real registry audit; exact results and source
hashes are retained separately as evidence, including failures before repairs.

This local guard change does not prove protected CI, a combined production
artifact, hosted/provider configuration, media revocation or any other launch
gate. The public beta still requires the full launch checklist and applicable
action-time confirmations.
