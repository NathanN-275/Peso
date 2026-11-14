# R1 isolated candidate — stopped on newly reported CRITICAL cause

For Nathan, 2026-10-06 America/New_York. Nathan approved only
[R1's two root patches and consumer-test scope](root-dependency-remediation-proposal-20261006.md)
in this chat. **R1 is incomplete; Gate 2 remains FAIL.** No candidate lock or
test change was applied to the workspace. This record is the only intended
tracked change in this chunk. No launch gate advanced.

## Source and exact candidate bytes

Baseline source: `f4793729b78d015829f0601bd8cc79d45030295e`, tree
`ce47797beb42a933b232ebc0872dd7479b9a3557`, branch
`fix/merged-source-secret-coverage`. A Git archive created the isolated copy
at `/private/tmp/peso-root-r1.T40UNC`; it has no Git metadata. Committed sanitized
`.env.example` templates are source fixtures, not active configuration. No
active env files, credentials, existing dependencies/dist, ignored backup/raw
provider data, or the five untracked notes were copied or loaded.

Strict whole-lock comparison passed: identical keys/package paths and every
other entry byte-for-byte unchanged. Only compression 1.8.1→1.8.2 and
source-map-js 1.2.1→1.2.2 changed, using the reviewed registry resolution/SRI;
compression adds the edge to already locked destroy 1.2.0. No direct manifest,
parent, parser, peer, override or lifecycle-permission change.

| Input/artifact | SHA-256 |
| --- | --- |
| Workspace/baseline `package-lock.json`, unchanged | `0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c` |
| Isolated candidate lock; **not applied or approved as a security pin** | `db55ca8bd50b721df2066c68e5161efc684663ae5644ca0353fc5ab1fb6639cd` |
| Final candidate `scripts/root-dependency-consumers.test.js` | `7d25cee00380d2606a6e6d23b1abbe91152f500cfdef37ff31916d62204fe5ac` |
| Unchanged root audit guard | `672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170` |
| Retained evidence inventory, 55 files | `ce2746d907ca9d270b4916b34baa4a8cbc83226b373e15be5bf3da2dd4600266` |

Retained ignored evidence:
`/Users/nathan/Downloads/peso-app/artifacts/root-r1/run-xcorxJ`.
It contains candidate lock/test bytes, verification utilities, complete command
outputs/receipts, package byte inventories and raw audit output/decision. All
receipt stdout/stderr and audit-attempt checksums were independently recomputed
after copying and matched. This local copy is not hosted CI, protected backup or
a generated frontend artifact. The original isolated directory was preserved.

## Red → green and verified install/consumer results

TDD used the approved dependency/consumer seams. The compression test invokes
real middleware through a tiny loopback-only unfinished HTTP response, aborts
the client, and observes the real native stream's public `destroyed` property.
Only Node's public zlib factory boundary is instrumented; no fake stream,
dependency replacement, private handle or memory/timing-based assertion is used.
Factories/resources are restored and closed even on red runs. No exploit
traffic reached a provider or application service.

- RED compression 1.8.1: native stream remained open after response close.
  GREEN 1.8.2: the same cleanup assertion passed.
- RED source-map-js 1.2.1: constructor accepted an indexed line offset of
  10,000,001. GREEN 1.2.2: constructor rejected it before traversal. The test
  never iterates or serializes an oversized map.
- Added bounded compatibility checks for real PostCSS nested CSS/map positions,
  unchanged selector/Tailwind prefix output, and actual installed Expo wrapper
  compression for `.bundle`/`.map` versus an unchanged `.txt` response.

PASS: final **5 tests, 0 failures/cancellations/skips** on Node 24.18.0 and
Node 20.20.2. Node 20 exercised the Node-24-installed JS candidate; it did not
receive a separate clean install before the stop. Its isolated official darwin-x64
archive SHA-256 matched
`8be6f5e4bb128c82774f8a0b8d7a1cc1365a7977d9657cece0ca647b3fe04e61`
against [Node's checksum list](https://nodejs.org/dist/v20.20.2/SHASUMS256.txt).
No global/user runtime changed.

PASS on Node 24.18.0/npm 12.0.2: clean `npm ci --ignore-scripts --no-audit
--no-fund`, explicit unchanged local patch apply/verify, and typecheck. No
third-party lifecycle scripts ran. Existing UUID deprecation was recorded,
not suppressed or fixed outside scope. Registry tarball SHA-512/SHA-256 matched
the reviewed targets; all 4 compression and 18 source-map-js shipped regular
files matched installed bytes. No installed target patching was needed.
Canonical package inventory digests: compression
`06e967eb679a4474c9ef064ec14b952beb846ace9b9688a5b5244e53f78c6690`;
source-map-js `96d90ee8e22cca13c8ece14ddfb23504214e62bc810bfac46eb0ecf6ff407972`.

Setup/fixture failures are explicit: the first install used the escalated shell's
unsupported Node 22.12.0, so was not accepted; the first pinned retry failed
before install because both npm configs resolved to `/dev/null`. A distinct
empty global config and explicit Node 24 invocation resolved setup before
dependency changes. An initial source-map test was accidentally placed inside
the capture helper, causing a parent failure; its retained output is not counted
as the clean red reproduction. Corrected top-level RED had 1 pass/1 failure,
then GREEN had 2 passes. Final test bytes and later receipts are hash-bound above;
early tracer-bullet output receipts do not contain a full early test-source hash.

## Failed policy suite — no suppression or pin refresh

Node 24 full `npm run test:policy`: **348 total, 335 PASS, 13 FAIL,
0 cancelled/skipped**. All 13 are in unchanged `scripts/npm-audit-ci.test.js`;
the unchanged reviewed-lock pin stops CLI fixtures before their intended
assertions. They are recorded failures, not passes, exclusions or acceptance.
Eight were already failing at the scope guard; the changed candidate lock moves
failure earlier and shadows five additional fixture assertions. No test or
validator was rewritten to conceal this.

Failing line numbers: **393, 400, 409, 419, 436, 467, 485, 498, 505, 554,
561, 584, 617**. The five additional tests respectively cover a new frontend
consumer, root/TS entrypoints, export entrypoint, old/missing/extra installed
copies, and an unpatched installation. Complete output remains retained at
`checks/policy-node24/stdout`, SHA-256
`d6aa902e6c84e9e5b9333546f029216ac897a2abd12a0fc16c045e18ce52351d`.

## Fresh raw audit and new independent blocker

Read-only candidate root audit at **2026-10-06T17:30:07.790Z**:
**23 HIGH, 8 MODERATE, 1 CRITICAL**, total 32, raw exit 1.
Compression/source-map-js entries and their two advisory causes are absent in
this dated report. That observation plus tests/installed bytes supports the two
targeted candidate fixes, not a clean registry audit or security acceptance.

Original evidence: `/private/tmp/peso-root-r1.T40UNC/artifacts/npm-audit/run-b62SLz`;
retained copy: ignored receipt directory above, `audit/`.
Report SHA-256:
`b80b5e4a17e69ccddb6d55aa0677acb1af89269f6f8020cf71582f98a3d0e77f`.
Decision SHA-256:
`3c062a71e32cf84b77708709babb833e7abe75af40b2c8f73edc42ff61b571e0`.
Real guard exit 1: **Audit reviewed evidence mismatch: package-lock.json**.
Its source metadata is null (source-only isolated copy); the external receipts
record the baseline commit and actual candidate lock/test hashes. No fake Git or
CI provenance was supplied. The guard stopped before policy classification;
no treatment acceptance or zero-blocker result is claimed.

The new raw CRITICAL leaf is **shell-quote 1.9.0**, source **1241332**,
[GHSA-pqg4-j6r4-53mv](https://github.com/advisories/GHSA-pqg4-j6r4-53mv),
affected range `>=1.8.4 <1.11.0`, path `node_modules/shell-quote`.
The official advisory was added to GitHub's database on October 6 and identifies
1.11.0 as patched. It describes unsafe line terminators in string tokens after
a comment token when quoting shell commands. The dated raw report is retained
even though its CVSS/severity metadata differs from the current page.
No payload was sent to a shell or provider; no applicability exception is issued.

The main agent verified that this leaf is **identical in baseline and candidate**:
resolved `https://registry.npmjs.org/shell-quote/-/shell-quote-1.9.0.tgz`,
integrity
`sha512-Iov+JwFv/2HcTpcwNMKd8+IWNb8tboQJNQTkAY/LLVK7gGH9jy+LGkVqPxfekHl+yMmiqXszdGWXgkfml7hjqA==`.
Its sole locked dependency parent is react-devtools-core 6.1.5 → `^1.6.1`.
The range can admit 1.11.0, but that is not tarball/consumer/compatibility review
or permission to add a third upgrade. New HIGH/CRITICAL findings block regardless
of whether an existing guard fails earlier on its reviewed-input pin.

Existing raw braces/Forge/image-size findings and selector-parser MODERATE/LOW
causes remain. Web audit was not rerun: its last commit-bound result remains
7 HIGH/1 CRITICAL/1 MODERATE at source
`80bab91d42bd79f00086b3453d79497e06c842e7`; see the R1 proposal's hashes.

## Stop and next blocker

Stopped before workspace application/implementation commit, separate Node-20
clean install/typecheck/full suite, candidate builds/budgets, generated-artifact
or Forge execution-path proof, hosted CI/retention/privacy/bindings, push, merge,
workflow dispatch, migrations, provider changes or deployment. These unrun checks
are not skips that count as acceptance. Workspace root/web dependencies, test
files, audit guards, installed dependencies, existing dist and all five notes
remain untouched. Both security pins, all allowances, patch/consumer evidence
and **2026-10-12T23:59:59Z** expiry remain unchanged.

- Next bounded chunk: primary-source/registry-byte and actual locked-consumer
  review of shell-quote, followed by a separate remediation proposal for Nathan.
- Do not extend R1, update shell-quote or refresh either security pin without
  that review and specific approval. A frozen-scope refresh cannot clear a new
  CRITICAL finding.
- After any approved remedy, resume isolated clean installs on Node 20/24,
  security/consumer checks and all failed policy/audit gates before reconsidering
  workspace application; final-byte R2/Stage B remains separate and unapproved.
