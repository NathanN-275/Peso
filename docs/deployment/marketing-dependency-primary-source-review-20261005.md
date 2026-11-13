# Marketing dependency primary-source review — 2026-10-05

For Nathan's release-security remediation proposal. Research only; findings authorize no dependency changes or deployment. Astro's critical finding, CI, and frozen-scope decisions remain with the main agent.

## Provenance and limits

- Observed HEAD: `8f7094c71bc4b17774ce147e6fbe14c2825b2350`.
- Input audit: `/private/tmp/peso-marketing-audit.tAAcB5/npm-audit.json`, SHA-256 `1d19ca0390c2859f076fb73bcb27e5899559c64d7bab9c7c1eb2ed19aae03a35`; auditReportVersion 2. Its totals are 7 HIGH, 1 MODERATE, 1 CRITICAL; this note covers the eight noncritical package entries and all 15 causes within them.
- Input lock: `web/package-lock.json`, SHA-256 `af4b8931f67be644bbe14c5cf73600d1d9e44e43e6dc171486169c7d01f3ab91`. Every reviewed package resolves at `node_modules/<name>` within this lock; all eight are transitive.
- Primary evidence retrieved on 2026-10-05 America/New_York (2026-10-06 UTC; clock checkpoint `2026-10-06T01:40:09Z`): public maintainer advisories, releases/source, and npm registry JSON. Registry timestamps below are exact `time[version]` values, distinct from GitHub release/advisory dates. Links are live; this is a dated observation, not an archived upstream snapshot.
- “Minimum” means the smallest published stable upgrade in the locked release line addressing **every cause in that package's supplied entry**, not the oldest patched version in another major or a guarantee against other advisories. Audit `fixAvailable: true` alone does not establish a fix.
- Existing temporary braces/Forge treatment still expires `2026-10-12T23:59:59Z`. No scope hash, policy, pin, or exception was refreshed or expanded; the two hashes above bind research inputs only. No provider exports or credentials were used.

## Published minima and existing parent constraints

The seven confirmed minima and the unresolved cache candidate all satisfy the parent ranges recorded below, checked with the existing local `semver` library. Range compatibility does not prove installability, API compatibility, runtime exposure, or release readiness.

| Package / audit severity | Locked → minimum stable fix | npm publication (UTC) | Existing locked parents and constraints |
| --- | --- | --- | --- |
| devalue / HIGH | 5.9.0 → **5.9.3** | `2026-09-18T18:45:39.495Z` ([registry](https://registry.npmjs.org/devalue)) | Astro 7.1.6: `^5.8.1` |
| http-cache-semantics / HIGH | 4.2.0 → **unresolved**; 4.3.0 is a published candidate outside the audit range, not a verified fix | 4.3.0: `2026-10-04T02:56:05.593Z` ([registry](https://registry.npmjs.org/http-cache-semantics)) | Astro 7.1.6: `^4.2.0` |
| js-yaml / HIGH | 4.3.1 → **4.3.2** | `2026-08-26T20:42:48.747Z` ([registry](https://registry.npmjs.org/js-yaml)) | Astro 7.1.6 and @astrojs/internal-helpers 0.10.2: `^4.3.0` |
| nanoid / HIGH | 3.3.17 → **3.3.18** | `2026-08-07T16:41:05.696Z` ([registry](https://registry.npmjs.org/nanoid)) | PostCSS 8.5.25: `^3.3.16` |
| sharp / HIGH | 0.35.3 → **0.35.4** | `2026-08-26T09:42:27.903Z` ([registry](https://registry.npmjs.org/sharp)) | Astro 7.1.6, optional dependency: `^0.34.0 \|\| ^0.35.0` |
| source-map-js / HIGH | 1.2.1 → **1.2.2** | `2026-09-30T14:08:09.382Z` ([registry](https://registry.npmjs.org/source-map-js)) | css-tree 3.2.1, magicast 0.5.4, PostCSS 8.5.25: `^1.2.1`; csso's nested css-tree 2.2.1: `^1.0.1` |
| svgo / HIGH | 4.0.2 → **4.1.0** | `2026-08-24T12:10:36.576Z` ([registry](https://registry.npmjs.org/svgo)) | Astro 7.1.6: `^4.0.1` |
| smol-toml / MODERATE | 1.7.1 → **1.9.0** | `2026-09-22T17:15:34.756Z` ([registry](https://registry.npmjs.org/smol-toml)) | Astro 7.1.6 and @astrojs/internal-helpers 0.10.2: `^1.6.0` |

Registry stable-version enumeration found only the target between each locked version and minimum, except devalue (`5.9.1`, `5.9.2`, `5.9.3`) and smol-toml (`1.7.2`, `1.8.0`, `1.9.0`). `http-cache-semantics@4.2.1` and `smol-toml@1.8.1` are unpublished. All eight candidate version records exist, have no prerelease suffix and no `deprecated` field. Registry Node engines: sharp `>=20.9.0`; nanoid `^10 || ^12 || ^13.7 || ^14 || >=15.0.1`; source-map-js `>=0.10.0`; svgo `>=16`; smol-toml `>= 18`; devalue, http-cache-semantics and js-yaml have no `engines` field in these version records.

## Every current audit cause

### devalue — all seven causes require 5.9.3 together

| Maintainer advisory | Supplied audit range | Maintainer patch / publication |
| --- | --- | --- |
| [GHSA-9rgm-9g3h-6x36: malformed-input parse DoS](https://github.com/sveltejs/devalue/security/advisories/GHSA-9rgm-9g3h-6x36) | `<5.9.1` | **5.9.2**, published `2026-08-27T14:11:44Z`; advisory affected range says `<5.9.1` but patch field/body say 5.9.2. [v5.9.2 release](https://github.com/sveltejs/devalue/releases/tag/v5.9.2) confirms index bounds fix. Do not infer 5.9.1 is sufficient. |
| [GHSA-j22f-vq7h-c4qm: shared-buffer disclosure](https://github.com/sveltejs/devalue/security/advisories/GHSA-j22f-vq7h-c4qm) | `>=5.1.0 <=5.9.2` | **5.9.3**, published 2026-09-18 |
| [GHSA-hx4r-w6wj-j8fg: sparse-array CPU amplification](https://github.com/sveltejs/devalue/security/advisories/GHSA-hx4r-w6wj-j8fg) | `<=5.9.2` | **5.9.3**, published 2026-09-18 |
| [GHSA-mcm9-63f2-9j32: repeated-string expansion](https://github.com/sveltejs/devalue/security/advisories/GHSA-mcm9-63f2-9j32) | `<=5.9.2` | **5.9.3**, published `2026-09-18T18:42:08Z` |
| [GHSA-wf3x-273g-mvxv: sparse-array eager allocation](https://github.com/sveltejs/devalue/security/advisories/GHSA-wf3x-273g-mvxv) | `>=1.0.0 <=5.9.2` | **5.9.3**, published `2026-09-18T18:41:44Z` |
| [GHSA-x5rw-q4pp-hg5g: internal async rejection](https://github.com/sveltejs/devalue/security/advisories/GHSA-x5rw-q4pp-hg5g) | `>=5.8.0 <=5.9.2` | **5.9.3**, published `2026-09-18T18:40:18Z` |
| [GHSA-4q55-j62x-fr9h: malformed null-prototype keys](https://github.com/sveltejs/devalue/security/advisories/GHSA-4q55-j62x-fr9h) | `<=5.9.2` | **5.9.3**, published `2026-09-18T18:39:52Z` |

The [v5.9.3 release](https://github.com/sveltejs/devalue/releases/tag/v5.9.3), published `2026-09-18T18:44:46Z`, lists fixes for all six later causes. Maintainer severity differs from the supplied audit for repeated strings (medium versus HIGH), async rejection (low versus HIGH), and malformed keys (low versus MODERATE). Preserve the audit's package-level HIGH; these discrepancies neither remove causes nor establish Peso is unaffected. Maintainer pages for shared-buffer disclosure and sparse-array CPU amplification were readable, but corresponding unauthenticated advisory API requests returned 404; exact sub-day advisory publication timestamps were not verified for those two.

### http-cache-semantics — one cause, disputed and unresolved

The supplied `GHSA-ch52-4w7c-c8xp` range is `<=4.2.0`. The [repository owner's response](https://github.com/kornelski/http-cache-semantics/issues/56#issuecomment-5975759591), posted `2026-10-04T02:24:46Z`, disputes the report and says sharing restrictions require `Cache-Control: private`. The repository advisory API returns 404; no maintainer advisory identifies a patched version.

Registry `4.3.0` has gitHead [`b1d4bd682fbab0252985de45219f4e7497c0067c`](https://github.com/kornelski/http-cache-semantics/commit/b1d4bd682fbab0252985de45219f4e7497c0067c), committed `2026-10-04T02:54:06Z`. Its [published-commit source](https://github.com/kornelski/http-cache-semantics/blob/b1d4bd682fbab0252985de45219f4e7497c0067c/index.js#L429) still honors `max-stale` via the stale branch; `maxAge()` still returns zero for the cited shared-cookie/proxy-revalidate cases (lines 631–645). This limited inspection does not resolve the disputed semantics. **4.3.0 escaping the supplied range is insufficient to label it patched.** A verified minimum for this cause remains unavailable; no runtime-unaffected conclusion follows from the owner's dispute.

### Other six entries

- **js-yaml:** [GHSA-2883-xcg3-v3hh](https://github.com/nodeca/js-yaml/security/advisories/GHSA-2883-xcg3-v3hh), audit `>=4.0.0 <4.3.2`, published `2026-08-26T21:38:31Z`, updated `2026-09-01T21:42:13Z`, names **4.3.2** for v4. The [release commit/changelog](https://github.com/nodeca/js-yaml/commit/79ca68d90f333fbe6d9e42827527e62636200191), `2026-08-26T20:39:09Z`, counts empty merge mappings toward the budget and caps merge-sequence size. The 3.15.2 backport does not satisfy the existing v4 ranges.
- **nanoid:** audit `GHSA-2v37-7h3g-55p8`, `<3.3.18`. [3.3.17 release](https://github.com/ai/nanoid/releases/tag/3.3.17) claimed the zero-size fix, but [follow-up source commit](https://github.com/ai/nanoid/commit/e10f8d40ce9d1ab47f66d65a16b48086432730d0), `2026-08-07T15:49:44Z`, fixes the remaining React Native async `customAlphabet` path, returning an empty resolved promise for nonpositive sizes. [3.3.18 release](https://github.com/ai/nanoid/releases/tag/3.3.18), published `2026-08-07T16:35:23Z`, confirms that fix. Registry gitHead: `9ad98052b316c5e707f8098ace509d2ae165e54d`. No maintainer advisory at the supplied GHSA ID was available; release/source evidence supports **3.3.18**.
- **sharp:** [GHSA-rgj7-g3m4-5g8c](https://github.com/lovell/sharp/security/advisories/GHSA-rgj7-g3m4-5g8c), audit `<0.35.4`, published `2026-08-27T09:33:22Z`, updated `2026-09-02T22:17:11Z`, names **0.35.4** with libheif **1.23.2**. Both upstream causes name 1.23.2: [GHSA-g89c-p67h-r497](https://github.com/strukturag/libheif/security/advisories/GHSA-g89c-p67h-r497) (duplicate Alpha-plane overflow; published `2026-08-25T11:17:10Z`, updated `2026-09-03T11:51:24Z`) and [GHSA-2jg2-4ch7-h545](https://github.com/strukturag/libheif/security/advisories/GHSA-2jg2-4ch7-h545) (derived-item/pixel-plane out-of-bounds access; published `2026-08-25T11:19:23Z`, updated `2026-08-25T14:12:58Z`). [sharp v0.35.4](https://github.com/lovell/sharp/releases/tag/v0.35.4), published `2026-08-26T09:38:44Z`, uses [sharp-libvips v1.3.3](https://github.com/lovell/sharp-libvips/releases/tag/v1.3.3), published `2026-08-26T08:26:22Z`, whose dependency table confirms heif 1.23.2. Registry optional binaries advance from 0.35.3 to 0.35.4 and libvips packages from 1.3.2 to 1.3.3; global native-library installations require separate verification. No deployed binary inventory was examined.
- **source-map-js:** audit `GHSA-68fv-2mgg-jv7q`, `>=1.0.0 <1.2.2`. [v1.2.2 release](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2), published `2026-09-30T13:34:23Z`, updated `2026-09-30T13:58:11Z`, explicitly fixes indexed-source-map DoS/CVE-2026-93749 via PR #79. **1.2.2** is the next stable v1 publication; registry gitHead `0a1d334fd1e55a47df97fcd60a7915d46df3b08a`. No maintainer advisory at the supplied GHSA ID was available; release evidence supplies the fix.
- **svgo:** both [GHSA-w27v-7q3p-w38r](https://github.com/svg/svgo/security/advisories/GHSA-w27v-7q3p-w38r) (namespace/control-character links) and [GHSA-4vpr-x523-8j87](https://github.com/svg/svgo/security/advisories/GHSA-4vpr-x523-8j87) (`foreignObject` executable HTML) have audit range `>=4.0.0 <4.1.0`, publication `2026-08-24T14:33:02Z`; updated `2026-09-01T20:46:00Z` and `2026-09-01T20:42:22Z`, respectively. Both name **4.1.0** for v4. [v4.1.0 release](https://github.com/svg/svgo/releases/tag/v4.1.0), published `2026-08-24T11:57:00Z`, confirms both fixes and introduces stricter XML validation plus css-select v6/css-what v7. Malformed inputs previously accepted may now fail parsing; functional verification remains outstanding.
- **smol-toml:** [GHSA-r4xh-jqrq-34v2](https://github.com/squirrelchat/smol-toml/security/advisories/GHSA-r4xh-jqrq-34v2), audit `<=1.8.0`, published/updated `2026-09-22T16:40:12Z`, names **1.9.0** and describes a linear key parser replacing quadratic document rescans. 1.7.2 and 1.8.0 remain within this cause's affected range.

## Verification and remaining work

Read-only checks matched HEAD and locked versions, enumerated registry stable publications, compared all 15 audit ranges, and checked all 13 parent edges: the seven confirmed minima plus the cache candidate satisfy every existing parent constraint and lie outside every supplied range for their package. All 15 supplied cause IDs are present in this note; final checks confirmed unchanged input hashes and HEAD. That numeric result is not a fresh audit or proof of security remediation, especially for the disputed cache entry.

Integration recount confirmed **13**, not 14: devalue 1, http-cache-semantics 1, js-yaml 2, nanoid 1, sharp 1, source-map-js 4, svgo 1, smol-toml 2. The checked inventory is the parent paths/versions and ranges in the table, including `node_modules/csso/node_modules/css-tree` for source-map-js. Counting each parent path, dependency field, and child package once gives 12 `dependencies` edges and one `optionalDependencies` edge (Astro → sharp), with no `peerDependencies` edges. Sharp's two alternative ranges form one constraint on one edge. The earlier 14-edge wording was a counting error, not an additional checked edge; the saved paragraph already read 13 at integration recheck. The lock hash still matches the bound input.

Only this note was authored, using `apply_patch`. No install, audit fix, build, dependency/lockfile edit, Git mutation, provider action, or deployment was performed. Reachability and behavior in Peso, a resulting resolved graph and fresh audit, and native binary contents remain unverified. The main agent must retain the unresolved cache finding and existing treatment expiry/scope when preparing its proposal.
