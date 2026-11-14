# Additional Astro transitive compatibility review — 2026-10-06

For Nathan. **Source/metadata review only; compatibility acceptance remains pending.**
Reviewed Peso HEAD `dd20508717af1c8a0041a200642aa1e0f11a4219`, tree
`a1129112546d7292ba373c5006ce26192ac3bd10`. No dependency edit, package
installation/execution, PoC, build, new audit, Git mutation or provider mutation
was performed. This note does not approve pins or installed/native bytes.
**Undici 8.0.0 is REJECTED, including as a trial target. Undici 8.10.2 is
proposed only after the retained identity/range/engine checks below.**
**Gate 2 remains FAIL; cache 4.2.0 remains an unresolved HIGH; Forge prebuilt
bundle hold and cutoff 2026-10-12T23:59:59Z remain unchanged.**

The existing [W1 checkpoint](/Users/nathan/.codex/state/plugins/codex-security/scans/peso-app/artifacts-19ef6278944bd097b40d1b822067912bdc2a0b6eb71d87747c09118a5f2e0aae/artifacts/w1-20261006-dd20508/checkpoint.md)
supplies the before-state and holds. The main investigator owns the
[graph proposal](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/graph-proposal.json),
observed `2026-10-06T19:37:16.099Z`: 29 proposed identities including Astro,
with platform variants and wasm-runtime 1.2.3. Its original Undici 8.0.0 seed is
superseded by main's [revised Undici proposal](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/undici-revised-proposal.json).
This sidecar read retained attribution, engine, hook, advisory and release
records; it did not repeat registry or advisory queries. Main owns the revised
exact scope proposal. Identity/range
closure does not establish npm lock layout, signatures, artifact contents or
native loading. Risk assessments and future checks below are recommendations,
not test results or claims of runtime non-reachability.

## Owning source identities

Public primary sources were read on **2026-10-06**. Dates below distinguish
GitHub release publication from commit/tag timestamps; none is asserted to be
an npm publication timestamp. Astro callers were reviewed at the Astro tag
commit, while separately published packages have their own release commits.

| Scope / owning repository | Exact source attribution and date |
| --- | --- |
| Astro 7.2.8 / withastro/astro | Annotated [tag object](https://api.github.com/repos/withastro/astro/git/tags/e631a341ce62a596143c5e711f48e42bfbdd1611) peels to `7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d`; tag timestamp `2026-08-26T20:59:50Z`. |
| compiler-rs/binding 0.4.0 / withastro/compiler-rs | compiler-rs [tag object](https://api.github.com/repos/withastro/compiler-rs/git/tags/b6e2fe88d83d2b22fa271bcf29d197fe5b50f3c7) peels to `e8364c186182ab0ec669156ff526d4596d2fc329`; [release](https://api.github.com/repos/withastro/compiler-rs/releases/tags/%40astrojs%2Fcompiler-rs%400.4.0) published `2026-08-10T22:45:40Z`. Binding [manifest](https://github.com/withastro/compiler-rs/blob/e8364c186182ab0ec669156ff526d4596d2fc329/crates/astro_napi/package.json) is 0.4.0 at that commit; WASI metadata gitHead agrees. |
| markdown-satteri 0.3.8 / withastro/astro | [Tag object](https://api.github.com/repos/withastro/astro/git/tags/1f93360430b278ce648a345a7a2f544307421995) peels to `d38ed60390abfc9087a0cbfce99b9a4893229de5`; [release](https://api.github.com/repos/withastro/astro/releases/tags/%40astrojs%2Fmarkdown-satteri%400.3.8) published `2026-08-24T14:57:40Z`. |
| internal-helpers 0.10.4 / withastro/astro | [Tag object](https://api.github.com/repos/withastro/astro/git/tags/eeef0bee017b8c20e6e2e2c5891a0ff6f598298a) peels to `8a31cba625a23d886614172e1d3b02b8eb896a18`; [release](https://api.github.com/repos/withastro/astro/releases/tags/%40astrojs%2Finternal-helpers%400.10.4) published `2026-08-19T14:38:53Z`. |
| satteri 0.10.3 / bruits/satteri | [Tags](https://api.github.com/repos/bruits/satteri/tags?per_page=100) identify `satteri-v0.10.3` at `5df21fc0cead783853a8959c641d9c241d0037b6` and old 0.9.5 at `92d01ec4eee3a7284608f5a4974dca6d4aec836e`; [release](https://api.github.com/repos/bruits/satteri/releases/tags/satteri-v0.10.3) published `2026-08-19T00:47:49Z`. WASI metadata gitHead agrees. |
| diff 9.0.0 / kpdecker/jsdiff | [Tag](https://api.github.com/repos/kpdecker/jsdiff/git/ref/tags/v9.0.0) is `ed13aca03aa25735fafc0645d1185e7a1c68fd8c`, [commit](https://api.github.com/repos/kpdecker/jsdiff/commits/ed13aca03aa25735fafc0645d1185e7a1c68fd8c) dated `2026-04-13T12:41:14Z`. Registry gitHead instead names `db0b12ace208da7fd741cf96d97f009347a9eaa8`, [dated](https://api.github.com/repos/kpdecker/jsdiff/commits/db0b12ace208da7fd741cf96d97f009347a9eaa8) `2026-04-13T12:36:37Z`. |
| unifont 0.7.5 / unjs/unifont | [Tag](https://api.github.com/repos/unjs/unifont/git/ref/tags/v0.7.5) is `874be153ef772c4f3b2dbaa96e676c4fb57c82c8`; [release](https://api.github.com/repos/unjs/unifont/releases/tags/v0.7.5) published `2026-08-11T10:42:46Z`. |
| undici 8.0.0 / nodejs/undici — **REJECTED; historical comparison only** | [Tag](https://api.github.com/repos/nodejs/undici/git/ref/tags/v8.0.0) and receipt gitHead agree on `d7fbba51772deecb830a297647456a5e9f9fec57`; [release](https://api.github.com/repos/nodejs/undici/releases/tags/v8.0.0) published `2026-04-02T09:11:33Z`. |
| undici 8.10.2 / nodejs/undici — **PROPOSED ONLY** | Main's retained [registry record](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/undici-8.10.2-registry.json) gitHead and [owning release record](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/undici-8.10.2-release.json) target_commitish agree on `5e541e0b9df7563e5766bbd469fbfe383d9ae6ca`; [release](https://github.com/nodejs/undici/releases/tag/v8.10.2) published `2026-09-04T13:56:45Z`. Source samples below use that exact commit; no independent tag peeling or artifact verification was performed. |
| find-proc 0.1.0 / gameroman-npm/find-proc | Receipt gitHead is [commit](https://api.github.com/repos/gameroman-npm/find-proc/commits/6d4397ee85907954f4eb64da0ea90aa3532d7fa7) `6d4397ee85907954f4eb64da0ea90aa3532d7fa7`, dated `2026-08-21T22:40:45Z`, with release v0.1.0 commit message. This is not yibn2008/find-process. |
| @napi-rs/wasm-runtime 1.2.3 / napi-rs/napi-rs, wasm-runtime | Receipt gitHead is [release commit](https://api.github.com/repos/napi-rs/napi-rs/commits/70c149321ca4e361f6726349cf9b2258467fb24f) `70c149321ca4e361f6726349cf9b2258467fb24f`, dated `2026-08-12T03:30:38Z`. |

**Attribution limitations:** a release tag, repository field or gitHead does not
prove a published tarball was built from that source. Workspace manifests and
generated loaders can differ from publication output. The diff comparison is
explicitly [diverged](https://api.github.com/repos/kpdecker/jsdiff/compare/db0b12ace208da7fd741cf96d97f009347a9eaa8...ed13aca03aa25735fafc0645d1185e7a1c68fd8c);
the returned changes concern version/release-note files, but this is not a
tarball equivalence proof. Do not silently substitute the tag for npm gitHead.
The jsdiff release API returned 404 while the tag page and source notes were
readable. Failed initial sandbox HTTPS reads were retried as authorized public
read-only requests. No retrieved package code was executed.

## Caller and behavior review

### Compiler 0.3.2 → 0.4.0

The owner documents added parse comments, changed parse positions from UTF-8
bytes to UTF-16 offsets, and preservation of other attributes on scripts using
`define:vars`. These are observable API/output changes. [Compiler release](https://github.com/withastro/compiler-rs/releases/tag/%40astrojs/compiler-rs%400.4.0).
Astro's compile caller invokes `preprocessStyles` and synchronous `transform`,
requests source maps and translates diagnostics; the wrapper invokes
`compileAstroSync` and separately exposes `parseAstroSync`. [Astro caller](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/src/core/compile/compile.ts),
[compiler wrapper](https://github.com/withastro/compiler-rs/blob/e8364c186182ab0ec669156ff526d4596d2fc329/packages/compiler/src/index.ts).

**Assessment:** meaningful build/compiler risk; a successful import is
insufficient. Later checks should compare emitted HTML, script attributes,
CSS and diagnostics/source positions using ASCII, accented characters and
astral characters. Include `<script define:vars>` with `nonce`, `id` and
`data-astro-rerun`; assert the intended attribute preservation explicitly.

### Markdown wrapper 0.3.5 → 0.3.8; Sätteri 0.9.5 → 0.10.3

The intervening wrapper releases update shared helpers and Sätteri; 0.3.8
broadens plugin option types and corrects the smart-punctuation default tooltip.
[Wrapper changelog at Astro commit](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/markdown/satteri/CHANGELOG.md).
Its renderer lazily imports Sätteri, collects images after user MDAST plugins,
runs highlighting/user HAST/image/headings passes, and calls `markdownToHtml`
with GFM and smart punctuation enabled unless disabled. Prism conversion now
uses Sätteri's `htmlToHast(..., { fragment: true })`.
[Renderer source](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/markdown/satteri/src/satteri-processor.ts).

Sätteri 0.10 freezes visitor nodes, requires context methods for mutation, makes
visitor positions opt-in, accepts nested/factory/skip plugin entries and adds
raw-HTML reparsing. It also changes footnote IDs/links for Unicode and punctuation
and adds a footnote clobber prefix option. [Owner changelog at 0.10.3](https://github.com/bruits/satteri/blob/5df21fc0cead783853a8959c641d9c241d0037b6/packages/satteri/CHANGELOG.md).

**Assessment:** substantial ordinary plugin compatibility risk despite the
wrapper patch version. Later fixtures should cover context-based edits,
rejection of direct mutation, position opt-in, mixed sync/async plugins,
headings, image URL rewrites, raw HTML and Unicode footnotes. The Prism/HTML
parser replacement needs a fragment fixture if that mode is in trial scope.
Peso's inspected `web/astro.config.mjs` has static output without Markdown
customization, and no `.md`/`.mdx` files were found under `web/src`; these source
observations bound the initial fixture set, not package exposure or acceptance.

### Shared helpers 0.10.2 → 0.10.4

0.10.3 fixes incremental cache invalidation caused by Shiki mutating language
aliases; 0.10.4 adds path-segment-aware request-base stripping.
[Helper changelog](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/internal-helpers/CHANGELOG.md).
The highlighter clones `langAlias` before handing it to Shiki.
[Highlighter](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/internal-helpers/src/shiki.ts).
`stripRequestBase` collapses leading slashes and strips only the base itself or
its slash-delimited descendants; the older `removeBase` export still exists.
Astro routing adopts the new helper. [Path helper](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/internal-helpers/src/path.ts),
[routing caller](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/src/core/routing/match-request.ts).

**Assessment:** bounded routing/highlighting risk. Later tests should distinguish
`/docs`, `/docs/page`, `/docs-archive/page` and duplicate leading slashes, and
verify aliases/configuration remain stable across repeated renders.

### diff 8.0.4 → 9.0.0

Version 9 drops ES5 support and changes patch parsing/formatting, including
quoted filenames, Git headers, unpaired-header rejection and optional filename
types. Its `parsePatch` uses `TextDecoder`/typed arrays despite the broad legacy
Node engine declaration in the receipt. [Owner release notes](https://github.com/kpdecker/jsdiff/blob/ed13aca03aa25735fafc0645d1185e7a1c68fd8c/release-notes.md).
The inspected Astro caller imports `diffWords` to format proposed integration
configuration changes for `astro add`. [CLI caller](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/src/cli/add/index.ts).

**Assessment:** focused CLI presentation risk for this caller; patch API changes
must not be attributed to `diffWords` without evidence. Later exercise the
configuration preview with whitespace and Unicode, at accepted package bytes;
resolve the gitHead/tag discrepancy when accepting artifacts.

### unifont 0.7.4 → 0.7.5; Undici 8.0.0 rejected, 8.10.2 proposed

The old fetch wrapper calls ofetch and retries caught failures; 0.7.5 uses global
`fetch`, rejects non-success responses and skips retries for 4xx other than 429,
while retaining retries for other failures. [Old wrapper](https://github.com/unjs/unifont/blob/v0.7.4/src/fetch.ts),
[new wrapper](https://github.com/unjs/unifont/blob/874be153ef772c4f3b2dbaa96e676c4fb57c82c8/src/fetch.ts).
`createUnifont` now awaits proxy setup; with a proxy environment variable, that
setup dynamically imports Undici and may install `EnvHttpProxyAgent` as a
global dispatcher when the existing dispatcher passes its Agent check. Setup
errors are swallowed. [Factory](https://github.com/unjs/unifont/blob/874be153ef772c4f3b2dbaa96e676c4fb57c82c8/src/unifont.ts),
[proxy source](https://github.com/unjs/unifont/blob/874be153ef772c4f3b2dbaa96e676c4fb57c82c8/src/proxy.ts).

The release also changes font fallbacks, variable weights and provider behavior.
[Unifont release](https://github.com/unjs/unifont/releases/tag/v0.7.5).
Astro's font resolver calls `createUnifont` with `throwOnError: false` and extracts
the returned fonts. [Astro font caller](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/src/assets/fonts/infra/unifont-font-resolver.ts).
Undici 8 changes dispatcher compatibility, enables HTTP/2 by default and drops
non-real Blob support; this is relevant when its dispatcher is actually used,
not proof that unifont replaces global fetch with Undici's exported fetch.
[Historical Undici 8.0.0 release](https://github.com/nodejs/undici/releases/tag/v8.0.0).
That release is retained for behavior comparison and is not an eligible trial.

**Assessment:** meaningful transport/global-state risk. Later use controlled
HTTP fixtures for success, 404, 429, 5xx, failed response decoding and retry
limits; inspect resolved CSS/weights/fallbacks. Test no-proxy, configured proxy
and pre-existing custom dispatcher in separate processes. Peso currently imports
local `@fontsource` CSS in `web/src/layouts/base-layout.astro`; this does not prove
all transitive font initialization is absent. Retain ofetch wherever another
parent still needs it, as recorded by the main graph owner.

### Supplemental Undici rejection and bounded 8.10.2 review

Main's retained [8.0.0 advisory check](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/undici-advisory-check.json),
observed `2026-10-06T19:46:52.876Z`, contains **22 matches, including seven HIGH**.
For example, the owning HIGH advisories for dropped TLS options in BalancedPool
and unrequested WebSocket subprotocols both include 8.0.0 and name 8.10.2 as
patched. [TLS advisory](https://github.com/nodejs/undici/security/advisories/GHSA-w293-vg96-wgc3),
[WebSocket advisory](https://github.com/nodejs/undici/security/advisories/GHSA-rfgv-xxqx-mfg5).
**Reject 8.0.0; fitting a dependency range or Node engine does not permit it.**
No consumer non-reachability claim or exception is proposed.

Main's revised receipt identifies exact **8.10.2**, fetched
`2026-10-06T19:47:39.751Z`. It fits unifont's `^8.0.0`, retains Node ≥22.19.0
(Node 24.18.0 fits), declares no dependency/optional/peer edges, and retains the
same unapproved `prepare` hook. [Published version record](https://registry.npmjs.org/undici/8.10.2),
[retained parent/version/check evidence](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/undici-revised-proposal.json),
[parent graph receipt](/Users/nathan/Downloads/peso-app/artifacts/astro-transitive-proposal/run-mPSuiH/graph-proposal.json).
Its advisory query at `2026-10-06T19:47:40.059Z` returned zero matches. This is
a dated published-advisory observation, **not a complete npm audit, verified
tarball, clean install or approval**.

The owning 8.10.2 release tightens cache/interceptor origin identities and
safe-method/cookie handling; preserves TLS callbacks; rejects malformed
WebSocket handshakes; bounds decompression; and turns terminal retry/body and
invalid resumed-response conditions into explicit errors. It also fixes
iterable proxy authorization headers, connection timeouts and fetch header
behavior. These change rejection, caching, transport and error semantics.
[Owning release retained by main](https://github.com/nodejs/undici/releases/tag/v8.10.2).
Interceptor limits and WebSocket changes are conditional paths; they do not
establish that unifont's global fetch enables those APIs.

Selected exact endpoint source comparisons add caller-relevant detail beyond
the latest patch's release notes:

- **Proxy environment parsing:** 8.0.0 prepends schemes to scheme-less proxy
  values; 8.10.2 passes them directly to ProxyAgent's URL parser. New
  `NO_PROXY` matching normalizes trailing dots and IPv6 brackets/ports.
  [Old environment agent](https://github.com/nodejs/undici/blob/d7fbba51772deecb830a297647456a5e9f9fec57/lib/dispatcher/env-http-proxy-agent.js),
  [new environment agent](https://github.com/nodejs/undici/blob/5e541e0b9df7563e5766bbd469fbfe383d9ae6ca/lib/dispatcher/env-http-proxy-agent.js),
  [new URL parser](https://github.com/nodejs/undici/blob/5e541e0b9df7563e5766bbd469fbfe383d9ae6ca/lib/dispatcher/proxy-agent.js).
  **Inference to verify:** a scheme-less value such as `proxy.example:8080`
  may fail setup, and unifont's swallowed setup error may leave the intended
  proxy unused. [Unifont catch boundary](https://github.com/unjs/unifont/blob/874be153ef772c4f3b2dbaa96e676c4fb57c82c8/src/proxy.ts).
- **Proxy requests:** the new source materializes iterable headers for the
  Proxy-Authorization guard, passes connection timeouts into connector paths,
  and permits forwarding HTTP requests through HTTPS proxies when tunneling
  is not requested. [Old ProxyAgent](https://github.com/nodejs/undici/blob/d7fbba51772deecb830a297647456a5e9f9fec57/lib/dispatcher/proxy-agent.js),
  [new ProxyAgent](https://github.com/nodejs/undici/blob/5e541e0b9df7563e5766bbd469fbfe383d9ae6ca/lib/dispatcher/proxy-agent.js).
  The new global source retains dispatcher v2 and the legacy wrapper bridge;
  actual interoperability with Node's bundled fetch remains untested.
  [Global dispatcher source](https://github.com/nodejs/undici/blob/5e541e0b9df7563e5766bbd469fbfe383d9ae6ca/lib/global.js).

**Limited review and later test boundary:** this samples transport sources at
8.0.0 and 8.10.2 and reads the retained 8.10.2 release; it is not an exhaustive
review of every intervening minor release. After separate approval, extend the
existing font/proxy fixtures with explicit/scheme-less URLs, case precedence,
IPv6/port/trailing-dot `NO_PROXY`, HTTP/HTTPS forwarding versus CONNECT,
timeout/error completion and preserved custom dispatchers. Use isolated
processes and controlled endpoints, and verify proxy setup errors are observable.
Add SOCKS/TLS, interceptor/retry/decompression or WebSocket controls only where
the accepted consumer enables those paths. Preserve full dependency audit
coverage regardless of which consumer fixtures apply. Generated/published
bytes, signatures, bundled-fetch behavior, provider runtime and all execution
results remain unknown. **8.10.2 remains proposed only; all checks above are
NOT RUN here.**

### New find-proc 0.1.0

Astro's dev/preview lockfile logic now queries the recorded PID's command,
checks an Astro CLI pattern and rejects its own PID. Lookup failure or an
undefined command preserves the prior PID-only liveness behavior.
[Astro lockfile caller](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/src/core/dev/lockfile.ts).
The owning implementation validates numeric PID input, shells out to `ps` on
macOS/Linux, and spawns PowerShell/CIM on Windows. Its shell helper has a 2 MB
output buffer. [Public API](https://github.com/gameroman-npm/find-proc/blob/6d4397ee85907954f4eb64da0ea90aa3532d7fa7/src/find.ts),
[platform source](https://github.com/gameroman-npm/find-proc/blob/6d4397ee85907954f4eb64da0ea90aa3532d7fa7/src/find_process.ts),
[shell helper](https://github.com/gameroman-npm/find-proc/blob/6d4397ee85907954f4eb64da0ea90aa3532d7fa7/src/utils.ts).

**Assessment:** process identity and portability risk. Later use the injected
lookup seam for dead/live/reused/self PIDs, non-Astro commands, undefined
commands and lookup rejection. Test command parsing for supported platforms;
real lifecycle checks must use disposable child processes, never unrelated
user processes. A static build pass would not cover dev/preview behavior.

## Node floors, native/WASM and runtime 1.2.2 → 1.2.3

Astro/compiler wrapper require Node ≥22.12.0; binding allows
`^20.19.0 || >=22.12.0`. Undici raises the proposed graph floor to **≥22.19.0**;
wasm-runtime accepts `^20.19.0 || ^22.13.0 || >=23.5.0`.
[Astro manifest](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/package.json),
[compiler manifest](https://github.com/withastro/compiler-rs/blob/e8364c186182ab0ec669156ff526d4596d2fc329/packages/compiler/package.json),
[binding manifest](https://github.com/withastro/compiler-rs/blob/e8364c186182ab0ec669156ff526d4596d2fc329/crates/astro_napi/package.json),
[Proposed Undici 8.10.2 manifest](https://github.com/nodejs/undici/blob/5e541e0b9df7563e5766bbd469fbfe383d9ae6ca/package.json),
[runtime manifest](https://github.com/napi-rs/napi-rs/blob/70c149321ca4e361f6726349cf9b2258467fb24f/wasm-runtime/package.json).
Main's original receipt and revised Undici evidence report engines accepting
Node 24.18.0. The 8.0.0 engine observation is historical and does not restore
its eligibility. This is
declarative compatibility, not execution evidence. Tracked marketing Security
CI selects Node 24; a generic Node 22 setting or Astro's minimum alone is
insufficient evidence for an actual host. Record exact host patch versions later.
Undici's receipt declares `prepare: husky && node ./scripts/platform-shell.js`;
it was neither executed nor approved. Source build scripts are not an install
result or authority to run lifecycle hooks.

Both owning manifests list macOS/Windows x64 and arm64, Linux x64/arm64 GNU and
musl, and threaded WASI targets. [Compiler targets](https://github.com/withastro/compiler-rs/blob/e8364c186182ab0ec669156ff526d4596d2fc329/crates/astro_napi/package.json),
[Sätteri targets](https://github.com/bruits/satteri/blob/5df21fc0cead783853a8959c641d9c241d0037b6/packages/satteri/package.json).
Generated loaders choose by OS/architecture/libc, attempt native loading then
WASI, and recognize force-WASI settings. Compiler's tagged loader contains a
stale `0.2.3` literal in opt-in version checks. **Unknown:** whether publication
regenerated that loader. Inspect actual accepted loader bytes before calling
this a published defect. [Compiler loader](https://github.com/withastro/compiler-rs/blob/e8364c186182ab0ec669156ff526d4596d2fc329/crates/astro_napi/index.js),
[Sätteri loader](https://github.com/bruits/satteri/blob/5df21fc0cead783853a8959c641d9c241d0037b6/packages/satteri/index.js).

Sätteri's WASI caller imports runtime instantiation/context/filesystem helpers,
uses Node WASI and worker threads, and manipulates worker references; a native
pass cannot accept this path. [WASI caller](https://github.com/bruits/satteri/blob/5df21fc0cead783853a8959c641d9c241d0037b6/packages/satteri/satteri_napi.wasi.cjs).
Runtime 1.2.3's owning release commit lists emnapi v1/v2 compatibility and an
alpha dependency update. Its source comparison also changes peer ranges and
the generated-artifact build pipeline from Rollup to Rolldown.
[Release commit](https://github.com/napi-rs/napi-rs/commit/70c149321ca4e361f6726349cf9b2258467fb24f),
[source comparison](https://github.com/napi-rs/napi-rs/compare/%40napi-rs%2Fwasm-runtime%401.2.2...%40napi-rs%2Fwasm-runtime%401.2.3).
The runtime exports emnapi instantiation and plugin APIs plus filesystem proxy
helpers. [Runtime source](https://github.com/napi-rs/napi-rs/blob/70c149321ca4e361f6726349cf9b2258467fb24f/wasm-runtime/runtime.js).

**Assessment:** require matching native/WASI package bytes and actual generated
runtime/loader inspection, including existing emnapi peer resolution. After
approval, cover native macOS arm64 and the actual Linux CI/deploy architecture
and libc, plus forced WASI import/compile/render, workers and clean process exit.
Windows/musl claims need their own platform evidence if included. Do not infer
portability from the optional package list or a permissive WASI engine field.

## Removed edges and bounded acceptance handoff

Astro removes `@rollup/pluginutils`'s `dataToEsm` use in the content virtual
module, validates JSON and emits `JSON.parse` for regular stores; it also adds
incremental metadata. [Exact old/new content-source comparison](https://api.github.com/repos/withastro/astro/compare/astro%407.1.6...astro%407.2.8),
[target source](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/src/content/vite-plugin-content-virtual-mod.ts).
This deserves small/large/Unicode/corrupt store and incremental rebuild fixtures
if the content path is in acceptance scope. Edge removal does not authorize
pruning packages needed by other parents.

Astro's Markdown peer remains optional in the target source manifest; main's
published metadata receipt supplies exact declaration 7.2.4. Preserve its
current absence. [Optional peer source](https://github.com/withastro/astro/blob/7cadf1055a61c85d0b05f3c7d8c709f7faa5cf0d/packages/astro/package.json).
Do not install it merely to satisfy a declaration change or fill a test fixture.

Future acceptance requires a separately approved isolated candidate: reconcile
the exact lock delta with main's identities/edges; verify artifact provenance,
contents and hooks; retain the unchanged complete web audit and stop on new
churn or HIGH/CRITICAL; run only the relevant bounded seams above and the Peso
marketing output checks. Each result must identify exact source, inputs,
installed package bytes and platform. No unknown pin, lifecycle/native
execution, cache treatment or Forge prebuild acceptance is authorized by this
research. All such verification remains **NOT RUN**.
