# Astro additional transitive scope — lock-only proposal

For Nathan, 2026-10-06 America/New_York. **Proposed, not approved or applied.**
Gate 2 remains **FAIL**. This supplements the previously approved
[marketing Stage A scope](marketing-security-remediation-proposal-20261005.md)
after W1 stopped on additional Astro requirements. It is not Stage B, a security
pin refresh, a package-install approval, or a deployment decision.

## Source and inspection boundary

Inspected local source: `dd20508717af1c8a0041a200642aa1e0f11a4219`, tree
`a1129112546d7292ba373c5006ce26192ac3bd10`, branch
`fix/merged-source-secret-coverage`. The main agent mapped registry identities
and ranges while the research skill's sidecar prepared a separate
[primary-source compatibility review](astro-additional-transitive-compatibility-review-20261006.md).
Only sanitized documentation is intended for the local commit. The five original
untracked notes, dependencies, security pins and provider state are preserved.

Before-state root lock SHA-256:
`0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c`.
Web manifest and lock respectively:
`91ef9fa6dd1231e9331627ea48a621bbf6b798443747503a407b2d68cb543137` and
`af4b8931f67be644bbe14c5cf73600d1d9e44e43e6dc171486169c7d01f3ab91`.
No package/lockfile was edited and no npm resolution, install or audit ran here.

Raw public registry responses and generated helpers/receipts remain ignored at
`artifacts/astro-transitive-proposal/run-mPSuiH/`. They contain no credentials or
provider exports and are not hosted CI retention or a recovery backup.

| Evidence | SHA-256 |
| --- | --- |
| Revised additional identity list, including the already reviewed Astro | `dc996e34e8d4a699bed13df0d26c569bc80be7e89c046b5bef92fd736623895c` |
| Initial metadata identity/range graph | `4873a123e7a55fe2313c234a5267b4c0d50acbdfd1e11c1ad3b53bae34fd1e60` |
| Reconciled revised identities and all 100 immediate edges | `3d78b954e77f6c6c9548990784c82a1b6edea3df4855d45cfc7b7606d75f3229` |
| Undici rejected-floor/current-patch proposal receipt | `662cb101a1c565050c10186992584d0dfa77e48f2befe3d891b06230d7f3ae45` |
| Partial layout diagnostic, **FAIL**, described below | `b6f85861246456267cd30dc19bb84b87fac5b792e613a78234c2080ef0c192b6` |

Existing installed `semver` was used only as a metadata/range comparison utility;
no proposed dependency, native package or lifecycle hook was executed.
These hashes bind research data, **not a candidate lockfile or approved security
pins**. Thirty exact registry records were fetched: the current Astro plus **28
additional identities**, and the rejected initial Undici 8.0.0 record.
The browser could not retrieve these registry URLs;
approved credential-free public HTTPS requests provided the exact responses.
Each response has its own URL, retrieval time and raw hash in the receipt.
Registry-declared SRI/signatures do not establish downloaded tarball, signature,
installed-byte, native ABI or consumer acceptance; no such claim is made.

## Proposed exact additional versions and parent requirements

Use the smallest reviewed stable floors below, not a moving latest tag. Every
record exists and has no deprecated field at this observation. This is an
identity/range closure for the additional graph, not npm's resolved placement.

| Parent / requirement | Locked identity | Exact trial identity |
| --- | --- | --- |
| Astro → compiler-rs `^0.4.0` | 0.3.2 | 0.4.0 |
| compiler-rs → compiler-binding `0.4.0` | 0.3.2 | 0.4.0 |
| compiler-binding → nine platform packages, exact `0.4.0` | 0.3.2 each | 0.4.0 each |
| Astro and markdown-satteri → internal-helpers `0.10.4` | 0.10.2 | 0.10.4 |
| Astro → markdown-satteri `0.3.8` | 0.3.5 | 0.3.8 |
| markdown-satteri → satteri `^0.10.3` | 0.9.5 | 0.10.3 |
| satteri → nine platform packages, exact `0.10.3` | 0.9.5 each | 0.10.3 each |
| Astro → diff `^9.0.0` | 8.0.4 | 9.0.0 |
| Astro → unifont `~0.7.5` | 0.7.4 | 0.7.5 |
| unifont → undici `^8.0.0` | absent | **8.10.2**; initial 8.0.0 floor rejected |
| Astro → find-proc `0.1.0` | absent | 0.1.0 |
| compiler WASM → wasm-runtime `^1.2.2`; Satteri WASM → `^1.2.3` | 1.2.2 | 1.2.3, satisfies both |

Owning metadata:
[Astro](https://registry.npmjs.org/astro/7.2.8),
[compiler-rs](https://registry.npmjs.org/@astrojs%2Fcompiler-rs/0.4.0),
[compiler-binding](https://registry.npmjs.org/@astrojs%2Fcompiler-binding/0.4.0),
[internal helpers](https://registry.npmjs.org/@astrojs%2Finternal-helpers/0.10.4),
[Markdown wrapper](https://registry.npmjs.org/@astrojs%2Fmarkdown-satteri/0.3.8),
[Satteri](https://registry.npmjs.org/satteri/0.10.3),
[diff](https://registry.npmjs.org/diff/9.0.0),
[unifont](https://registry.npmjs.org/unifont/0.7.5),
[Undici](https://registry.npmjs.org/undici/8.10.2),
[find-proc](https://registry.npmjs.org/find-proc/0.1.0),
[WASM runtime](https://registry.npmjs.org/@napi-rs%2Fwasm-runtime/1.2.3).

Both platform families contain exactly these nine suffixes: `darwin-arm64`,
`darwin-x64`, `linux-arm64-gnu`, `linux-arm64-musl`, `linux-x64-gnu`,
`linux-x64-musl`, `win32-arm64-msvc`, `win32-x64-msvc`, `wasm32-wasi`.
Prefixes are `@astrojs/compiler-binding-` and `@bruits/satteri-` respectively.
Retain all optional/native/WASM lock entries; a macOS trial cannot omit Linux,
Windows or WASM from the report. Metadata OS/CPU/libc selectors were retained;
neither those selectors nor inclusion in a lock verifies platform execution.

## Engine, lifecycle and preserved-identity constraints

All 29 proposed records' declared Node requirements admit explicit **Node
24.18.0**. That is a metadata check, not actual hosted runtime acceptance.
[Undici 8.10.2](https://registry.npmjs.org/undici/8.10.2) requires Node
`>=22.19.0`, stricter than Astro's `>=22.12.0` floor. Marketing trials must use
Node 24; root Node 20 results cannot count as Astro-7 acceptance.
[wasm-runtime 1.2.3](https://registry.npmjs.org/@napi-rs%2Fwasm-runtime/1.2.3)
declares `^20.19.0 || ^22.13.0 || >=23.5.0`. Do not extend these results to an
uninspected provider runtime or all Node versions allowed by Astro alone.

Undici declares `prepare: husky && node ./scripts/platform-shell.js`. It did not
run and receives **no lifecycle approval**. None of the other 28 records declares
preinstall/install/postinstall/prepare in inspected metadata. The next operation
remains scripts-disabled lock-only; no third-party hook or package/native code
execution is authorized. Declared lifecycle metadata is not complete safety
proof of future package contents or installation behavior.

Preserve these compatible existing identities and their registry integrities:

- `@tybys/wasm-util@0.10.3` satisfies wasm-runtime's `^0.10.3`.
- Root `@emnapi/core@1.11.3` and `@emnapi/runtime@1.11.3` satisfy wasm-runtime's
  `^1.7.1 || ^2.0.0-alpha.4` peers; do not introduce alpha versions.
- Satteri WASM's existing nested `@emnapi/core@1.11.1` and
  `@emnapi/runtime@1.11.1` satisfy its exact declarations. Keep both nested
  identities rather than silently replacing them with root 1.11.3.
- `@types/hast@3.0.5` already satisfies Satteri's raised `^3.0.5` floor;
  its other existing type dependencies remain compatible.
- Ofetch stays because unstorage still requires it, although unifont removes
  its own ofetch edge. Unifont's existing ohash/css-tree identities fit.
- Astro's Markdown-remark peer declaration becomes 7.2.4, but remains optional
  and absent. Do not add it or treat an optional declaration as an installed path.
- Preserve `http-cache-semantics@4.2.0` with the exact old lock entry. It fits
  Astro's `^4.2.0` but retains the unresolved HIGH security hold.

The first metadata traversal kept compiler WASM's compatible old runtime 1.2.2
before discovering Satteri's stricter floor. The separate review receipt
reconciles **both** edges to the proposed 1.2.3 and rechecks their ranges; the
initial traversal is preserved, not presented as the final identity graph.

## Rejected Undici floor and revised patched proposal

Before presenting approval scope, a current
[public advisory query](https://api.github.com/advisories?ecosystem=npm&affects=undici%408.0.0&per_page=100)
at `2026-10-06T19:46:52.876Z` returned **22** active Undici 8.0.0 causes:
**7 HIGH, 10 medium, 5 LOW**. These are advisory-API cause counts/severities,
not npm package-entry totals. The initial 8.0.0 graph is **rejected**, retained
as investigation evidence, and not proposed for installation or acceptance.
All 22 identities, affected ranges and patch floors remain in the raw response
and revision receipt. Neither proxy-only source usage nor a source search
dismisses these findings.

The largest published v8 patched floor among those causes is **8.10.2**.
In particular, the HIGH
[TLS option-loss advisory](https://github.com/advisories/GHSA-w293-vg96-wgc3)
and [unrequested WebSocket subprotocol advisory](https://github.com/advisories/GHSA-rfgv-xxqx-mfg5)
both require it. The owning
[8.10.2 release](https://github.com/nodejs/undici/releases/tag/v8.10.2),
published `2026-09-04T13:56:45Z`, identifies those fixes and additional
origin/cache/retry/decompression corrections. Publication and later advisory
disclosure dates are different observations, not contradictory source SHAs.

Exact [8.10.2 registry metadata](https://registry.npmjs.org/undici/8.10.2)
was fetched at `2026-10-06T19:47:39.751Z`, SHA-256
`68f678fba4a4798b33e994b01744b53f843228367f441135c795ea48b87b2a1a`.
It fits unifont's `^8.0.0`, keeps Node `>=22.19.0` and the same prepare hook,
and declares no runtime dependency/optional/peer entries. Its registry gitHead
is `5e541e0b9df7563e5766bbd469fbfe383d9ae6ca`.
All 22 queried 8.0.0 causes exclude 8.10.2 under their reported ranges and list
an equal-or-earlier patch floor. The separate
[8.10.2 advisory query](https://api.github.com/advisories?ecosystem=npm&affects=undici%408.10.2&per_page=100)
returned zero records at `2026-10-06T19:47:40.059Z`.
That limited published-advisory lookup is **not** a complete fresh npm audit,
an unaffected-runtime declaration or acceptance of package artifacts.
The sidecar review records additional 8.10.2 behavior/provenance limits.

## Conditional orphan pruning — never blanket cleanup

A read-only overlay removes Astro's pluginutils edge and the Markdown wrapper's
hast-util-from-html edge. Baseline traversal has 295 reachable entries including
the root, with no missing/invalid ranges. The partial overlay identifies these
ten possible lost paths, but **does not authorize unconditional removal**:

| Old package/path | Locked version |
| --- | --- |
| `node_modules/@rollup/pluginutils` | 5.4.0 |
| `node_modules/@rollup/pluginutils/node_modules/estree-walker` | 2.0.2 |
| `node_modules/hast-util-from-html` | 2.0.3 |
| `node_modules/hast-util-from-parse5` | 8.0.3 |
| `node_modules/parse5` | 7.3.0 |
| `node_modules/hastscript` | 9.0.1 |
| `node_modules/vfile-location` | 5.0.3 |
| `node_modules/web-namespaces` | 2.0.1 |
| `node_modules/entities` | 6.0.1 |
| `node_modules/hast-util-parse-selector` | 4.0.0 |

The projection deliberately does not implement previously approved Sharp/SVGO
remediation: it leaves Sharp 0.35.3 under new Astro's `^0.35.4` requirement and
therefore **fails** the range assertion. Two diagnostic invocations exited 1;
the second retained the full result before the same unchanged assertion.
This is not a resolved candidate or a green graph check. The known Sharp 0.35.4
fix must accompany a future complete candidate; no validator was weakened.

The ten lost paths are candidates for conditional review, not proven orphans in
that future complete graph. Proposed trial authority may permit npm to remove
only these exact entries **after** complete prod/dev/optional/peer reachability
shows they are no longer needed, including the original Sharp/SVGO updates.
Preserve any still required by another parent. Any other pruning, relocation,
duplicate identity change or unexpected refresh stops for review. Do not manually
delete them to make a check pass, or add unrelated dependencies to preserve them.

## Exact registry-declared trial identities

This is the sanitized identity list bound by the SHA-256 above, not a patch or
install inventory. Each declared tarball URL is retained in `identity-list-revised.json`.
The following revised SRI values were **read**, not verified against downloaded tarballs.

| Package | Version | Declared tarball SRI |
| --- | --- | --- |
| @astrojs/compiler-binding | 0.4.0 | sha512-x2RjDUuWfwLNtc3mjAdSRInwqh/rqbLar9cm/5FOMbHvmYZB7yfKewzSclAxWjIZsypJDXv1lhaP2WG+P8TK3g== |
| @astrojs/compiler-binding-darwin-arm64 | 0.4.0 | sha512-ZVUwHundaQyFNjE6uoa0usaC0WOCitDCLS/4mdb4rOiJXwVUuKJBMxI5WMzXLWmamsXtK/Z//ifLXvV5Yeh4Hw== |
| @astrojs/compiler-binding-darwin-x64 | 0.4.0 | sha512-FI6G8AY8u6fR1SI/QRR5yGMwtvZwP34CDmZpZ5HwJGa50UM1VISTLhqkhV4a476pmgd25X1Aur2dqw6hUnrlKA== |
| @astrojs/compiler-binding-linux-arm64-gnu | 0.4.0 | sha512-lB9gLFJK7m82EnjaU8nlRBEfcwGNeHidW3sSjODTUjMNaoewVuUz9fwwdY5M4jiSXIqWLH3yl6TX8FTDKA74Sw== |
| @astrojs/compiler-binding-linux-arm64-musl | 0.4.0 | sha512-HPbvWqbxFxyaoQJhLxCaSjtYBx9KBo7JGVzEFZCmMl968a2PsSH0UfiODYgYPXofTOIsIH2aoCcrHXML0IA3ig== |
| @astrojs/compiler-binding-linux-x64-gnu | 0.4.0 | sha512-tQKolMxoJ/+0AmLWm1PmJ/i+z3i10ZU1bNuVjEDulCf48azEMtUNjTZgHJ5MPtpYRNc7dlETr8QujUfduzoC7Q== |
| @astrojs/compiler-binding-linux-x64-musl | 0.4.0 | sha512-5v5YymudsxMHp3NBLCS8BUlu5CRqeLtWD9cKS/4nIhIEHCbpz9okmVV6I0HWqmBAPhWYcDa3vw/vltYPrOQCTA== |
| @astrojs/compiler-binding-wasm32-wasi | 0.4.0 | sha512-m/phuH3x3PREvv1OnkM44NoPh4MatUadix1fB1u5SvMLCyDTUZykDJbKnWf1cjnYmHdlB8HcjTjl6JrCqAIXcw== |
| @astrojs/compiler-binding-win32-arm64-msvc | 0.4.0 | sha512-B9zYf3okEY83kM8gydlpH2BHP00w4ifxPqlYlWrgTwuD6wnkrJDCwBlgy1q31cERjCJRXN1lrE2VmkLvFjv/6g== |
| @astrojs/compiler-binding-win32-x64-msvc | 0.4.0 | sha512-zB0Nrv0dGc0zZWPGDRmmETTPhDRqyZjAjk+gWMlVrJX5U89obpB3VUUE1ZiHxOCN5LQojeLK6O8L/dnoHolvNQ== |
| @astrojs/compiler-rs | 0.4.0 | sha512-koVikeon1kreEy+/JzLQRy3vzHHQVOjycs4degg4vFufKApZOwMZvSSAEztYNhmcQVfNVsVZZI4cEge3cexAbQ== |
| @astrojs/internal-helpers | 0.10.4 | sha512-nozZSy/mKYLqe4YrqbKtdOszedAfXYCtw3wZ0d+CAjz4GqQ4L9rl1ltIL5BlgwmYVinJg/RZ0MgGuWOdlyRZlA== |
| @astrojs/markdown-satteri | 0.3.8 | sha512-n8ItpFTCmlDsVR5+rwDmehSf+jFCYLWmZiisZNGuF7xILqYhsVeBfcha4qgS2Seq3fAc9Tm58ZVrvqFQ6RQgRQ== |
| @bruits/satteri-darwin-arm64 | 0.10.3 | sha512-RBPx54YSt6ly9ozJ4AbgY6ITep3uJAaPE0ErxhQnE9Mk5ldGeQYbq4bWiJyZOoQmqC45cMCZmFyPjQdJT4biEw== |
| @bruits/satteri-darwin-x64 | 0.10.3 | sha512-l0G6eARLHwlFEc7KOzEr0Z7YVEUzAQVSDZcevGOng0ycFvY+Eg7SNpNAc5/k0XXKEM+Q62A8wUaaL+d0W63x7g== |
| @bruits/satteri-linux-arm64-gnu | 0.10.3 | sha512-U6Lv74zONfwnKbzPAylqp45isfUVJNQPnROlX1mWJ7TLCkJRKeYEFyNe5auZEynVY0ZrgyFe7mKE04dmsFqEhw== |
| @bruits/satteri-linux-arm64-musl | 0.10.3 | sha512-m/dsv+OsXuQMc0Mmkz1KAO0U/TbY+qe4puyhf08ce7EW5I+czxa5n5Vpy6ZTYwFvA3TtrokwiBRDApzz+oPeww== |
| @bruits/satteri-linux-x64-gnu | 0.10.3 | sha512-Y+YYrs3U+UhxRf3vn9Fgjo3NtjnqYBsAEpTrZcwfKpaiSXKpQlr4v2H9Lp4jtlC4PNjPr02wkiNtiAgNlhkB8w== |
| @bruits/satteri-linux-x64-musl | 0.10.3 | sha512-Fqg47592hkRebzI5EMU9BYnbFz7m/Q4awJt062xr9lweaHTmlN6ij/Z9Dzyt4THsqRFm87DZFMcwrniQpeEbPA== |
| @bruits/satteri-wasm32-wasi | 0.10.3 | sha512-OHBxAJMt97QNQJ8JbtdzdH54dWV7OT0pxl1wGZyD4vRDUeJjm5CXgeC/t1VJzD9tQiwPCVY3/Hh/88SJpVOj7g== |
| @bruits/satteri-win32-arm64-msvc | 0.10.3 | sha512-4+fLJgFthvZQHdpb1nVXQXH1T6spXs5fYj71KTvTOhsSZ3jA1VkvneVtv7VinX7vgtMu6PZGm/X3P84ancCMkA== |
| @bruits/satteri-win32-x64-msvc | 0.10.3 | sha512-BdbaBcnKktrNbAGibVnZFIZKtl+xl3TKvgLDNZempM0d2C+2l9OU874AqdhkOkegWk/vdCS1Z+wUD6W5KYUT9w== |
| @napi-rs/wasm-runtime | 1.2.3 | sha512-UMduMbqO5s5zF2NkNacMT/yK5Y5QiKvWr2+50bzIIxFDwVJ2h49b+oyjaCGPhJxd2/gC2x39EHv/gHVuu36x2Q== |
| astro | 7.2.8 | sha512-19nfgzl1IHNYzIfamUIr4dYSQcovWfMO5JGlN7Ahlg6Q6R+nzSPWAh+VO/mSg0hhcea35JHY0wL5ADZUi0WiYQ== |
| diff | 9.0.0 | sha512-svtcdpS8CgJyqAjEQIXdb3OjhFVVYjzGAPO8WGCmRbrml64SPw/jJD4GoE98aR7r25A0XcgrK3F02yw9R/vhQw== |
| find-proc | 0.1.0 | sha512-OaOpEYv2PiQ7SQ5LIrl+deA1XaWcxEjnpM6VuWXTUvn+teIXxeFTLDmu18/zDQpFmHN4o3oDBX+BT0AGwEhemg== |
| satteri | 0.10.3 | sha512-LBDONBUtj48XanFpLcCDvyCjBruz5aj5MGwE9gR+/RTB3monyglmh9jpGXuYUDO4rvBhvK2bpbjTKeU9kkHtfg== |
| undici | 8.10.2 | sha512-/y4/bH9YNU5hi9NIrpOuvGXFcxrj3CMrV+/AYpowAYTpHn8gX/XPFjNy766FPoYY0miQhdW977JFWKGNhBdwyQ== |
| unifont | 0.7.5 | sha512-ULe/Cs+ZIsq+dcFofNkhqielCrUJnb5mr+Yc4EBM2VlL+6OZR6+cjtI2mT1bJvRBrVncqHAbLURxmPLcCXzWMg== |

## Proposed next authority — W1 expanded, still lock-only

Request Nathan's approval of **only** the 28 additional exact identities above,
their required metadata/declaration changes, and conditional ten-entry orphan
review, alongside the original approved web targets. Approval would permit:

1. Use a genuine isolated checkout of the then-current exact source SHA, not
   fake Git provenance; keep credentials, active env, old node_modules/dist and
   five untracked notes out. Changing the sanitized docs commit is not security
   acceptance and requires the isolated source identifier to be refreshed.
2. Pin Astro's direct manifest declaration to exact 7.2.8 in that isolated web
   package. Propose only reviewed versions, all required prod/dev/optional/peer
   entries and proven orphan changes. No new direct transitive dependencies,
   overrides, force, blanket audit fix, root changes or omitted package classes.
3. Resolve only the web lock with scripts disabled on Node 24. Enumerate all
   before/after entries and fields, every preserved/new/nested consumer edge,
   peer placement and conditional pruning. Stop on unexplained churn, mismatched
   metadata identities, unexpected lifecycle declarations or impossible minimal
   preservation; do not silently choose later versions from broad ranges.
4. Run the unchanged real complete web audit guard, retain raw attempts/report/
   decision and actual source/tree/dirty hashes. A remaining or new HIGH/CRITICAL
   must fail. Preserve cache 4.2.0; do not call it patched or exempt.
5. Stop. No package install, scripts/native execution, tests/build bypass,
   workspace application, security-pin refresh, push/provider mutation or deploy.

This is trial scope, **not approval of future lockfile bytes**. Tarball/signature,
installed/native-byte, public-consumer behavior, policies/typechecks/builds and
generated/hosted artifact proof need separate future evidence and appropriate
authority. Do not skip those to meet the temporary audit treatment deadline.

## Verification and continuing release holds

PASS this research chunk: 30 registry identity/hash checks, all 100 revised reconciled
immediate edge declarations (one absent optional peer; concrete selected edges
range-checked), declared Node-24 compatibility, preserved external-parent range,
and 13 input/note hashes unchanged; current Undici cause/patch/range checks.
The secondary review retains its own limits.
The additional-identity mapping has no recorded incompatible unchanged parent;
this is not complete npm placement, security-audit or API acceptance.

FAIL: initial Undici 8.0.0 security floor and partial layout projection,
explicitly recorded above; Gate 2 still fails. The documentation check initially
rejected a macOS Git confstr warning as unexpected stderr. Its corrected helper
retains that exact warning while still rejecting whitespace diagnostics or any
other stderr; redacted Gitleaks and whitespace checks passed. The initial helper
and diagnostic failures are preserved, with no project validator changed.
Retained, not rerun: root isolated full policy 349 PASS/13 FAIL, web audit
7 HIGH/1 CRITICAL/1 MODERATE. Raw findings and missing audit/artifact/provider
evidence stay blockers. No fresh complete registry audit or executed test skips
are claimed here. NOT RUN: resolution/install, proposed dependency code/native execution,
consumer reproductions/controls, suites/typecheck/build, CI, generated artifacts,
Netlify privacy/API/database binding, migration, deployment or acceptance.

Existing root reviewed-lock and frozen-source pins remain unchanged; root R1-SQ
is still isolated and unapplied. Forge prebuilt bundles remain unpatched and
require exact generated/deployed execution-path proof. The root treatment still
expires **2026-10-12T23:59:59Z**, without renewal or broadened allowances.
No later launch gate is assumed complete. No CONTEXT/ADR change is warranted.

Next blocker: Nathan's specific approval of this expanded **isolated lock-only**
trial; the unresolved cache HIGH remains an independent blocker afterward.

- Review the exact identities, runtime floor, lifecycle prohibition, nested
  peers, compatibility risks and conditional pruning above.
- If approved, resolve the complete isolated reviewed graph, inspect every diff,
  run the unchanged audit guard and stop on failure.
- Propose a separate cache remedy if still needed; no range-escape upgrade,
  automatic exception, pin replacement or release action is implied.
