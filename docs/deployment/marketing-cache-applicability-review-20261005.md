# Marketing cache applicability review — 2026-10-05

For Nathan, within the authorized Stage A research boundary. **Keep the raw
http-cache-semantics HIGH blocker unresolved.** The reviewed Astro consumer does
not call the advisory's stale-request evaluation methods, but this is bounded
source/fixture evidence, not generated-artifact exclusion or runtime acceptance.
4.3.0 reproduces the two principal library cases below; neither its version
number nor a future green audit establishes a fix. No cache upgrade, advisory
exception, scope-pin change, provider action, commit or push is authorized or
performed by this review. [Proposal][P] [Advisory][U1] [Experiments](#bounded-private-experiments)

## Evidence identity and limits

Read-only observations began at local HEAD
`3ad4c2a52389849077e8df1458ea5daee3f84ae7`; primary-source retrieval and fixtures
occurred on 2026-10-05 America/New_York / 2026-10-06 UTC (clock checkpoint
`2026-10-06 02:05:16 UTC`). The existing review supplies historical context;
its older HEAD is not substituted for this review's source identity. Concurrent
main-agent guard work is outside this document's write set. These are dated
observations of local files and live upstream data, not retained hosted evidence.
[Prior review][P0] [Proposal][P] [Local lock][L1]

The preserved before-state audit was read without rerunning or modifying it:
`/private/tmp/peso-marketing-audit.tAAcB5/npm-audit.json`, SHA-256
`1d19ca0390c2859f076fb73bcb27e5899559c64d7bab9c7c1eb2ed19aae03a35`.
Its cache entry has `severity: high`, `isDirect: false`, cause/source `1240991`,
GHSA-ch52-4w7c-c8xp, `range: <=4.2.0`, node
`node_modules/http-cache-semantics`, and `fixAvailable: true`. This last field
does not identify a verified security patch. The current official GHSA still
lists HIGH, affected `<=4.2.0`, and patched versions **None**. The saved report
uses CVSS 3.1/7.5; the live GHSA uses CVSS 4.0/8.7. Preserve the raw report rather
than rewriting it to match newer metadata. [Saved audit][E0] [Advisory][U1]

The locked parent-edge enumeration across `dependencies`,
`optionalDependencies`, and `peerDependencies` found one cache edge:
`web` → Astro **7.1.6** → http-cache-semantics **4.2.0**, Astro range `^4.2.0`.
The installed package versions match those lock entries. This enumerates this
lockfile; it does not inventory external build tools or provider dependencies.
[Marketing manifest][L0] [Local lock][L1] [Installed Astro manifest][L2]

| Bound input / retrieved member | SHA-256 |
| --- | --- |
| `web/package.json` | `91ef9fa6dd1231e9331627ea48a621bbf6b798443747503a407b2d68cb543137` |
| `web/package-lock.json` | `af4b8931f67be644bbe14c5cf73600d1d9e44e43e6dc171486169c7d01f3ab91` |
| `web/astro.config.mjs` | `d601f020140925b5775b8c053b05197ecafc6381cc89bb09c86f189d60a97423` |
| cache 4.2.0 `package/index.js` | `01b7d66c854b2fe53ac05c98feb6e0d64722ab8898a778e2d2426a8b468d178f` |
| cache 4.3.0 `package/index.js` (memory only) | `ede1cc404a492fa348eb9d97a3007a0d72aa717bd22cd86a56bd0824c19729ca` |
| Astro 7.1.6 `dist/assets/build/remote.js` | `f373fa76e3112446db327c79b34e2bbb1ef1dcad41affb60788adf30edc9588e` |
| Astro 7.1.6 `dist/assets/build/generate.js` | `f46f0f1cdba218a2c42a562a20400f21334053db8a58fe16068246aad72b2a3a` |
| Astro 7.1.6 `dist/core/build/generate.js` | `e374ca3981ddf495a9d1b9c1fd6c306b246aab980cea8bb3b401f99abc236c0d` |
| Astro 7.1.6 `dist/assets/utils/redirectValidation.js` | `1c142b4b5042e87fa644a75245af8e8938ea2fd8d8bbfd28180f8ffdccefa688` |

Hash evidence comes from direct local reads and in-memory official tarball
member comparisons. Both cache tarballs' computed SHA-512 SRI matched registry
metadata; 4.2.0 also matched the lock's SRI and installed `index.js`. Astro's
tarball SRI matched its lock entry, and all four members above matched installed
bytes. These checks bind the inspected implementations, not all installed files.
[Local lock][L1] [Cache registry 4.2.0][U2] [Cache registry 4.3.0][U3] [Astro registry][U4]

Cache 4.2.0 registry `gitHead` is
`83810982b8f8996b101ed761548ea7e87a9132ea`; its raw GitHub `index.js` URL returned
404 during this review. Therefore the exact locked implementation is anchored
to the integrity-verified npm tarball, not that unavailable Git object. The
advisory-linked source at `f01112e954b83cfa8765b633ba880e5e980aa54c/index.js`,
fetched directly, matched the 4.2.0 member's SHA-256 above. 4.3.0 registry
`gitHead` is `b1d4bd682fbab0252985de45219f4e7497c0067c`; its fetched raw source
matched the verified 4.3.0 member. [Registry 4.2.0][U2] [Unavailable Git object][U5]
[Advisory source][U6] [Registry 4.3.0][U3] [Candidate source][U7]

## Advisory, dispute, and exact locked branch

The official GHSA describes cross-user disclosure when a shared cache retains
zero-lifetime responses and accepts client `max-stale`. The original report
names Set-Cookie and proxy-revalidate; its version wording (`<=4.1.1`) differs
from the GHSA's `<=4.2.0`. This review tests the actual locked bytes rather than
assuming either description proves Peso's exposure. [Advisory][U1] [Report][U8]

Owner `kornelski` disputed the report in comment `5975759591`, created
`2026-10-04T02:24:46Z`, arguing that freshness does not prevent sharing and that
private responses need `Cache-Control: private`. RFC 9111 §7.3 permits caching
Set-Cookie responses; §5.2.2.7 prohibits storing an unqualified private response
in a shared cache. Separately, §5.2.2.8 requires origin validation before a
shared cache reuses a stale proxy-revalidate response. Thus the cookie argument
does not by itself resolve the proxy-revalidate branch. This is an inference
from the cited standard and observed behavior, not a maintainer patch claim.
[Owner comment][U9] [RFC cookies][R1] [RFC private][R2] [RFC proxy-revalidate][R3]

In verified 4.2.0: shared mode defaults on (line 192); `storable()` rejects
private/no-store responses (262–295). `satisfiesWithoutRevalidation()` delegates
to `evaluateRequest()` (330–332). That method rejects must-revalidate and request
no-cache, checks URL/method/host/Vary, then accepts suitable `max-stale` on its
stale branch (394–442). `maxAge()` returns zero for shared Set-Cookie without
public **or immutable**, response no-cache, and shared proxy-revalidate
(599–626). A hit returns `responseHeaders()`, whose normal filtering preserves
Set-Cookie (339–346, 507–556). These facts explain the synthetic results below;
they do not supply a deployed shared-cache consumer. [Exact installed source][L3]
[Verified advisory source][U6]

The 4.3.0 tarball still has the max-stale branch at 429–434 and the cited
cookie/proxy lifetime branches at 628–646. Its expired cookie and proxy fixtures
still return hits. Accordingly **4.3.0 is not a verified fix for these behaviors**;
it was fetched only into memory and never installed. [Candidate source][U7]
[Registry 4.3.0][U3] [Experiments](#bounded-private-experiments)

## Actual web consumer trace

The observed executable import in the installed web tree is
`astro/dist/assets/build/remote.js:1`. Searching the supplied installed tree for
the package name and the two evaluation-method names located that import and
library/docs/manifest occurrences. This is a bounded textual search, not proof
against dynamic consumers or generated imports. [Remote-image consumer][L4]
[Installed source][L3] [Installed Astro manifest][L2]

The traced path is:

`Astro core build generation` → `static image list` → `generateImagesForPath`
→ remote `loadImage` → `loadRemoteImage` / expired-validator
`revalidateRemoteImage` → `new CachePolicy` → `storable()` / `timeToLive()`.
Core generation iterates registered static images; it does not establish that
any remote image is registered in an actual Peso build. [Core generator][L6]
[Asset generator][L5] [Remote-image consumer][L4]

| Boundary | Observed behavior | Primary evidence |
| --- | --- | --- |
| Initial fetch | Constructs a URL-based Request; policy inputs use that request and remote response. Returns body Buffer, expiry, ETag and Last-Modified. | [remote.js:3][L4] |
| Revalidation | Constructs validator headers, fetches origin, handles 200/304, then creates a new policy to calculate TTL. | [remote.js:24][L4] |
| Policy decision | Both functions call `storable()` and `timeToLive()`, not `evaluateRequest()` or `satisfiesWithoutRevalidation()`. | [remote.js:15][L4] |
| Header/body sink | Neither function returns Set-Cookie or the policy object; generation writes transformed bytes and metadata containing expires/ETag/Last-Modified. | [remote.js][L4], [generate.js:212][L5] |
| Cache hit | Asset generator compares persisted `expires` to `Date.now()` and copies cached image bytes. Validator failure has a separate stale-image fallback. | [generate.js:115][L5] |
| Fetch adapter | `fetchWithRedirects` builds its Request from URL and supplied headers; it does not take a site visitor's incoming Request argument. | [redirectValidation.js:19][L7] |

Source-level inference: this particular consumer does not supply the advisory's
visitor max-stale → retained policy evaluation → cached response-header sink.
The mocked consumer calls below corroborate those function boundaries. They
do not establish that no other packaged or hosted consumer exists. The build
cache can still retain **body bytes**: TTL incorporates stale-if-error and
stale-while-revalidate, and generation has its own error fallback. Do not turn
the narrower call-path result into a claim of general cache safety or freshness.
[Remote-image consumer][L4] [Asset generator][L5] [TTL implementation][L3]
[Experiments](#bounded-private-experiments)

Peso explicitly configures `output: 'static'`; its package build command writes
to `../dist`. The tracked source search over `web/src` and `web/astro.config.mjs`
for `http-cache-semantics|CachePolicy|astro:assets|getImage|inferRemoteSize|<(Image|Picture)`
returned no matches. Inspected image references use plain `img` elements with
local public paths; the layout uses locally imported font CSS and `/og.png`.
These are source observations only. They do **not** establish tree-shaking,
remote-image nonexecution, absence of cache code from output, deployed functions,
or provider runtime/cache behavior. [Config][L8] [Manifest][L0] [Home page][L9]
[Header][L10] [Footer][L11] [Layout][L12]

## Bounded private experiments

All fixtures used synthetic values and `https://cache-fixture.invalid/image`.
No requests were sent to that hostname: library fixtures use plain objects;
consumer fixtures inject `fetchFn` returning an in-memory Response. No app
endpoint, credentials, install, real image transform, filesystem cache write,
generated build or deployment was used. Official tarballs were fetched and
verified in memory, and their cache source was evaluated in an isolated VM for
the candidate comparison. These observations are reproducible with the fixture
below; they are not end-to-end exploitation or release tests. [Fixture below](#reproduction-fixture)
[Consumer implementation][L4] [Registry 4.2.0][U2] [Registry 4.3.0][U3]

For locked 4.2.0, create a shared policy for user A, then request the same
URL/host/method for user B at age **61 seconds**, with
`Cache-Control: max-stale=999999`. Every row had `maxAge() === 0` and ordinary
lookup without max-stale returned false. Direct evaluation produced:

| Response fixture | `storable()` | max-stale hit | Returned synthetic Set-Cookie |
| --- | --- | --- | --- |
| `max-age=60`, Set-Cookie | true | true | `session=SYNTHETIC_A` |
| `max-age=60, proxy-revalidate`, **no cookie** | true | true | absent |
| `no-cache`, no cookie | true | true | absent |
| `max-age=60, must-revalidate`, Set-Cookie | true | false | absent |
| `private, max-age=60`, Set-Cookie | false | true if forcibly retained | `session=SYNTHETIC_A` |
| `no-store`, Set-Cookie | false | true if forcibly retained | `session=SYNTHETIC_A` |
| `max-age=60`, Set-Cookie, `Vary: cookie` | true | false | absent |

The private/no-store rows deliberately bypass storage admission: a consumer
honoring `storable()` would not retain them. They must not be represented as a
successful attack on correctly rejected entries. The proxy-only row isolates
that directive from cookie lifetime handling and is older than its original
max-age. The same seven outcomes were observed for both verified tarballs at
age one second; additional 61-second checks confirmed the cookie and proxy-only
outcomes in **4.3.0** too. This corroborates branch behavior, not actual session
theft. [Reproduction fixture](#reproduction-fixture) [Locked implementation][L3]
[Candidate implementation][U7] [RFC proxy-revalidate][R3]

Four calls into actual installed Astro `loadRemoteImage` / `revalidateRemoteImage`
covered 200 cookie, 200 proxy+cookie, 200 private+cookie, and 304 cookie responses.
All returned exactly `data`, `expires`, `etag`, `lastModified`; expiry equaled
the frozen current time, and 304 returned null data. Temporarily wrapping the
real CachePolicy methods counted `storable: 7` (including nested calls),
`timeToLive: 3`, and **zero** calls to either evaluation method. Initial outgoing
requests had empty headers; the 304 request had only `if-none-match`. Method
wrappers and clock overrides were restored in the process. These fixtures
exercise the consumer functions, not `generateImagesForPath` or a real build.
[Consumer fixture](#reproduction-fixture) [Remote implementation][L4]

Two additional consumer fixtures used a Set-Cookie response with `max-age=60`
and, separately, `stale-if-error=600` or `stale-while-revalidate=600`.
Both returned expiry **600000 ms** after the frozen time, with the same four
fields. This is why zero `maxAge()` cannot be generalized to no body retention
in Astro. [TTL fixture](#reproduction-fixture) [TTL source][L3] [Remote source][L4]

### Reproduction fixture

Run from the reviewed repo with the already-installed, hash-verified versions;
the code writes no files. This reproduces the locked matrix and the four
consumer calls plus TTL probes. The 4.3.0 comparison above used the same
library inputs against its verified tarball source in memory; this snippet
does not install or select that candidate. [Locked source][L3] [Consumer source][L4]

```sh
node <<'NODE'
const assert = require('node:assert/strict');
const Policy = require('./web/node_modules/http-cache-semantics');
const originalNow = Policy.prototype.now;
let now = 1700000000000;
Policy.prototype.now = () => now;
const a = { url: 'https://cache-fixture.invalid/image', method: 'GET',
  headers: { host: 'cache-fixture.invalid', cookie: 'user=A' } };
const b = { ...a, headers: { host: 'cache-fixture.invalid', cookie: 'user=B',
  'cache-control': 'max-stale=999999' } };
const cookie = { 'set-cookie': 'session=SYNTHETIC_A' };
const cases = [
  ['cookie', { 'cache-control': 'max-age=60', ...cookie }, true, true],
  ['proxy-only', { 'cache-control': 'max-age=60, proxy-revalidate' }, true, true],
  ['no-cache', { 'cache-control': 'no-cache' }, true, true],
  ['must-revalidate', { 'cache-control': 'max-age=60, must-revalidate', ...cookie }, true, false],
  ['private', { 'cache-control': 'private, max-age=60', ...cookie }, false, true],
  ['no-store', { 'cache-control': 'no-store', ...cookie }, false, true],
  ['vary-cookie', { 'cache-control': 'max-age=60', ...cookie, vary: 'cookie' }, true, false],
];
try {
  for (const [name, headers, storable, hit] of cases) {
    now = 1700000000000;
    const p = new Policy(a, { status: 200, headers });
    now += 61000;
    assert.equal(p.storable(), storable);
    assert.equal(p.maxAge(), 0);
    assert.equal(p.satisfiesWithoutRevalidation(b), hit);
    assert.equal(p.satisfiesWithoutRevalidation({ ...b, headers: {
      host: 'cache-fixture.invalid', cookie: 'user=B' } }), false);
    console.log(name, p.evaluateRequest(b));
  }
} finally { Policy.prototype.now = originalNow; }
(async () => {
  const { loadRemoteImage, revalidateRemoteImage } =
    await import('./web/node_modules/astro/dist/assets/build/remote.js');
  const keys = ['storable', 'timeToLive', 'evaluateRequest', 'satisfiesWithoutRevalidation'];
  const saved = Object.fromEntries(keys.map(k => [k, Policy.prototype[k]]));
  const counts = Object.fromEntries(keys.map(k => [k, 0]));
  for (const k of keys) Policy.prototype[k] = function (...args) {
    counts[k]++; return saved[k].apply(this, args);
  };
  const dateNow = Date.now;
  Date.now = () => 1700000000000;
  try {
    for (const [label, cc, status] of [
      ['cookie', 'max-age=60', 200], ['proxy', 'max-age=60, proxy-revalidate', 200],
      ['private', 'private, max-age=60', 200], ['304', 'max-age=60', 304],
    ]) {
      const stub = async req => {
        console.log(label, Object.fromEntries(req.headers));
        return new Response(status === 304 ? null : 'SYNTHETIC_IMAGE', {
          status, headers: { 'cache-control': cc, ...cookie, etag: '"synthetic-tag"',
            'last-modified': 'Tue, 14 Nov 2023 22:13:20 GMT' },
        });
      };
      const out = status === 304
        ? await revalidateRemoteImage(a.url, { etag: '"synthetic-old"' }, stub)
        : await loadRemoteImage(a.url, stub);
      assert.deepEqual(Object.keys(out).sort(), ['data', 'etag', 'expires', 'lastModified']);
      assert.equal(out.expires, Date.now());
      assert.equal(out.data === null, status === 304);
    }
    assert.deepEqual(counts, { storable: 7, timeToLive: 3,
      evaluateRequest: 0, satisfiesWithoutRevalidation: 0 });
    console.log(counts);
    for (const directive of ['stale-if-error=600', 'stale-while-revalidate=600']) {
      const out = await loadRemoteImage(a.url, async () => new Response('SYNTHETIC_IMAGE', {
        headers: { 'cache-control': 'max-age=60, ' + directive, ...cookie },
      }));
      assert.equal(out.expires - Date.now(), 600000);
    }
  } finally {
    Date.now = dateNow;
    for (const k of keys) Policy.prototype[k] = saved[k];
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
NODE
```

## Evidence still required before any acceptance decision

These are proposed evidence requirements, not additional implementation or
provider authorization. The existing proposal keeps the cache unresolved and
forbids installing 4.3.0 merely to escape the range. [Proposal][P]

1. **Exact consumer proof for the eventual candidate:** bind package/lock hashes,
   source SHA plus dirty state, actual installed bytes, Node/npm versions,
   plugin/adapter/image configuration and all consumers. Repeat these function
   fixtures against those bytes and trace registration into a controlled build
   using synthetic public images, without credentials. Include body-cache TTL,
   revalidation and error fallback evidence. Today's 7.1.6 path is not proof for
   a future Astro resolution.
2. **Exact generated-artifact proof:** obtain the actual marketing artifact and,
   separately, combined/private-beta output with full inventories and hashes,
   bundle/manifest/module relationships and any functions or server code. Bind
   to the exact producing source/tree, lock, commands and environment. Search
   results over source cannot replace this evidence. No such artifacts were
   available/examined here; package exclusion remains unproven.
3. **Runtime boundary proof:** inspect the intended provider's real build/publish
   commands, adapters/functions, routing and cache behavior at the actual
   deployment. Establish whether visitor headers can reach a shared retained
   policy and whether sensitive body/header bytes can reach another visitor.
   If warranted and separately authorized, use synthetic users/cookies in a
   controlled nonproduction consumer; no live attack or provider mutation is
   part of this review. Source `output: static` is not this proof.
4. **Resolution authority:** either obtain a verified upstream patch with
   regression evidence for the pertinent behavior, or submit a separate, exact
   applicability/treatment proposal to Nathan supported by the above evidence.
   Do not suppress the finding, change cache versions, renew expiry, or treat
   the owner dispute as approval. Preserve raw HIGH and the unresolved decision
   even if a candidate's registry report no longer lists this advisory.

The requirements follow from the missing generated/runtime evidence, the
bounded consumer result, and the existing approval boundary. This review
changes only this Markdown file using `apply_patch`; it does not duplicate the
main agent's independent audit CLI work or advance release gates. [Proposal][P]
[Consumer evidence][L4] [Advisory][U1]

Final read-only verification executed the embedded reproduction fixture directly
from this document with exit 0, checked all reference definitions/local targets,
and rechecked unchanged marketing manifest, lock, installed cache `index.js`, and
Astro remote-consumer hashes. `git diff --check` passed and HEAD remained
`3ad4c2a52389849077e8df1458ea5daee3f84ae7`. Main-agent untracked guard files and
the five pre-existing deployment notes were observed and left untouched.
These checks validate this research handoff, not deployment acceptance.
[Fixture](#reproduction-fixture) [Manifest][L0] [Lock][L1] [Cache source][L3]
[Consumer source][L4]

## Primary source links

[P]: /Users/nathan/Downloads/peso-app/docs/deployment/marketing-security-remediation-proposal-20261005.md
[P0]: /Users/nathan/Downloads/peso-app/docs/deployment/marketing-dependency-primary-source-review-20261005.md
[E0]: /private/tmp/peso-marketing-audit.tAAcB5/npm-audit.json
[L0]: /Users/nathan/Downloads/peso-app/web/package.json
[L1]: /Users/nathan/Downloads/peso-app/web/package-lock.json:2817
[L2]: /Users/nathan/Downloads/peso-app/web/node_modules/astro/package.json:121
[L3]: /Users/nathan/Downloads/peso-app/web/node_modules/http-cache-semantics/index.js:394
[L4]: /Users/nathan/Downloads/peso-app/web/node_modules/astro/dist/assets/build/remote.js:3
[L5]: /Users/nathan/Downloads/peso-app/web/node_modules/astro/dist/assets/build/generate.js:98
[L6]: /Users/nathan/Downloads/peso-app/web/node_modules/astro/dist/core/build/generate.js:171
[L7]: /Users/nathan/Downloads/peso-app/web/node_modules/astro/dist/assets/utils/redirectValidation.js:19
[L8]: /Users/nathan/Downloads/peso-app/web/astro.config.mjs:3
[L9]: /Users/nathan/Downloads/peso-app/web/src/pages/index.astro:43
[L10]: /Users/nathan/Downloads/peso-app/web/src/components/site-header.astro:12
[L11]: /Users/nathan/Downloads/peso-app/web/src/components/site-footer.astro:6
[L12]: /Users/nathan/Downloads/peso-app/web/src/layouts/base-layout.astro:1
[U1]: https://github.com/advisories/GHSA-ch52-4w7c-c8xp
[U2]: https://registry.npmjs.org/http-cache-semantics/4.2.0
[U3]: https://registry.npmjs.org/http-cache-semantics/4.3.0
[U4]: https://registry.npmjs.org/astro/7.1.6
[U5]: https://raw.githubusercontent.com/kornelski/http-cache-semantics/83810982b8f8996b101ed761548ea7e87a9132ea/index.js
[U6]: https://github.com/kornelski/http-cache-semantics/blob/f01112e954b83cfa8765b633ba880e5e980aa54c/index.js
[U7]: https://github.com/kornelski/http-cache-semantics/blob/b1d4bd682fbab0252985de45219f4e7497c0067c/index.js
[U8]: https://github.com/kornelski/http-cache-semantics/issues/56
[U9]: https://github.com/kornelski/http-cache-semantics/issues/56#issuecomment-5975759591
[R1]: https://www.rfc-editor.org/rfc/rfc9111.html#section-7.3
[R2]: https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.7
[R3]: https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.8
