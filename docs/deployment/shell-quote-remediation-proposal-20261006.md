# shell-quote — bounded R1-SQ candidate proposal

For Nathan, 2026-10-06 America/New_York. **Proposal only; no implementation
authority yet. Gate 2 remains FAIL.** The research skill's background
[primary-source review](shell-quote-primary-source-review-20261006.md) verifies
the advisory minimum, owning fix, shipped bytes/signatures and behavior changes.
The main agent independently traced locked/installed consumers below.

## Baseline and evidence provenance

Reviewed HEAD: `b223b74b9e31a92f0b30b048b0e00303876db54b`, tree
`5395b7ab8df666ae4ca6a3a2093618ff45974782`. Tracked source was clean;
the five original untracked notes were preserved. Workspace root lock remains
`0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c`.
No package, lock, application/test file, pin or provider changed in this review.

The [held R1 candidate](root-dependency-r1-candidate-hold-20261006.md) remains
outside Git: lock SHA-256
`db55ca8bd50b721df2066c68e5161efc684663ae5644ca0353fc5ab1fb6639cd`,
test SHA-256 `7d25cee00380d2606a6e6d23b1abbe91152f500cfdef37ff31916d62204fe5ac`.
It has compression 1.8.2/source-map-js 1.2.2 but unchanged shell-quote 1.9.0.
Its retained 55-file inventory was reverified in this chunk.

No fresh audit/full suite was run. Retained R1 results remain:

- Root audit: **23 HIGH, 8 MODERATE, 1 CRITICAL**, raw/guard exit 1. Report
  `b80b5e4a17e69ccddb6d55aa0677acb1af89269f6f8020cf71582f98a3d0e77f`;
  decision `3c062a71e32cf84b77708709babb833e7abe75af40b2c8f73edc42ff61b571e0`.
- Full candidate policy: **348 total; 335 PASS, 13 FAIL, zero skips**. All
  failures hit the unchanged reviewed-lock pin; no assertions were rewritten.
- Prior candidate consumer suite: 5 PASS on Node 20/24. Separate Node-20 clean
  install/full verification did not run before the CRITICAL stop.
- Last web audit: 7 HIGH/1 CRITICAL/1 MODERATE at source
  `80bab91d42bd79f00086b3453d79497e06c842e7`, not refreshed by this review.

## Exact proposed target and compatibility boundary

The sole locked chain is React Native 0.86.2 → react-devtools-core `^6.1.5`
(resolved 6.1.5) → shell-quote `^1.6.1` (resolved 1.9.0 at
`node_modules/shell-quote`). **1.11.0 fits the existing parent range.**
Neither parent, any direct manifest nor a peer range needs changing for that
resolution. No override or latest-version update is proposed.

[GHSA-pqg4-j6r4-53mv](https://github.com/advisories/GHSA-pqg4-j6r4-53mv) identifies
affected `>=1.8.4 <1.11.0`, minimum patched **1.11.0**. The
[owning fix](https://github.com/ljharb/shell-quote/commit/6002b2ed90c6b83095eb272b6b0adaf3a172b0bc)
rejects LF/CR/U+2028/U+2029 in strings after a comment token. Database/maintainer
severity differences do not downgrade the retained CRITICAL finding or justify
an allowance. Source **1241332** and raw metadata remain recorded unchanged.

Exact candidate package identity from the primary-source review:

- Resolution: `https://registry.npmjs.org/shell-quote/-/shell-quote-1.11.0.tgz`.
- SHA-512: `sha512-JdxDPD0DBTyu08pq0kPC0xSNet/qsU07qT6IsX1AS8oO2ICNRY4ldNa8OAI6PuwAH8tG3lxEhbqmyp4Dw4036g==`.
- Compressed tarball SHA-256:
  `028be526afacb2bf5c6c008a95d5435b5d205135f68bb48afd0bb947610393f1`.
- Registry gitHead: `88241f8fa324a85da03b40fc69443c069837b472`.

All 11 shipped files were compared with immutable upstream source; integrity
and registry signatures passed. This verifies published-byte binding, not a
clean install, publisher attestation or Peso compatibility. No target code was
executed. Declared Node `>=0.4`, MIT license, CommonJS entry, named parse/quote
exports and zero runtime/optional/peer/bundled dependencies remain. No new
lifecycle scripts were introduced; existing package hooks must not be invoked.

Changes extend beyond the guard: parser handling of ANSI-C quoting, variables,
backslashes and substitution changes; optional unquoted expansion splitting
is added; quote handling of glob tilde/empty patterns and apostrophe/`!` changes.
That requires bounded compatibility controls, not an assumption that a same-major
update is behavior-identical. Existing engine declarations are not runtime proof.
This target addresses the dated advisory; future audit findings still block.

## Actual installed consumer and bundled-code boundary

The main agent inspected package manifests, entry shims, generated supplier
bundles/maps and React Native setup source. No DevTools initializer/server,
editor launcher, shell payload or provider call ran.

1. React Native's `Libraries/Core/setUpReactDevTools.js` imports
   react-devtools-core inside `__DEV__` branches. The package's main is
   `dist/backend.js`; `backend.js` also forwards to that file. This is an
   installed-source entry trace, not proof of production build elimination.
2. `standalone.js` forwards to `dist/standalone.js`. Its map contains shell-quote
   source content, including a quote function that differs from root 1.9.0.
   **Source-map content is not the executable bundle.** The exact embedded
   upstream version has not been identified.
3. Parsing the actual standalone bundle AST identifies module **8923** at
   byte range **[438018, 439928)** (UTF-16 offsets [438016, 439926)). Its body
   is a parser and exposes only `Q`. The observed consumer alias `fm.Q` parses
   `REACT_EDITOR`; surrounding editor-launch source passes arguments to spawn,
   rather than calling this module's quote function. The module's static export
   and alias trace is bounded; no full graph/runtime applicability claim follows.
4. Searching actual installed JS/CJS/MJS with ignore rules disabled found no
   literal direct shell-quote require/import outside its package. The backend
   map has no shell-quote source entry. These negative searches/maps are
   supplementary, not complete execution-path or generated frontend proof.

Main agent fetched the exact locked react-devtools-core 6.1.5 tarball and checked
its SHA-512 against the lock. **All 15 shipped regular files matched installed
bytes**, including actual standalone/backend bundles. Thus these inspected bytes
are not assumed to match upstream merely from a package version label.

| Installed/generated supplier evidence | SHA-256 |
| --- | --- |
| `node_modules/shell-quote/quote.js`, baseline 1.9.0 | `190b8d295c711d21a386d11486eeaa401f8426545dcb7fc839d40c9f7852030d` |
| React DevTools 6.1.5 compressed tarball | `cfe3ed5cdc7f8391d504fd35b2239d49ec4bd91d64990e80cdeebfbfe717f499` |
| `node_modules/react-devtools-core/dist/standalone.js` | `83ee56e2e867720123418336f83f1aea6c40a5d8c582da22f09e07d58d8bbce0` |
| Executable standalone module 8923 slice | `eec9239b76ff1bbe1a587fc4d04033be033493b78256d0ad9098651df7eacae5` |
| `node_modules/react-devtools-core/dist/standalone.js.map` | `8679428cfa8dcd725fb5a5d837d44a9078c6fe27c01dfddffc9e808f9f405bae` |
| Mapped shell-quote source content | `c93d1805a19c1363ba108c9319e26a57fcb4d861c199da9fd64dc83a79f6abe1` |
| `node_modules/react-devtools-core/dist/backend.js` | `1c9ca2a7b9f8709ee7a06b76caf500166f600b9c06b76294fed7eb69f2a28204` |
| `node_modules/react-native/Libraries/Core/setUpReactDevTools.js` | `fe78cfdc9ed165f2d3d38f065307a74579890b3c016fa63048c8f79609e42b86` |

A root leaf update **does not rewrite these prebuilt parent bundles or maps**.
No package-wide fixed/unaffected statement, scanner exception or VEX assertion
is issued. Actual Peso-generated artifacts/deploy paths remain unverified,
including excluded unpatched Forge bundles. If later proof finds a relevant
vendored vulnerable execution path, stop for a separate parent/artifact remedy.

## Local diagnostic verification completed

PASS on Node 24.18.0: actual 1.9.0 ordinary parse/quote round trip for literal
`code`, `--goto`, and `fixture path.tsx:12`; identical direct parser output.
Pure quote calls after a benign comment token **accepted and emitted all four
line terminators**. This confirms the vulnerable library behavior without
executing returned strings, launching editors or asserting Peso exploitability.
It is not a patched-candidate regression pass.

PASS: unchanged `npm run deps:verify`, 15 recorded file hashes, the retained R1
55-file inventory, actual AST/supplier-byte checks. Diagnostic outputs/scripts
are ignored in `artifacts/shell-quote-review/run-vUB0oq`, outside Git. Receipts:

- `consumer-receipt.json`:
  `ead57a869d0a161c57a6eef43e03fe9c4ba657acaf632bdcb0fe48e621b93a5e`.
- `parent-bytes-receipt.json`:
  `852532b91dc4e8034ad00dcae9a7a489bf4f0329fcd1b2614413b27211eb999b`.
- Five-file `evidence-inventory.json`:
  `33e9325028a0fc9a2557d8d95f21543cbe72a06f48fef9766ec5c0d313a1292a`.

One diagnostic script syntax error was corrected before generating its receipt;
the successful receipt does not claim that failed attempt passed. No fresh
candidate install, typecheck, full policy, audit, build or hosted check ran.
The current new/changed dependencies and all security gates remain unaccepted.

## Requested approval R1-SQ — isolated third leaf and public API tests only

Ask Nathan to approve this scope before implementing it:

1. Reuse preserved R1 evidence/candidate bytes or a fresh credential-free copy
   of committed source. Keep the five notes, active env, provider exports,
   backups and existing workspace dependency/dist trees outside the candidate.
   Source templates remain non-executable fixtures; disable dotenv loading.
2. Change **only shell-quote 1.9.0→1.11.0** in the isolated candidate's root
   lock using the exact identity above. Existing R1 compression/source-map
   entries and destroy edge remain unchanged; the whole root diff must contain
   only those three approved leaf entries. Preserve all manifests, parents,
   runtime dependency paths, peer ranges and lifecycle permissions. No override,
   forced update, blanket audit fix or automatic latest-version selection.
3. Extend the held candidate's `scripts/root-dependency-consumers.test.js` at
   these public seams: `quote()` after a comment rejects LF/CR/U+2028/U+2029;
   non-adjacent later tokens and parse-produced comment plus appended string
   also reject; ordinary parse/quote outputs and before-comment newline controls
   remain usable. Use benign in-memory tokens only, never execute output in any
   shell. Add regression controls for the changed quoting/parser behavior noted
   above. No implementation-coupled module-ID assertion in behavioral tests.
   Run security assertions RED against the old leaf before GREEN on the new one.
4. Run separate clean installs on Node 20/24 with **all third-party scripts
   disabled**, then explicitly apply/verify the unchanged local braces/Forge
   patches. Verify target SRIs/all installed package bytes and unchanged checked
   consumers; rerun the existing five tests, new quote/parse tests, typecheck,
   full policy and real complete root audit. Retain every failure and exact
   source/candidate/artifact hash, including dirty or absent Git metadata.
5. Keep both security pins unchanged. The reviewed-lock/scope guard remains a
   release hold; its known shadowing failures are recorded, not rewritten,
   suppressed or represented as security acceptance. **Any new unapproved
   HIGH/CRITICAL cause, install/compatibility failure, unexplained policy failure
   or evidence mismatch stops candidate work.** Do not generalize old allowances.
6. Stop after this isolated verification chunk with its exact evidence. This
   requested extension **does not authorize applying any held candidate changes
   to the workspace**, changing reviewed pins, push/dispatch or deployment.
   Workspace application is reconsidered only after the candidate hold is
   reconciled; final exact-byte R2/Stage B remains separately unapproved.

Neither this proposal nor a later R1-SQ approval authorizes vendor-bundle edits,
React Native/DevTools upgrades, parser-major remediation, web dependency changes,
an unresolved-cache exception or new lifecycle permissions. Root guard hash
remains `672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`;
reviewed-lock pin remains the baseline hash. Frozen-scope pin remains
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`;
expiry remains **2026-10-12T23:59:59Z**, with no automatic renewal.

## Stop and next blocker

Earliest launch gate remains **Gate 2/security**. Both new notes only are
intended for a local docs commit; no CONTEXT/ADR change is warranted. No provider,
database, credential, paid service, production branch/deployment or visibility
changed. No later launch gate is assumed complete.

- Obtain Nathan's specific **R1-SQ approval** for the isolated shell-quote
  target and public quote/parse test seams above; do not apply workspace changes.
- If approved, perform one bounded candidate chunk and stop at its result.
- Before any pin review or launch progression, reconcile all root/web findings,
  complete exact artifact/Forge-path evidence and rerun the failed security gates.
