# Gate 2 reconciliation — next bounded web resolution

For Nathan, 2026-10-06 America/New_York. **Gate 2 remains FAIL.** This chunk
reconciles retained evidence and authority; it implements no dependency, test,
guard, pin or provider change. The research skill supplied a separate current
[cache advisory recheck](marketing-cache-advisory-recheck-20261006.md) while
the main agent checked local artifacts, input bytes and treatment boundaries.
No later launch gate advanced or was assumed complete.

## Actual source and evidence identity

Inspected local source: `c599bfb315e2971fac8284dfe34c210676186a9c`, tree
`1c4a510ad7dc0a0039b9b7e86763a6f269f31f4e`, branch
`fix/merged-source-secret-coverage`. Tracked source was clean; five original
untracked notes were observed, hashed and preserved. This is not a claim about
the current remote branch, main, PR checks or provider deployments. The fixed
merged-main comparison is `98bad175cf2025741632244f4dd2da6b9866f87f`.

Read the authoritative [14-gate plan](public-beta-launch-plan.md),
[PRR](../product/PRR.md), prior root/web proposals and implementation records.
Gate 2 is the active failed security checkpoint; the eventual final-source
freeze still needs revalidation after candidates are actually applied. No
credential/authentication/recovery/migration/admission/operational/provider or
acceptance gate is inferred complete from earlier checks.

Ignored current inspection receipt:
`artifacts/gate-2-reconciliation/run-nX0DbQ/reconciliation.json`, SHA-256
`b71dbadbf6d35da6e13939b50401d33e158b74088719b6c9e67768fadc2aa064`.
Its eight-file evidence inventory SHA-256 is
`72dcd3e6325be08317dcd6f4161b78b80930e801ba7c58c5c8a2c02f9f7ae4ce`.
It binds input hashes, source/scope comparisons, retained-audit inspection and
read-only patch verification. It is local evidence, not hosted CI or a backup.

## Workspace is not the isolated root candidate

| Root leaf | Actual workspace lock/installed version | Tested isolated R1-SQ version |
| --- | --- | --- |
| compression | 1.8.1 | 1.8.2 |
| source-map-js | 1.2.1 | 1.2.2 |
| shell-quote | 1.9.0 | 1.11.0 |
| postcss-selector-parser | 6.1.2 | 6.1.2, unchanged |

Workspace root lock remains
`0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c`.
The [verified isolated candidate](root-dependency-r1-sq-isolated-verification-20261006.md)
lock is `4cedd8e60ddf78842e2a1365b077e8642e1788591178a0e13984c3336a607ad3`;
test bytes are `a6803c7aa6a9a880aef99e4f957a0c3c7c93c00bb8eeae96053855cc5f292042`.
It has not been applied or approved as a security pin. Its null candidate Git
metadata and external source/candidate bindings remain explicit.

Retained, not rerun here: separate clean Node 20/24 installs, 19 consumer tests
passing on each, typecheck and installed-byte verification. Both full policy
runs remain **349 PASS / 13 FAIL / zero skips**. Both root audits/guards remain
FAIL: Node 24 has **25 HIGH / 8 MODERATE / 0 CRITICAL**; Node 20 has
**23 HIGH / 8 MODERATE / 0 CRITICAL**. Root HIGH findings are still raw findings,
not a clean registry audit. These zero-CRITICAL candidate reports do not describe
the unchanged workspace containing shell-quote 1.9.0.

R1-SQ approval explicitly withheld workspace application. The earlier R1
conditional application language does not override that later, narrower scope.
Neither approval authorizes current root-lock/scope pin changes, push or deploy.
The selector-parser MODERATE/LOW and UUID MODERATE risks remain recorded. The
existing HIGH threshold is not lowered or reinterpreted; parser 7.1.6 does not
fit the reviewed Tailwind/nested-parent ranges, so no override or major parent
migration is inferred necessary or authorized by this reconciliation.

## Marketing remains unremediated and its old audit was dirty

Workspace `web/package.json` and `web/package-lock.json` remain respectively
`91ef9fa6dd1231e9331627ea48a621bbf6b798443747503a407b2d68cb543137` and
`af4b8931f67be644bbe14c5cf73600d1d9e44e43e6dc171486169c7d01f3ab91`.
All nine relevant installed marketing versions match this unchanged lock.

Retained web audit `artifacts/npm-audit-web/run-yzxH6V` began at
`2026-10-06T14:33:21.967Z` and records npm 12.0.2. It remains
**7 HIGH / 1 CRITICAL / 1 MODERATE**, raw exit **1**, guard exit **1**.
Report SHA-256:
`1d19ca0390c2859f076fb73bcb27e5899559c64d7bab9c7c1eb2ed19aae03a35`;
decision `433dbdf35dc8642a9039d320f6bd536dd442a49fda85dbc2c587f7523d17ec06`.

Important provenance distinction: its recorded commit is
`80bab91d42bd79f00086b3453d79497e06c842e7`, tree
`7a5ccd7d31d59195c46a1e698145299516eebe88`, **dirty: true**,
`scriptMatchesCommit: true`. Its guard script matches committed bytes, but the
run is not clean-CI acceptance at that SHA, and certainly not at today's HEAD.
The before/after web input hashes match each other and today's unchanged files;
full attempt bytes/checksums were reverified. No fresh web audit ran here.

The [existing Stage-A proposal](marketing-security-remediation-proposal-20261005.md)
and [primary-source review](marketing-dependency-primary-source-review-20261005.md)
identify these still-uninstalled targets; dated fix research is not install or
current-audit acceptance:

| Package | Current locked version | Reviewed target / hold |
| --- | --- | --- |
| Astro | 7.1.6 | exact 7.2.8 |
| devalue | 5.9.0 | 5.9.3 |
| http-cache-semantics | 4.2.0 | **preserve 4.2.0; unresolved HIGH** |
| js-yaml | 4.3.1 | 4.3.2 |
| nanoid | 3.3.17 | 3.3.18 |
| Sharp | 0.35.3 | 0.35.4; native/libvips byte proof remains required |
| source-map-js | 1.2.1 | 1.2.2 |
| SVGO | 4.0.2 | 4.1.0; changed parser/dependency behavior remains untested |
| smol-toml | 1.7.1 | 1.9.0, compatibly addressing the recorded MODERATE |

## Current cache hold and Astro constraint recheck

The research sidecar's owning API/database/registry observations on October 6
still show [GHSA-ch52-4w7c-c8xp](https://github.com/advisories/GHSA-ch52-4w7c-c8xp)
active, affected `<=4.2.0`, patched version **None**, not withdrawn. Latest
registry version is still 4.3.0, and the linked database withdrawal request is
open. The owner dispute and range escape do not establish a security fix.
The prior library/consumer fixture and source comparisons are dated evidence,
not rerun fixtures, current tarball proof or generated/runtime exclusion.
The sidecar retained selected fields/response hashes only; its raw response
bodies were memory-only, not a durable raw-evidence archive.

The main agent separately fetched [exact Astro 7.2.8 metadata](https://registry.npmjs.org/astro/7.2.8)
at `2026-10-06T18:28:10.827Z`. Its declared SRI matches the previously proposed
identity. It declares Node `>=22.12.0`, npm `>=9.6.5`, cache `^4.2.0` and
optional Sharp `^0.35.4`. **Cache 4.2.0 satisfies this parent range**, so a cache
upgrade is not forced by that constraint. Node 20 root checks cannot be
presented as supported Astro-7 build checks; the web trial uses explicit Node 24.

The browser retrieval was unavailable; approved public HTTPS fallback supplied
the exact registry response. This fresh metadata/range check is not an Astro tarball/source, signature,
installation, native-library, API or build pass. Exact raw metadata was retained
outside Git, SHA-256
`d240fdf3591105ba923b72504001dc35a358f7ed1dd421ab55544f373930dec1`;
constraint receipt `6e0139f8674ba2d9adfba622fd3a1bfcab69aef55d73ecb6000fe9716994da79`.
No package code or hook ran during the network check.

## Independent review holds — none can clear another

- **Root reviewed-input hold:** the applied source still pins the original
  root lock. The isolated three-leaf candidate would fail that pin before scope
  and classification. Passing its consumer tests cannot enable the treatment.
- **Frozen-scope hold:** recomputed 149-file merged-source fingerprint remains
  `6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
  Current **unapproved intermediate** fingerprint is
  `cf27b590dc1be86cd69303207157cb4d6c23f3527ff59d68edf48699a9a0945a`.
  Exactly two files differ: `scripts/build-web.js` and
  `scripts/release-verify.js`, the already approved Stage-A enforcement edits.
  This is not a proposed final pin for the future web candidate.
- **Cache hold:** web guard accepts no HIGH/CRITICAL exceptions. A future
  green report, source search, static config or owner dispute cannot dismiss
  the recorded unresolved cache behavior. No new patch/treatment is approved.
- **Artifact/consumer hold:** Forge prebuilt bundles remain unpatched. Current
  source and pinned installed consumer checks do not establish exact generated
  marketing/combined output or deploy execution paths. DevTools' unchanged
  prebuilt boundary also remains explicit. No existing unbound dist is accepted.
- **Hosted/execution hold:** current Linux CI, retained artifacts at the actual
  source SHA, Netlify actual commands/protection/API/DB binding and exact hosted
  artifacts remain unverified here. Source workflow retention settings are not
  live retention/privacy evidence. Production-source/manual migration skips
  remain nonacceptance; no dispatch occurred.
- **Expiry hold:** root backport cutoff remains **2026-10-12T23:59:59Z**, with
  no automatic renewal. Root guard, patch/verifier/manifest/consumer/advisory
  pins and existing allowances are unchanged. No new web exception is borrowed
  from the root treatment.

## Next bounded action W1 — lock-only web resolution, then stop

Existing Stage-A authority permits isolated web resolution; it does not permit
R2/Stage-B pin refresh or any release action. Narrow the next chunk to:

1. Use a genuine isolated checkout of the exact committed source with actual
   Git provenance, omitting historic objects, active env, dependencies/dist,
   ignored exports/backups and five untracked notes. Do not manufacture Git
   evidence or label changed candidate files as committed/clean CI bytes.
2. Propose only the exact Astro target and reviewed fixed web targets above,
   with required related transitive/native-package lock entries individually
   enumerated. Keep `http-cache-semantics` **4.2.0**, its resolution/integrity
   and all unrelated entries unchanged. Root manifest/lock and root candidate
   files stay out of this web-only write scope. No override, force, blanket
   audit fix, new direct dependency or optional/dev/peer omission.
3. Before accepting any candidate graph, refresh target registry/fix identity
   checks, enumerate the complete before/after lock diff and related consumer
   changes, and validate all parent ranges. Stop if preserving these boundaries
   is impossible or if unexpected dependency/manifest/lifecycle churn appears.
4. Resolve **lock-only with scripts disabled** on explicit Node 24; no package
   install, package/native execution, third-party lifecycle approval or frontend
   build in W1. Run the unchanged real web guard against the complete candidate
   lock and retain raw output/decision, real Git dirty state and exact hashes.
   Cache or any other remaining/new HIGH/CRITICAL must keep that guard FAIL.
5. Stop with the candidate graph, audit evidence and remaining remedy proposal.
   A lock-only trial is not installed-byte, native/libvips, consumer/API,
   typecheck/build/budget, artifact or policy acceptance. Do not apply it to
   the workspace or use a direct Astro/Expo invocation to bypass the guard.

This narrow resolution is within the prior approved targets, not a new cache
remedy. If fixing/removing the cache path or introducing a verified local patch
requires broader changes, prepare a separate exact primary-source/byte/test
proposal and seek Nathan's approval. No applicability exception is proposed on
the currently incomplete artifact/runtime evidence. Additional dependency tests
must use agreed public seams; no unreviewed test/refactor scope is inferred.

## Verification and stop

PASS this chunk: 151 files across the retained R1-SQ/R1/shell-quote inventories;
retained web report/attempt/decision checksums and before/after input bindings;
149-file scope comparison; installed version/lock matches for four root and
nine web leaves; unchanged local patch verification; exact proposed Astro
metadata identity/cache-range check. Source/notes/input hashes stayed unchanged.
These are inspection checks, **not fresh security-policy or deployment passes**.

FAIL remains: root/web security acceptance and both pin holds. Retained policy
failures and raw findings remain recorded above. NOT RUN here: new root/web
audit, candidate resolution/install, regression/full suite, typecheck, builds,
generated/hosted artifacts, provider privacy/bindings, migration or release
acceptance. No executed test skips are used as acceptance evidence.

Only this reconciliation and the sanitized research note are intended for a
local docs commit. No CONTEXT/ADR term or architectural decision changed. No
push, dispatch, provider/database/credential mutation, paid resumption, production
merge/deploy or public exposure occurred. Stop at Gate 2.
