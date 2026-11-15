# css-select lifecycle — bounded source review

For Nathan, 2026-10-06 America/New_York. **Read-only investigation with this
documentation file as the sole Git-intended change. No execution approval.**
The main reviewer reconciled the expanded W1 preflight stop on
`css-select@6.0.0` / `prepare: npm run build` with exact published metadata,
the research sidecar's owning-source review, and installed npm source.
Gate 2 remains **FAIL**, the `http-cache-semantics@4.2.0` HIGH hold continues,
and frozen pins and expiry **2026-10-12T23:59:59Z** remain unchanged. The owning
[additional-scope proposal](astro-additional-transitive-scope-proposal-20261006.md)
records those continuing constraints; this note does not reopen them.

## Boundary and source identities

Local HEAD was verified as `70f925308f3cbb2b947693fd1713e0fde616f2e2` before
writing; tree `8efe6e099cfdd6999b05c64edc063afdc1b59d80`.
The proposal was read completely. The research skill supplied a background
primary-source researcher, assigned only this note's source review and no
further delegation. Main separately inspected exact registry metadata and npm
CLI source, then filled the consolidated evidence and disposition below.

The supplied target registry gitHead is
`7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2`. Independently, the owning
[v6.0.0 tag reference](https://api.github.com/repos/fb55/css-select/git/ref/tags/v6.0.0)
points to annotated tag `3959137b578133e8e0e5b7f2700c5b923271107d`; its
[tag object](https://api.github.com/repos/fb55/css-select/git/tags/3959137b578133e8e0e5b7f2700c5b923271107d)
peels to that exact commit. The
[commit](https://github.com/fb55/css-select/commit/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2)
has tree `7cef260bd2968b31b0cc7a70cc2d2e34f1426d1f`, and its
[manifest](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/package.json)
declares version 6.0.0. This independently corroborates repository identity,
not registry bytes or publication provenance.

The owning
[v5.2.2 tag reference](https://api.github.com/repos/fb55/css-select/git/ref/tags/v5.2.2)
points to tag `64803892616fe0eef1a0eb838ec8c1d33108e58c`; its
[tag object](https://api.github.com/repos/fb55/css-select/git/tags/64803892616fe0eef1a0eb838ec8c1d33108e58c)
peels to **`93caad96c807da1d48f08166ef14cf26916b9364`**, whose
[manifest](https://github.com/fb55/css-select/blob/93caad96c807da1d48f08166ef14cf26916b9364/package.json)
declares 5.2.2. The main reviewer subsequently supplied the exact published
5.2.2 registry gitHead as that same commit and confirmed both published versions
declare `prepare: npm run build`. The source comparison therefore uses the
provided old gitHead, independently corroborated by the owning tag; it is not
an inferred tag-to-registry mapping. Main's retrieval/hash proof is recorded
below. Both css-select tag objects report unsigned verification;
tag resolution is not a signature or tarball verification.

## Lifecycle and package-layout comparison

Every declaration in this table comes from the pinned owning
[5.2.2 manifest](https://github.com/fb55/css-select/blob/93caad96c807da1d48f08166ef14cf26916b9364/package.json)
and
[6.0.0 manifest](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/package.json).

| Declaration | 5.2.2 source | 6.0.0 source |
| --- | --- | --- |
| Prepare | `npm run build` | `npm run build` |
| Build | `npm run build:cjs && npm run build:esm` | `tshy` |
| CommonJS JS / types | `lib/index.js` / `lib/index.d.ts` | `./dist/commonjs/index.js` / `./dist/commonjs/index.d.ts` |
| ESM JS | `lib/esm/index.js` | `./dist/esm/index.js` |
| Exports | import/require JS paths | root import/require each has types/default; also `./package.json` |
| Files inclusion declaration | `lib` | `dist`, `src` |
| Build tooling, dev only | TypeScript `^4.6.3` | tshy `^3.0.2`, TypeScript `^5.8.3` |
| Runtime dependencies | boolbase `^1.0.0`, css-what `^6.1.0`, domhandler `^5.0.2`, domutils `^3.0.1`, nth-check `^2.0.1` | boolbase `^1.0.0`, css-what `^7.0.0`, domhandler `^5.0.3`, domutils `^3.2.2`, nth-check `^2.1.1` |

The prepare declaration therefore predates this upgrade. The 5.2.2
[build commands](https://github.com/fb55/css-select/blob/93caad96c807da1d48f08166ef14cf26916b9364/package.json)
invoke `tsc`, interpolate `git rev-parse HEAD` into a source-map URL, then
build ESM with `--module esnext --target es2019 --outDir lib/esm` and write a
module-type package.json in that directory. These commands were read as text,
never invoked. The old
[tsconfig](https://github.com/fb55/css-select/blob/93caad96c807da1d48f08166ef14cf26916b9364/tsconfig.json)
sets ES5/CommonJS, includes `src`, emits declarations/maps, and excludes spec,
fixture, test and snapshot patterns.

For 6.0.0 the bounded declared chain is `prepare → npm run build → tshy`.
The
[manifest's tshy configuration](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/package.json)
maps `.` to `./src/index.ts`, passes through `./package.json`, and excludes
`**/*.spec.ts`, `**/__fixtures__/*`, `**/__tests__/*`,
`**/__snapshots__/*`, and `test`. It sets no custom project, dialects,
liveDev, imports or selfLink options. Test, lint, format and Vitest/Biome
commands are separate script declarations, not part of that explicit chain.
The
[6.0.0 tsconfig](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/tsconfig.json)
sets ES2020/NodeNext, declarations and source/declaration maps, strict checks,
isolated declarations, `types: ["vitest/globals"]`, and an `outDir: lib`.
The declared test exclusion does not erase that build-time type reference.

The owning source
[lockfile](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/package-lock.json)
records dev-only tshy **3.0.2** and TypeScript **5.8.3**. This is upstream
repository lock evidence, not proof of the publisher's installed tools or
the application's future resolution. tshy 3.0.2's owning
[tag object](https://api.github.com/repos/isaacs/tshy/git/tags/72595bc0229f5958099b74d5f2e60f4e2a5c49c3)
peels to `cb3a46789e375554bade4dc6c94a4b0daeb8a610`; README and manifest
retrieved at that commit matched their tag versions exactly.

The pinned
[tshy README](https://github.com/isaacs/tshy/blob/cb3a46789e375554bade4dc6c94a4b0daeb8a610/README.md#tsconfigs)
documents TypeScript compilation for both dialects, overriding include,
exclude and outDir and setting the source root to `src`. Thus `outDir: lib`
alone does not demonstrate a mismatch with the declared `dist` entries.
Its
[usage/configuration documentation](https://github.com/isaacs/tshy/blob/cb3a46789e375554bade4dc6c94a4b0daeb8a610/README.md#configuration)
describes `dist/esm` and `dist/commonjs`, export rewriting and dialect-specific
declarations. Its
[build documentation](https://github.com/isaacs/tshy/blob/cb3a46789e375554bade4dc6c94a4b0daeb8a610/README.md#atomic-builds)
also describes staging in `.tshy-build`, temporary creation/deletion of
`src/package.json`, and self-links under src/dist node_modules. This is
documented tool behavior, not executed proof or a full tshy code audit.

## Release meaning and risks supported by this source

The owning
[6.0.0 release](https://github.com/fb55/css-select/releases/tag/v6.0.0),
[release API](https://api.github.com/repos/fb55/css-select/releases/tags/v6.0.0),
published `2025-06-29T17:21:19Z`, describes a re-release of 5.2.0 and a switch
to tshy, Vitest and Biome (#1596). That supports the build-tool migration;
it does not describe exact npm tarball inventory, publisher build receipts,
or installation requirements. Its comparison starts at v5.2.1, so it is not
a substitute for the explicit v5.2.2 comparison above. A GitHub release API
lookup for v5.2.2 returned 404 in this review; its owning tag/source exists,
but no release narrative was obtained for it.

- **Artifact gap:** the
  [6.0.0 manifest](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/package.json)
  declares compiled entries and inclusion of dist/src; the
  [root tree](https://api.github.com/repos/fb55/css-select/git/trees/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2)
  has no dist directory and
  [.gitignore](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/.gitignore)
  ignores dist and tshy build directories. Repository evidence cannot prove
  those compiled files exist or match source in an npm tarball or installation.
- **Execution/build gap:** if a workflow invokes prepare, its declared next
  step is third-party build tooling, with the documented writes above. The
  [css-select manifest](https://github.com/fb55/css-select/blob/7bb0cda6593c9a69f4c9a5d2b076f26b0fe508c2/package.json)
  classifies tshy/TypeScript/Vitest as dev dependencies. Inference: rebuilding
  from source requires build inputs beyond the runtime dependency list;
  dev-only classification neither approves execution nor proves those inputs
  are installed. Main's installed CLI analysis below bounds the proposed
  scripts-disabled operation, not the safety of a future rebuild.
- **Compatibility gap:** JS and declaration paths/conditional exports change,
  and css-what crosses a major version in the pinned manifests above. Inference:
  consumer loading/type/selector compatibility requires separate evidence;
  the release's re-release description does not establish it. No consumer or
  generated artifact tests ran here, and this is no vulnerability verdict.

## Proposed declaration treatment — execution stays disabled

Record only `css-select@6.0.0`'s exact `prepare: npm run build` declaration
as **reviewed-disabled**: source review completed, lifecycle execution still
disabled, no execution approval. Published 5.2.2 already has prepare according
to the main reviewer's supplied metadata; owning manifests independently show
the same hook but different build chains. The target's tshy chain requires
separate future execution approval and evidence before it may run. This is
a proposed treatment of one known declaration, not authority to continue W1.
Retain the unexpected-lifecycle stop for **all other packages**. The main
reviewer owns the exact npm semantics, receipt and any proposed next authority.

## Exact published metadata and retained evidence

Main fetched credential-free public HTTPS metadata; no npm package operation
or lifecycle hook ran. Raw responses, local/owning npm source, helpers and
receipts remain ignored at `artifacts/css-select-lifecycle-review/run-WGvi6w/`.

| Published version | Retrieval UTC | Raw metadata SHA-256 |
| --- | --- | --- |
| [5.2.2](https://registry.npmjs.org/css-select/5.2.2) | `2026-10-06T20:29:27.105Z` | `e9a4093fba59236ce685836cb41dccead7359045386c2cace7b3801b0f3c7857` |
| [6.0.0](https://registry.npmjs.org/css-select/6.0.0) | `2026-10-06T20:29:27.131Z` | `daef5b736db033e331ec0cbd2186b8bd43cfbad1e87ddd22464a59d53c325224` |

Both published records declare the same prepare hook and the respective build
commands in the source table. Neither declares preinstall/install/postinstall,
prepack/postpack, prepublish/prepublishOnly or dependencies lifecycle scripts.
All script keys and declarations, runtime/dev dependencies, gitHead and dist
metadata remain in the receipts; neither record declares a Node engine.
The 5.2.2 declared tarball SRI matches the current locked entry; the 6.0.0 SRI
and tarball URL match the stopped W1 preflight, without replacing an audit pin.

Old declared SRI:
`sha512-TizTzUddG/xYLA3NXodFM0fSbNizXjOKhqiQQwvhlspadZokn1KDy0NZFS0wuEubIYAV5/c1/lAr0TaaFXEXzw==`.
Target declared SRI:
`sha512-rZZVSLle8v0+EY8QAkDWrKhpgt6SA5OtHsgBnsj6ZaLb5dmDVOWUDtQitd9ydxxvEjhewNudS6eTVU7uOyzvXw==`.
Exact registry tarball URL:
`https://registry.npmjs.org/css-select/-/css-select-6.0.0.tgz`.
These are declarations, not downloaded-tarball, signature or installed-byte
verification. Signatures and file counts were retained but not accepted.

Main also retained the exact owning old/new manifests and tsconfigs at the
gitHeads above. All compared name/version, script, runtime/dev dependency,
entry/type/export and tshy fields match the published records. Raw owning
manifest SHA-256 values are `cfc1e661a525ae821a00994ce4d94790b209c21b35f6e19d54e8d1c61556d303`
(5.2.2) and `05fb1dbe024994587a60fea486986a73efb65433065701c272d7c9fa27c38b15`
(6.0.0), bound by `owning-source-receipt.json`. This is still not equality
between source and compiled tarball contents.

Inspection receipt SHA-256:
`1a094c0a4d6b5da8347e817d748eb5cd5fcd7e3a85597e8b1b19f2c398c30258`.
Initial evidence inventory SHA-256:
`ae5e1cc257b66d22d1aa5bc613731e33f804ed411a019233e1b99700cf1c2164`.
The supplementary npm source receipt is separate; initial receipts/inventory
are preserved rather than overwritten. Local ignored retention is not hosted
CI retention, off-machine backup or recovery acceptance.

## Installed npm 12.0.2 — bounded lock-only execution path

Actual trusted CLI `npm --version` returned **12.0.2** on Node **v24.18.0**,
Darwin **x64**. This executed only the already installed npm version command,
not css-select, tshy, an install, a hook or a resolution. Config was sanitized:
userconfig `/dev/null`, a distinct absent globalconfig under the research
directory, and an isolated cache. The first version probe failed because
userconfig/globalconfig both pointed to `/dev/null`; that config-loading failure
is retained in the receipt and was corrected without dependency or validator
changes. No provider/runtime identity is inferred from this local CLI.

Main independently read the following local files and fetched owning
`npm/cli` **v12.0.2** copies; all six copies were byte-identical. This does not
prove all installed npm bytes or dependencies match the release.

| Owning file | SHA-256 of local and retrieved source |
| --- | --- |
| [install](https://github.com/npm/cli/blob/v12.0.2/lib/commands/install.js) | `0d90b3c7ff4e5fe28270d49feb31660002f83b7f2382838f00317f929c3b948b` |
| [Arborist reify](https://github.com/npm/cli/blob/v12.0.2/workspaces/arborist/lib/arborist/reify.js) | `d43747975102489ed4f7579e779e68c099688f16192b4f8b9599eaf647112766` |
| [Arborist rebuild](https://github.com/npm/cli/blob/v12.0.2/workspaces/arborist/lib/arborist/rebuild.js) | `115adc4a3ff6129918283e4552cb0384513ab682c8c528f360a52fc16b0b8152` |
| [allow-scripts resolution](https://github.com/npm/cli/blob/v12.0.2/lib/utils/resolve-allow-scripts.js) | `ed578216aa03fe4579885c567c488354a7ea7590441b1cb0ecd2b1353dd3f6d0` |
| [configuration definitions](https://github.com/npm/cli/blob/v12.0.2/workspaces/config/lib/definitions/definitions.js) | `cf8f31b79a4428b25e2dac5b080c3b9e0fc03dd8dea54124a0c6cf05e1526630` |
| [ideal-tree builder](https://github.com/npm/cli/blob/v12.0.2/workspaces/arborist/lib/arborist/build-ideal-tree.js) | `1b1d2df18f87bbc7c0cd4fd68d89524f95c87033c046f3b5c9fab99362039d49` |

Source-backed paths, not executed lock/install tests:

- `install` forwards flattened options to Arborist. Root preinstall and
  post-reify install/postinstall/prepublish/preprepare/prepare/postprepare run
  only when `runRootLifecycle` is true; `ignore-scripts` makes it false.
- Lock-only reify builds the complete ideal tree and returns from
  `#reifyPackages` before physical dependency installation/rebuild. Its
  root dependencies-event path separately requires scripts not be ignored.
- Dependency rebuild gates preinstall/install/postinstall on `ignoreScripts`.
  Prepare is in the link-build branch, also guarded. Thus a registry dependency
  prepare declaration is not the same execution path as a local/root/link build.
- Configuration maps `ignore-scripts` to `ignoreExtension`; the ideal-tree
  loader then returns before importing/executing a root npm extension.
  No allowScripts approval, dangerous-all-scripts flag or extension is proposed.

The [npm install documentation](https://docs.npmjs.com/cli/v12/commands/npm-install/)
distinguishes lock-only resolution and script disabling; explicit `npm run`
commands are not made safe by ignore-scripts and stay prohibited here.
[Lifecycle documentation](https://docs.npmjs.com/cli/v12/using-npm/scripts/)
distinguishes package preparation, local/link and Git workflows. The local
Pacote Git fetcher also returns before preparation when ignoreScripts is set;
it was read/hashed, not executed or compared to an owning release. The trial
remains registry-only, not authority for Git/folder dependencies.

**Inference:** the exact inspected CLI path supports retaining this declaration
in a scripts-disabled, registry-only lock resolution without executing it.
That is narrower than proving the hook safe, an installed package complete,
the resolver correct under every input, or a provider runtime acceptable.
The existing lifecycle scope stop is not waived by this inference.

## Proposed scope amendment and next authority

Request Nathan's approval to recognize **only css-select 6.0.0**, with the exact
target SRI/tarball above, `prepare: npm run build` and `build: tshy`, as a
**reviewed-but-disabled declaration for the existing isolated W1 trial**.
This is not an audit allowance or permission to execute prepare/build/tshy.
No dependency version, direct transitive declaration, override or frozen pin
changes beyond the existing approved scope are proposed.

After approval, the trial may resume from a fresh genuine isolated checkout of
the then-current exact source SHA. Keep Node 24.18.0 / inspected npm 12.0.2,
sanitized environment/config/cache and registry-only metadata. Recheck tooling
if its version or inspected source hashes changed. The bounded operation is
`npm install --package-lock-only --ignore-scripts --include=prod --include=dev
--include=optional --include=peer --strict-peer-deps --audit=false --fund=false
--fetch-retries=0 --fetch-timeout=20000`, in the isolated web directory, using
the public registry and only the previously approved exact seed identities.
This command has **not run**. `audit=false` here avoids treating npm's optional
install-time quick report as acceptance; it does not disable the mandatory
subsequent unchanged complete `scripts/npm-audit-web-ci.js` guard.

Preserve css-select's real script metadata in the receipt, not in a fabricated
lock script field. Do not add tshy, TypeScript or Vitest to the application tree
to rebuild a transitive package. Retain all optional/native/WASM and compatible
unchanged/nested entries, optional absent Markdown peer, cache 4.2.0 and bounded
conditional orphan review. Enumerate every actual lock delta and consumer edge.
Stop on any other unreviewed hook, changed reviewed declaration/integrity,
unexplained churn, new Git/folder/extension path or HIGH/CRITICAL. No general
hook exemption, validator change, installation, execution, workspace application,
build, pin update, push, provider change or deployment is included. Stop after
the actual diff/audit evidence; cache remains an independent HIGH blocker.

This note resolves the research gap only. It is **proposed, not approved**;
W1 remains stopped until Nathan's specific scope decision. No gate passes here.

## Local verification

This review used public-source fetches, local Git/text/hash reads, and
`apply_patch` for this Git-intended file and ignored evidence helpers.
No dependency/config edits, install, resolution, proposed dependency scripts/code,
build, consumer tests, audit, push or provider writes
were performed. Baseline was a clean tracked tree plus five existing untracked
notes. PASS: HEAD unchanged; status adds only this note to the original five
untracked notes; tracked/staged diffs remain empty; note whitespace check
passes; root/web manifest, lock and scope-proposal SHA-256 values match their
before-write values. This documentation-only verification cannot count as W1,
package or launch acceptance. Gate 2 **FAIL**,
cache HIGH hold, frozen pins and **2026-10-12T23:59:59Z** expiry continue.
