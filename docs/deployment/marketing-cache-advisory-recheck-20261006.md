# Marketing cache advisory recheck — 2026-10-06

For Nathan's Peso Gate-2 read-only reconciliation. **Gate 2 remains FAIL.**
The current owning GitHub advisory still identifies http-cache-semantics
`<= 4.2.0` as affected, provides no patched version, and is not withdrawn.
The current npm registry still lists **4.3.0** as latest; no release newer than
the previously examined 4.3.0 was observed. Neither the maintainer dispute nor
escape from the affected range establishes remediation. [GHSA API][A]
[Advisory page][H] [Registry][N]

## Scope and dated evidence boundary

Workspace: `/Users/nathan/Downloads/peso-app`. Main-agent source checkpoint:
`c599bfb315e2971fac8284dfe34c210676186a9c`. This is supplied context, not a fresh
local source/pin verification by this sidecar. The main agent independently
verifies retained root/web audits, pins and source scope; those checks were not
duplicated here.

Read the [2026-10-05 applicability review][P1] and
[2026-10-05 remediation proposal][P2]. Their cache 4.2.0 and examined 4.3.0
remain unresolved. Their signature, tarball/member integrity, source and fixture
checks are **historical evidence, not fresh passes**. This recheck did not fetch
tarballs, verify signatures, execute package code or fixtures, install packages,
build, audit, inspect current consumers, or prove generated/runtime exclusion.

Successful direct primary-source retrievals occurred
`2026-10-06T18:22:38.978Z`–`2026-10-06T18:23:22.997Z`
(October 6, 14:22–14:23 America/New_York). Public GET requests were restricted to
this advisory, its owning database record and linked dispute, maintainer issue
56/comments, and this package's registry metadata. Initial sandbox fetches failed;
the successful public reads used approved network access. No deployment-provider
calls, messages, agents, Git mutations or other writes were performed. The only
write is this note via `apply_patch`; existing notes and raw evidence are preserved.

## Current owning advisory and database observations

**Observation — live GHSA API:** identity `GHSA-ch52-4w7c-c8xp`, alias
`CVE-2026-93748`, type `reviewed`, severity `high`, npm package
`http-cache-semantics`, `vulnerable_version_range: "<= 4.2.0"`,
`first_patched_version: null`, `withdrawn_at: null`.
`repository_advisory_url` is null. The advisory page independently displays the
same affected range and patched versions **None**. [GHSA API][A] [Page][H]

| GHSA API timestamp | Observed UTC value |
| --- | --- |
| `published_at` | `2026-09-18T18:31:44Z` |
| `updated_at` | `2026-10-02T22:36:44Z` |
| `github_reviewed_at` | `2026-10-02T22:36:42Z` |
| `nvd_published_at` | `2026-09-18T18:18:33Z` |

The API contains CVSS 3.1 score **7.5** and CVSS 4.0 score **8.7**, alongside
legacy `cvss` 3.1/7.5. These concurrent fields explain why a report using 3.1
need not match the page's 4.0 score; this is not permission to rewrite retained
audits. [GHSA API][A]

**Observation — owning advisory-database JSON:** schema 1.4.0, same GHSA/CVE,
published `2026-09-18T18:31:44Z`, modified `2026-10-02T22:36:42Z`, reviewed/HIGH.
Its npm ECOSYSTEM events are `introduced: "0"`, `last_affected: "4.2.0"`;
there is **no `fixed` event** and no `withdrawn` field. The two-second difference
between this record's modified time and the GHSA API updated time is recorded
as observed, without substituting one field for the other. [Database record][D]
[Immutable owning blob][B]

The contents API returned blob SHA-1
`ed95d1cd4d937b994d6f67563d822cc1677be62d`. Independently retrieved that exact
owning Git blob, base64-decoded its 2,371 bytes, and computed Git SHA-1 over
`blob 2371` + NUL + content: it matched the declared blob identity. Decoded
content SHA-256 was
`5d666500be0369035a36aca4e9009b477ad239d6094e33bf67f93ddd5a190fbe`
for both contents and immutable-blob responses. This binds the observed owning
record without relying solely on mutable `main`. The contents HTTP Last-Modified
was `2026-10-06T18:17:47Z`; that response header is not the advisory's embedded
modified timestamp and is not evidence of a new fix. [Contents API][D]
[Immutable blob API][B]

## Current registry release observations

**Observation — full npm packument:** `_id: http-cache-semantics`,
`_rev: 36-cc56ace056dc7b66e9ec94ebd6e91bbb`, 30 version entries.
`time.created: 2016-05-31T09:18:22.371Z`,
`time.modified: 2026-10-04T02:56:05.772Z`. All returned version keys/timestamps
were examined; there was no newer stable or prerelease entry than 4.3.0.
[Full registry metadata][N]

| Dist tag | Current target | Registry publication timestamp |
| --- | --- | --- |
| `beta` | `4.2.0-beta.1` | `2025-02-03T00:45:29.967Z` |
| `next` | `4.2.0-beta.2` | `2025-03-19T11:17:03.197Z` |
| `latest` | `4.3.0` | `2026-10-04T02:56:05.593Z` |

Registry 4.2.0 publication time is `2025-05-09T13:38:11.855Z`. The full packument
and separately retrieved exact 4.3.0 metadata agree on these package identities:
[Packument][N] [Exact 4.3.0 metadata][V]

| Registry-declared identity | 4.2.0 | 4.3.0 |
| --- | --- | --- |
| `_id` | `http-cache-semantics@4.2.0` | `http-cache-semantics@4.3.0` |
| `gitHead` | `83810982b8f8996b101ed761548ea7e87a9132ea` | `b1d4bd682fbab0252985de45219f4e7497c0067c` |
| `dist.shasum` (SHA-1) | `205f4db64f8562b76a4ff9235aa5279839a09dd5` | `09eead3b16c6d85552857cc3fbd888d8353a2aaf` |
| `dist.fileCount` / `dist.unpackedSize` | `4` / `49973` | `4` / `50444` |

Registry-declared tarball SRI values:

- 4.2.0: `sha512-dTxcvPXqPvXBQpq5dUr6mEMJX4oIEFv6bwom3FDwKRDsuIjjJGANqhBuoAn9c1RQJIdAKav33ED65E2ys+87QQ==`.
- 4.3.0: `sha512-M5t5LlJpS1UHMjvwRQVdFHvPISGeLAxNcrWuJkeGh0KxsqCHZ1O3NXZU/8x7cD0BDcGW8kapxMKTvwlqrNkHkA==`.

Tarball URLs are [4.2.0][T2] and [4.3.0][T3]; they were recorded from metadata,
**not downloaded or freshly integrity-verified**. The exact 4.3.0 response has
no `deprecated` field. It declares two signatures with key ID
`SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U`; these are observed
metadata, not a new cryptographic verification. Registry `gitHead` declarations
are not a fresh source-to-tarball binding. No new release or owning security-fix
claim was identified in the inspected sources, so no candidate was labeled a fix.
[Exact version metadata][V] [Historical integrity/source comparison][P1]

## Focused maintainer and owning-database dispute observations

Maintainer issue [56][I] (numeric ID `5490093977`) remains closed with
`state_reason: not_planned`, created `2026-09-17T16:30:35Z`, closed
`2026-10-04T02:24:46Z`, updated `2026-10-04T06:52:46Z`. Its four-comment response
had no pagination link. Owner `kornelski`'s [comment 5975759591][M] was created
and last updated `2026-10-04T02:24:46Z`; it disputes the cookie/freshness premise
and says private cache control governs sharing. It does not identify an
implemented security patch. The later [comment 5977471602][F], created/updated
`2026-10-04T06:52:46Z`, links the database withdrawal request. [Issue API][IA]
[Complete returned comment list][IC]

Owning advisory-database [issue 10139][Q] (numeric ID `5696987552`) remains
**open**, `closed_at: null`, created `2026-10-04T06:51:34Z`, updated
`2026-10-04T07:54:29Z`, zero comments. Its comments API returned `[]` without
pagination. The issue requests withdrawal on the basis of the owner's dispute;
the API metadata does not show an owning-database resolution. [Issue API][QA]
[Comments API][QC]

## Interpretation and unresolved evidence

**Inference:** these bounded observations provide no current patched target,
withdrawal, or newer release that resolves the prior cache blocker. A closed
maintainer issue or a pending database withdrawal request is not a withdrawal
of the owning advisory. 4.3.0 lies outside the reported range, but that fact
does not establish corrected behavior. The [prior review][P1] reported that
4.3.0 still reproduced its principal library cases; that remains dated evidence
and was not rerun. Both versions remain unresolved for this reconciliation.

**Unverified here:** current tarball contents/signature validity, any source
patch beyond these bounded linked records, new regression tests, current
installed/source/lock/consumer identities, generated-artifact exclusion,
provider/runtime exposure, retained audit provenance, pins and acceptance scope.
No inference of Peso exploitation or non-applicability is made. No allowance,
exception, expiry extension or remediation acceptance follows. **Gate 2 remains
FAIL**, independently of any future range-based clean audit result. [Prior
applicability limits][P1] [Remediation boundary][P2]

## Response identity and retention

All nine successful direct requests below returned HTTP 200 at their requested
URLs without redirects. SHA-256 and byte counts bind the exact response bodies
returned by Node's `fetch` after HTTP content decoding, before JSON parsing;
they are not hashes of compressed wire bytes or canonicalized JSON. GitHub JSON
used `application/vnd.github+json`; npm used `application/json`.

| Response | Retrieved UTC | Body bytes | Response-body SHA-256 |
| --- | --- | ---: | --- |
| [GHSA API][A] | `2026-10-06T18:22:39.116Z` | 2305 | `1871b8186dd10aa82aa211741c98a71e0209f328efe9a23aee1494f765c3a6e4` |
| [Full registry][N] | `2026-10-06T18:22:38.978Z` | 68046 | `80d047081285fcc7b46d40f2526e1d123fa3b2c02c0d4bb4d718cb678a80e623` |
| [Maintainer issue][IA] | `2026-10-06T18:22:39.007Z` | 6424 | `52e6a9b71840c190247f3808740609218f3ac9e3c3f173b89bdc8c5351c90c37` |
| [Maintainer comments][IC] | `2026-10-06T18:22:39.016Z` | 7982 | `9eedac4b847aeba6cb19cd31455ed98c2ff59c82ae212a5b642d4f3a2e5ebf9c` |
| [Database contents][D] | `2026-10-06T18:23:02.545Z` | 4515 | `cf2ff883c39566d23bad9d586dde21e30804e91c2cda85245ec871c6e0254865` |
| [Database dispute][QA] | `2026-10-06T18:23:02.573Z` | 3867 | `5cc8a06e8257f0ffec198048ac61c03ca9202102735f5930140ebad2afebdf2b` |
| [Database comments][QC] | `2026-10-06T18:23:02.540Z` | 2 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| [Exact 4.3.0][V] | `2026-10-06T18:23:02.633Z` | 1713 | `c4c95cf8d3becce754366907d8a99b44c6e7a10ce725cc01a5f7b859c0682493` |
| [Immutable database blob][B] | `2026-10-06T18:23:22.997Z` | 3560 | `ff10087561fd6c4f800fe86f4049e6731973193b51832976e9363159a4f1aba3` |

Additional response identifiers: GHSA ETag
`W/"6d0d495e1dc1ab96406bd7cd66ae14f5a5565abb8ecc60c196b5609ab2cb3e6d"`,
Last-Modified `Fri, 02 Oct 2026 22:36:44 GMT`, GitHub request ID
`C64C:162A3F:36A4B6D:B3AC0F8:6AC53C6F`; registry ETag
`W/"0e886ba1e24f3f6cf38a05e0525b3b49"`, Last-Modified
`Sun, 04 Oct 2026 02:56:07 GMT`; contents ETag
`"ed95d1cd4d937b994d6f67563d822cc1677be62d"`; immutable-blob request ID
`C667:3652FA:3614808:B1CAF7C:6AC53C9B`. ETags are recorded opaque HTTP
identifiers; the blob's computed Git hash is the separate content check above.

**Retention:** raw response bodies and decoded owning JSON were held only in
process memory, then discarded when each retrieval process exited. This note
retains selected fields, URLs, timestamps and hashes; tool transcript output is
not a separate durable raw-body evidence archive. No raw response-body file was
created, and the browser-rendered advisory page was not hash-bound. A later
request to a mutable URL can return different bytes, so these hashes alone do
not allow reconstruction of the responses. The immutable owning database blob
provides a retrievable content identity while upstream retains it; that is not
a promise of local raw-evidence retention.

## Direct sources

[P1]: /Users/nathan/Downloads/peso-app/docs/deployment/marketing-cache-applicability-review-20261005.md
[P2]: /Users/nathan/Downloads/peso-app/docs/deployment/marketing-security-remediation-proposal-20261005.md
[A]: https://api.github.com/advisories/GHSA-ch52-4w7c-c8xp
[H]: https://github.com/advisories/GHSA-ch52-4w7c-c8xp
[D]: https://api.github.com/repos/github/advisory-database/contents/advisories/github-reviewed/2026/09/GHSA-ch52-4w7c-c8xp/GHSA-ch52-4w7c-c8xp.json
[B]: https://api.github.com/repos/github/advisory-database/git/blobs/ed95d1cd4d937b994d6f67563d822cc1677be62d
[N]: https://registry.npmjs.org/http-cache-semantics
[V]: https://registry.npmjs.org/http-cache-semantics/4.3.0
[T2]: https://registry.npmjs.org/http-cache-semantics/-/http-cache-semantics-4.2.0.tgz
[T3]: https://registry.npmjs.org/http-cache-semantics/-/http-cache-semantics-4.3.0.tgz
[I]: https://github.com/kornelski/http-cache-semantics/issues/56
[IA]: https://api.github.com/repos/kornelski/http-cache-semantics/issues/56
[IC]: https://api.github.com/repos/kornelski/http-cache-semantics/issues/56/comments?per_page=100
[M]: https://github.com/kornelski/http-cache-semantics/issues/56#issuecomment-5975759591
[F]: https://github.com/kornelski/http-cache-semantics/issues/56#issuecomment-5977471602
[Q]: https://github.com/github/advisory-database/issues/10139
[QA]: https://api.github.com/repos/github/advisory-database/issues/10139
[QC]: https://api.github.com/repos/github/advisory-database/issues/10139/comments?per_page=100
