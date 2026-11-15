# shell-quote primary-source review — Gate 2 hold

For Nathan; read-only research on 2026-10-06, approximately 17:40–17:43 UTC.
Workspace HEAD: `b223b74b9e31a92f0b30b048b0e00303876db54b`.
Read [R1 hold](root-dependency-r1-candidate-hold-20261006.md) and the research skill.
**Gate 2 remains FAIL.** This note verifies published evidence, not a remediation
approval, applicability exception, unaffected assertion, or security-pin refresh.
Expiry remains **2026-10-12T23:59:59Z**. Main-agent locked-parent and installed-consumer
tracing/proposal is separate; this sidecar neither repeats nor certifies it.

## Advisory identity and present metadata

[GitHub database](https://github.com/advisories/GHSA-pqg4-j6r4-53mv) and
[maintainer advisory](https://github.com/ljharb/shell-quote/security/advisories/GHSA-pqg4-j6r4-53mv)
identify CVE-2026-102422 / CWE-78, affected `>=1.8.4 <1.11.0`, patched **1.11.0**.
The flaw concerns attacker-controlled line terminators in strings occurring after
a comment token in one `quote()` call. This is an upstream trigger description,
not a conclusion about Peso execution paths. No payload was executed.

The retained R1 raw audit identifies npm source **1241332**, CRITICAL, root path
`node_modules/shell-quote`, range `>=1.8.4 <1.11.0`, CVSS v3.1 **8.1**.
Its SHA-256 was independently rechecked without editing:
`b80b5e4a17e69ccddb6d55aa0677acb1af89269f6f8020cf71582f98a3d0e77f`
([local evidence](../../artifacts/root-r1/run-xcorxJ/audit/npm-audit.json)).
The locked 1.9.0 version is the research input from the hold, not a new local trace.

Current [database API](https://api.github.com/advisories/GHSA-pqg4-j6r4-53mv):
severity `critical`; legacy `cvss` remains v3.1 **8.1**; `cvss_severities`
also supplies v4 **9.2**. Database publication/review: `2026-10-06T13:40:36Z`;
update: `2026-10-06T13:40:37Z`; `withdrawn_at: null`.
Current [maintainer API](https://api.github.com/repos/ljharb/shell-quote/security-advisories/GHSA-pqg4-j6r4-53mv):
severity `high`, v3.1 **8.1**, v4 unset; published/updated `2026-09-29T03:47:24Z`,
not withdrawn. Both retain the same affected range and patched version.
Thus severity differs between owning surfaces; the raw CRITICAL/v3.1 evidence
is not rewritten or interpreted as a downgrade. Exact vectors:

- v3.1: `CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H`.
- v4: `CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N`.

## Minimum patch, owning fix and upstream tests

The [owning fix](https://github.com/ljharb/shell-quote/commit/6002b2ed90c6b83095eb272b6b0adaf3a172b0bc)
is `6002b2ed90c6b83095eb272b6b0adaf3a172b0bc`. It tracks whether a comment has
occurred and throws `TypeError` for subsequent strings containing LF, CR,
U+2028 or U+2029. README and quote declaration comments document that restriction.
[Tests at that commit](https://github.com/ljharb/shell-quote/blob/6002b2ed90c6b83095eb272b6b0adaf3a172b0bc/test/quote.js#L161)
cover all four terminators, a non-adjacent later token, and parse-produced
mid-word comments followed by appended input; controls cover strings before
comments and later strings without terminators. Assertions were inspected, not run.

[Fix-to-release comparison](https://api.github.com/repos/ljharb/shell-quote/compare/6002b2ed90c6b83095eb272b6b0adaf3a172b0bc...88241f8fa324a85da03b40fc69443c069837b472)
reports `ahead`, seven commits ahead, zero behind, merge base equal to the fix.
Registry `gitHead` for 1.11.0 is `88241f8fa324a85da03b40fc69443c069837b472`.
All **11** shipped regular files match that immutable upstream commit byte-for-byte,
including the guarded `quote.js`; the owning fix's earlier `quote.js` differs
because subsequent quoting fixes also shipped. Its regression block remains in
[release test/quote.js](https://github.com/ljharb/shell-quote/blob/88241f8fa324a85da03b40fc69443c069837b472/test/quote.js).
Tests are omitted from the 1.11.0 npm tarball, so source inspection is not a
claim of shipped tests, runtime reproduction, or a passed upstream suite.

## Exact registry and tarball bytes

Owning metadata: [1.9.0](https://registry.npmjs.org/shell-quote/1.9.0),
[1.11.0](https://registry.npmjs.org/shell-quote/1.11.0).
Both downloaded archives matched metadata SHA-512 SRI and SHA-1 shasum.
SHA-256 below is independently computed over compressed tarball bytes.

| Version | Exact resolved URL | Compressed bytes | SHA-256 |
| --- | --- | ---: | --- |
| 1.9.0 | https://registry.npmjs.org/shell-quote/-/shell-quote-1.9.0.tgz | 11111 | `5d3b53eba647dee6d8c8465b57937e59798710eb728af66d5e21ab0977824d05` |
| 1.11.0 | https://registry.npmjs.org/shell-quote/-/shell-quote-1.11.0.tgz | 9588 | `028be526afacb2bf5c6c008a95d5435b5d205135f68bb48afd0bb947610393f1` |

Exact SHA-512 SRI, 1.9.0:
`sha512-Iov+JwFv/2HcTpcwNMKd8+IWNb8tboQJNQTkAY/LLVK7gGH9jy+LGkVqPxfekHl+yMmiqXszdGWXgkfml7hjqA==`.
Exact SHA-512 SRI, 1.11.0:
`sha512-JdxDPD0DBTyu08pq0kPC0xSNet/qsU07qT6IsX1AS8oO2ICNRY4ldNa8OAI6PuwAH8tG3lxEhbqmyp4Dw4036g==`.
SHA-1: 1.9.0 `e108b1a136586d5964edb3300016d4bedba0fe57`;
1.11.0 `fdbed3f4f297a8090c64cc13c4643c0b3e957c79`.
Registry file-count/unpacked-size declarations match parsed contents:
1.9.0 **21 / 33477**; 1.11.0 **11 / 25616**. No nonregular tar members observed.
[Packument](https://registry.npmjs.org/shell-quote) currently tags **1.12.0** latest;
this review targets the advisory minimum, not a latest-version recommendation.
Publication times: 1.9.0 `2026-06-25T04:47:19.588Z`,
1.11.0 `2026-09-29T02:34:24.391Z`.

All 1.11.0 file hashes below bind tar contents to
[immutable release source](https://github.com/ljharb/shell-quote/tree/88241f8fa324a85da03b40fc69443c069837b472).

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| .github/FUNDING.yml | 582 | `c7a193a356c0b26fa9b1951da9e2d96667f29d90e69cac03c63246a5d4d0e53b` |
| LICENSE | 1109 | `8bb16db1b047019e4395965f2cf3611b06c34bf86dc2d0210b3c3f91b53c21fe` |
| README.md | 6530 | `55a63af81235f1f573285452ae9d154c6f815c92bc805e49fff14bc456ba1f66` |
| index.d.ts | 873 | `9662f0c5d566400bd966954513836ca3c52ba478b2915d63a2e0247970da6357` |
| index.js | 87 | `6dba443a976bcfdb5972a479c5c43c298e96bdef471c1629844ce9d6b31f5b68` |
| package.json | 2062 | `aa7d4d7ce4ab7aa759b3f75bfb7c3857d5dc80d2f39a6fc7f2aff6c48d43bc6f` |
| parse.d.ts | 1783 | `e88115e6dd80c98334d31f2cb18f949a911cfcf31bf6171c49822cf689d14e15` |
| parse.js | 9871 | `dda6ec46f07a7d6b768cadfd5c6baa80427f04b737d0a6ab6d9c58b68d9fbbaf` |
| quote.d.ts | 559 | `0b85b063e7306f60c60151de3504cb141807f233b5e87cfe15d9ad6a28b493d8` |
| quote.js | 2037 | `fe2cfc6ce188a0204f4fe8862abf59b2c111d8192fa3f9d536ca1135df430635` |
| tsconfig.json | 123 | `9fc194b35c4578503db2e415266293f0886ce04aff360f4cf796079f8b59745c` |

Additional source SHA-256: owning-fix `quote.js`
`8cc7b9dbde6f7736dd78b5517a38f13d284572aa1d45a46ff4e64cfb9ea35916`;
owning-fix `test/quote.js` (7804 bytes)
`88cbcfdbbe8f9389d5d60ba8a542658a31d0c64aaa4d3a46d402652bd6292cd3`;
release `test/quote.js` (8670 bytes)
`b7c7cf7574a247347647983c1274b569a9e0013de0df8fc58826914d97a6c88e`.

## API, behavior and packaging delta from 1.9.0

Tarball manifests and [release entry point](https://github.com/ljharb/shell-quote/blob/88241f8fa324a85da03b40fc69443c069837b472/index.js)
retain `engines.node: >= 0.4`, CommonJS `main: index.js`, `types: index.d.ts`,
and named `parse`/`quote` exports. Neither version declares `exports`, `type`,
`bin`, runtime/optional/peer/bundled dependencies. Root entrypoint/declarations
are byte-identical; `shell-quote/parse` and `/quote` files remain available.
Declared engine compatibility was not tested. MIT license is unchanged.

Static comparison of shipped code and the
[release changelog](https://github.com/ljharb/shell-quote/blob/88241f8fa324a85da03b40fc69443c069837b472/CHANGELOG.md)
shows changes beyond the advisory guard:

- `parse` adds typed `splitUnquoted?: boolean | string`: omitted/false/empty
  disables splitting; true uses space/tab/LF; a string supplies delimiter characters.
  Quoted expansions remain unsplit. This is opt-in; other parser fixes are not.
- `parse` adds ANSI-C quoting with escape decoding, no variable expansion or
  field splitting inside it, and NUL truncation. Single-quote backslashes,
  escaped-backslash scanning, nested substitution brace matching, text after
  special parameters, and underscore-prefixed variable names change handling.
- `quote` additionally escapes tilde in glob patterns, preserves empty glob
  patterns as an empty quoted word, and changes quoting for apostrophe/exclamation
  combinations to preserve `!`; its double-quote branch no longer backslash-escapes
  `!`. The single-quote branch removes a replacement that could not match.
- README documents POSIX quoting, use of output verbatim, and parser expansion
  limitations. These documentation statements are not Windows execution validation.
- Packaging removes `.nycrc`, `eslint.config.mjs`, `security.md` and seven
  `test/*.js` files; adds no files. Changed dev-only ranges: eslint, evalmd,
  auto-changelog, @arethetypeswrong/cli, @ljharb/eslint-config.

Both manifests have exactly the same 12 scripts: `prepack`, `prepublish`,
`prepublishOnly`, `prelint`, `lint`, `postlint`, `pretest`, `tests-only`, `test`,
`posttest`, `version`, `postversion`. **No new lifecycle scripts**; neither declares
preinstall/install/postinstall/prepare. Existing prepublish/prepack/test/version
hooks still exist; no script was invoked. No native build file was shipped.

## Registry signature verification and evidence limits

Following [npm's signature format](https://docs.npmjs.com/about-registry-signatures/),
Node built-in crypto verified ECDSA/SHA-256 signatures for both versions over
`shell-quote@<version>:<dist.integrity>`, using the HTTPS
[registry keys](https://registry.npmjs.org/-/npm/v1/keys). Both returned **true**.
Matched key ID `SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U`,
scheme `ecdsa-sha2-nistp256`, `expires: null`; recomputed SSH-format public-key
fingerprint matches. This verifies registry integrity binding, not publisher
identity, independent provenance/attestation, code safety, or Peso compatibility.

Exact fetched-response SHA-256 (response bodies, not normalized JSON):
database API `b133489e9650324443f4ef79eae5cff3c2f9ef19552349fbe115ba4a15fb7c57`;
maintainer API `a33e9d375b0af285dc7d18af5dd122304b3eec32b74bd71266e045c61e4a36dd`;
1.9.0 metadata `3d5607b89880e938200d9df71cf038cd1df1f34bdc86073a1475717ac04280e8`;
1.11.0 metadata `efa65e1213a793776565ded927d0d6b3b1cf45bb0c6babb52d2a784161f3329a`;
keys `faf23d8753d5bb79df250f10391ac89b63ecf7743e48487a544a99c847f9c8df`.
Fetch/parse/hash/signature operations stayed in memory; no tar extraction to disk,
npm installs, lifecycle/package execution, shell payloads, or fresh npm audit.
Initial sandbox HTTPS attempts failed DNS; approved read-only network access worked.
Raw fetched bytes were not persisted; these bindings are research receipts, not a
durable raw-evidence bundle. No independent source-signature/provenance check ran.
Only this note was written via apply_patch; five prior notes and raw evidence were
preserved. Dependencies/locks/tests/app/providers/CONTEXT/ADRs/pins were untouched;
no commit, push, workflow dispatch or other-thread message. Main integration,
installed-consumer relevance and any remediation/compatibility testing remain unverified.
