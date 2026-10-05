# Dependency audit primary-source recheck — 2026-10-05

Research sidecar for Nathan's evidence-bound audit-treatment review. Recommendation: classify the installed changes as **Peso-maintained, scoped security backports with recorded local evidence**. Neither upstream package has a registry release identified as patched for these advisories at this observation. Preserve the raw findings and evaluate any future treatment against exact artifacts and every applicable cause. This note grants no exception or release approval.

## Observation boundary and method

The environment date is **2026-10-05**, America/New_York. The clock returned `2026-10-05 20:03:16 UTC`; direct public-source observations below occurred at `20:04:24–20:04:55 UTC` (16:04 EDT). These are retrieval times, distinct from publication, update, and closure timestamps supplied by sources. Findings describe the returned snapshot, not future source status.

GitHub pages were checked with the web reader. Registry packuments, GitHub REST metadata, and official documentation source were subsequently read with credential-free Node `fetch` GET requests. No npm command, local npm configuration, credential file, authentication token, or package-install lifecycle was used. Initial sandboxed registry requests failed DNS resolution and supplied no evidence; the subsequent public GETs succeeded. The web reader also could not open the braces registry URL; its registry facts below come from the successful direct request. Only this Markdown note was written. No application tests, audit command, code/policy edits, commit, push, or deployment were performed.

Local assessment/installation notes were read as historical context. Their reported checks were **not independently rerun** here. The main review separately owns current installed-byte verification, audit graph, and consumer/build-path evidence.

## Registry versions and distribution tags

The complete returned `versions` keys were examined, including prereleases, rather than relying only on the `latest` tag.

| Public primary source | Observed at (UTC) | Complete returned `dist-tags` | Highest version present | Version publication time (`time[version]`) | Packument `time.modified` |
| --- | --- | --- | --- | --- | --- |
| [braces packument](https://registry.npmjs.org/braces) | `2026-10-05T20:04:24.849Z` | `{"latest":"3.0.3"}` | `3.0.3` | `2024-05-21T08:59:11.390Z` | `2024-09-18T05:27:12.449Z` |
| [node-forge packument](https://registry.npmjs.org/node-forge) | `2026-10-05T20:04:24.842Z` | `{"latest":"1.4.0"}` | `1.4.0` | `2026-03-24T21:44:34.668Z` | `2026-03-24T21:44:34.780Z` |

No version above either stated maximum appeared. In particular, Forge `1.4.1` and `1.4.1-0` were absent; development metadata or a proposed changelog entry is not evidence of npm publication. npm defines distribution tags as aliases for versions; default unqualified installation selects `latest`. A tag is not a security certification, and it need not establish the highest published version by itself. [Official npm dist-tag documentation](https://docs.npmjs.com/cli/v11/commands/npm-dist-tag/), [documentation source retrieved at `2026-10-05T20:04:55.338Z`](https://raw.githubusercontent.com/npm/cli/latest/docs/lib/content/commands/npm-dist-tag.md).

Published artifact identity returned by the registry, recorded without downloading or verifying tarballs:

| Version | `dist.tarball` | `dist.integrity` |
| --- | --- | --- |
| `braces@3.0.3` | [braces-3.0.3.tgz](https://registry.npmjs.org/braces/-/braces-3.0.3.tgz) | `sha512-yQbXgO/OSZVD2IsiLlro+7Hf6Q18EJrKSEsdoMzKePKXct3gvD8oLcOQdIzGupr5Fj+EDe8gO/lxc1BzfMpxvA==` |
| `node-forge@1.4.0` | [node-forge-1.4.0.tgz](https://registry.npmjs.org/node-forge/-/node-forge-1.4.0.tgz) | `sha512-LarFH0+6VfriEhqMMcLX2F7SwSXeWwnEAJEsYm5QKWchiVYVvJyV9v7UDvUv+w5HO23ZpQTXDv/GxdDdMyOuoQ==` |

These registry fields identify published archives; they do not attest that locally modified installed files equal those archives.

## Advisory status

GitHub's reviewed advisory pages and REST records agree on the following ranges and lack of a patched version:

| Advisory / CVE | npm package and affected range | Patch / withdrawal fields | Source publication time | Source update time | API retrieval time |
| --- | --- | --- | --- | --- | --- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), `CVE-2026-93687` | `braces`, `<= 3.0.3` | `first_patched_version: null`; `withdrawn_at: null` | `2026-09-18T18:31:41Z` | `2026-10-02T22:36:34Z` | `2026-10-05T20:04:54.399Z` |
| [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv), `CVE-2026-85393` | `node-forge`, `<= 1.4.0` | `first_patched_version: null`; `withdrawn_at: null` | `2026-09-03T21:31:15Z` | `2026-10-01T21:09:10Z` | `2026-10-05T20:04:54.612Z` |

API provenance: [braces advisory record](https://api.github.com/advisories/GHSA-vfj7-8cjw-p6xm), [Forge advisory record](https://api.github.com/advisories/GHSA-86w9-cpqp-85rv). Both pages show High severity. Braces concerns recursion through deeply nested patterns. Forge concerns extra nested DigestAlgorithm elements during RSA PKCS#1 v1.5 verification with low-exponent keys and describes an incomplete earlier fix. Neither advisory supplies a comprehensive safety claim for a locally modified artifact.

## Upstream proposal status and immutable provenance

| Proposal | Direct API observation | Head SHA | Base SHA |
| --- | --- | --- | --- |
| [micromatch/braces #72](https://github.com/micromatch/braces/pull/72), author `FSDevelop` | `state: closed`, `merged: false`, `merged_at: null`; retrieved `2026-10-05T20:04:25.010Z` | `28d440b5dd449dbf1fe6f3506cf94ecca4d02660` | `e53730e6f935498326c72d768889ac194eedc0e0` |
| [digitalbazaar/forge #1152](https://github.com/digitalbazaar/forge/pull/1152), author `Krysthyan` | `state: open`, `merged: false`, `merged_at: null`; retrieved `2026-10-05T20:04:25.034Z` | `ceba34402e329f0365134f23fe19898756527d65` | `7a43db987bd0ecdc5b41f6d73f58ba6ca5bf9ae1` |
| [digitalbazaar/forge #1157](https://github.com/digitalbazaar/forge/pull/1157), author `itsalexfer` | `state: open`, `merged: false`, `merged_at: null`; retrieved `2026-10-05T20:04:25.060Z` | `683ab3344899cc08a581e4d5675a33e87aff7b04` | `723240415b25120d47146f982809fa69344ab890` |

API provenance: [braces #72](https://api.github.com/repos/micromatch/braces/pulls/72), [Forge #1152](https://api.github.com/repos/digitalbazaar/forge/pulls/1152), [Forge #1157](https://api.github.com/repos/digitalbazaar/forge/pulls/1157).

- Braces #72: created `2026-09-21T09:55:48Z`, closed `2026-10-05T06:43:43Z`, updated `2026-10-05T13:40:19Z`. Its description proposes bounded parsing/AST depth and parent-cycle checks. This establishes that the PR was not merged; it does not establish whether code was adopted by another route, the author's account of maintainer motives, or rejection of every possible remedy.
- Forge #1152: created `2026-09-09T21:39:06Z`, updated `2026-10-02T08:20:43Z`, `closed_at: null`. It proposes an explicit nested element-count check. The [reviews API](https://api.github.com/repos/digitalbazaar/forge/pulls/1152/reviews), retrieved `2026-10-05T20:04:54.873Z`, returned review `5389656054`: `fpusset`, `APPROVED`, `author_association: NONE`, submitted `2026-10-02T08:20:43Z` against the listed head. This documents an approving review, not demonstrated maintainer acceptance or a merged release.
- Forge #1157: created and updated `2026-10-04T08:09:28Z`, `closed_at: null`. It builds on #1152 and adds rejection of nonempty captured NULL contents. The [files API](https://api.github.com/repos/digitalbazaar/forge/pulls/1157/files), retrieved `2026-10-05T20:04:55.102Z`, lists `lib/rsa.js` and `tests/unit/rsa.js`. Its description explicitly distinguishes synthetic private-key malformed-encoding fixtures from forgery without a private key. Contributor test reports remain reports, not independently repeated tests in this sidecar.

None of these status records establishes an official patched release. Repository PR status, registry publication, local backport effectiveness, and application exposure are separate questions.

## Scoped backport classification

The [initial assessment](dependency-security-blocker-20261004.md) records a narrow braces backport of five `lib/` changes from the stated candidate onto published 3.0.3, excluding unrelated unreleased base-branch changes. The [initial installation note](dependency-patch-installation-20261005.md) records installation while retaining version identity and audit findings. Some earlier assessment paragraphs say the proposals were open; those are historical observations, superseded for present PR status by the dated API recheck above.

The [supplemental Forge assessment](forge-null-backport-assessment-20261005.md) and [installation note](forge-null-backport-installation-20261005.md) record the combined element-count/NULL-content backport onto `node-forge@1.4.0`. The latter reports these SHA-256 values:

| Reported local artifact | SHA-256 from installation note |
| --- | --- |
| Braces patch | `e07abe26dbd330daea0e448ca1382327322dd5eccc08c5dd1a9b9f7bf5a6d699` |
| Combined Forge patch | `be39d6da41ca04aed6ae697f65000184083b8a4c1b9874ab759fd2cfd4dc70fe` |
| Installed Forge `lib/rsa.js` | `22cdfb3220439533211cf00ff7c7e6605607761d77a2c3c263411d4c70798c4f` |
| Manifest / installer trust anchor | `1bae92dd0779b9cd026754c599c47508fd49f36a36c2c3decf07325f6728b6b0` |

These are transcribed evidence pointers, not fresh hash verification. The installation note explicitly excludes Forge's unchanged, unpatched `dist/` bundles from its fixed-artifact scope and reports the unchanged audit gate failing. The earlier element-count-only hash `acc22e5d36e27832c34e02dd3933aad7977d45b047eead5016520735efedc9c5` is historical evidence, not the supplemental installed target.

Interpretation: “backported remediation for the assessed recursion and DigestAlgorithm cases, limited to verified runtime paths and tested behavior” is defensible conditional wording. “Comprehensive fix,” “upstream accepted,” “official patched version,” and “all HIGH findings resolved” exceed this evidence. Local ownership remains with Peso, including reproducibility, installation enforcement, compatibility, coverage gaps, and retirement when an official fix is verified.

## Why npm can still report these packages and their parents

Official npm documentation describes Bulk Advisory requests as package names plus version lists, matched against advisory ranges. Quick Audit fallback submits the lockfile tree and environment metadata. npm derives meta-vulnerabilities when dependency ranges require vulnerable versions, caches them, and reevaluates when advisory ranges change or new versions are published. `--audit-level` changes the failure threshold, not report contents. [npm audit documentation](https://docs.npmjs.com/cli/v11/commands/npm-audit/), [official documentation source retrieved at `2026-10-05T20:04:55.237Z`](https://raw.githubusercontent.com/npm/cli/latest/docs/lib/content/commands/npm-audit.md).

Inference for this review: patching bytes while retaining `braces@3.0.3` and `node-forge@1.4.0` does not change those documented version inputs. Continued leaf and parent findings are therefore compatible with effective scoped patches. They neither disprove patch effectiveness nor certify it. Parent entries can represent inherited causes; each relevant cause still needs inspection before treatment. No current graph/count, cache diagnosis, or exact npm 12 implementation behavior was independently verified here; v11 web docs and the mutable official `latest` source were explanatory sources.

Any future project-policy acceptance should retain the raw registry report, distinguish its own decision from npm's classification, and bind treatment to installed-byte/identity verification, artifact and consumer scope, advisory identity, and a dated review/retirement condition. This is a recommendation for the main review, not a policy edit.

## Optional VEX framing

The first-party [OpenVEX specification](https://github.com/openvex/spec/blob/main/OPENVEX-SPEC.md), [raw source retrieved at `2026-10-05T20:04:55.556Z`](https://raw.githubusercontent.com/openvex/spec/main/OPENVEX-SPEC.md), binds statements to products, vulnerabilities, statuses, and timestamps; products can carry hashes. `fixed` describes product versions containing a fix. `under_investigation` applies when impact is unknown. `not_affected` requires a justification or impact statement. Its execution-path and inline-mitigation justifications require stronger evidence than a passing regression alone; inline mitigation must prevent known-vector exploitation without user disabling or attacker subversion.

Interpretation: an artifact-specific backport statement need not await upstream release, but must identify the actual modified product. Using only the ordinary npm name/version risks conflating patched and original artifacts. Exclude or separately assess unpatched Forge bundles. Do not issue `fixed` for the entire application or `not_affected` solely because selected tests pass. VEX describes impact; it does not automatically change npm audit's documented inputs or approve a release. No VEX statement is issued by this note.

## Recommendation to the main review

Keep the current security gate status until Nathan's separate policy decision. Use these primary-source snapshots to support a narrowly scoped treatment proposal only after current artifact hashes, installed inventory, every advisory cause, and actual consumers/build outputs are verified. Record uncertainty and unresolved artifacts explicitly. Prefer a verified official patched release to retire the backports; recheck both registry metadata and advisories at that time. This sidecar establishes source status and classification boundaries, not comprehensive remediation or deployed exploitability.
