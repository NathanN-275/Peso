# Public resource ID review — Gitleaks v8.30.1

Research for Nathan, 2026-10-05. Recommendation: prefer post-scan classification that retains the original scanner findings over adding a scanner allowlist. This is a source review and decision record, not authorization to implement classification. The active scanner script, workflow, and configuration must remain unchanged.

## Scope and evidence boundary

The supplied review establishes two verified public resource ID occurrences reported as `generic-api-key`, both containing `srv-dak9ohfqj5pc73ac2ga0`:

| File | Reported line |
| --- | ---: |
| `config/combined-web-release-binding.json` | 7 |
| `scripts/release-env.test.js` | 214 |

Their verification is an input from Nathan's review, not an independent provider lookup in this chunk. Render distinguishes the resource identifier in `/v1/services/{serviceId}` from the API key supplied in `Authorization: Bearer …`. Its authentication documentation treats API keys as secret credentials. These sources establish distinct roles, not a universal safety guarantee for strings beginning with `srv-`. [Render service endpoint](https://api-docs.render.com/reference/retrieve-service), [Render authentication](https://api-docs.render.com/reference/authentication).

**No API-auth value is classified as public based solely on an `srv-` prefix, field name, or filename.** Even exact equality with the known ID must be associated with the verified resource-reference occurrence; using that value in an authentication position does not inherit the exception. Other occurrences remain unresolved without evidence of their role. This is the recommended classification boundary; no classifier was implemented here.

## Finding semantics and redaction

All Gitleaks citations below pin `v8.30.1`.

| Field or stage | Source semantics | Decision risk |
| --- | --- | --- |
| `Match` versus `Secret` | `detectRule` initializes both from the full regex match, trimming surrounding LF bytes. Capture extraction then changes only `Secret`: configured `SecretGroup`, otherwise the first nonempty capture. | The token and assignment context are different evidence. [Detector source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/detect.go). |
| `StartColumn` / `EndColumn` | Locations describe the full match, not its secret capture. | Do not locate `Secret` by treating these as secret offsets. [Detector source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/detect.go). |
| Column arithmetic | `location` uses string byte indices: start minus origin plus one; exclusive regex end minus origin. After a newline, the origin is the newline byte itself. | End is inclusive in that coordinate system. A conventional line slice that excludes LF can differ by one; UTF-8 bytes differ from JavaScript string indices. Validate the recovered match, not just the numeric slice. [Location source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/location.go). |
| Redaction order | Capture extraction and entropy checks precede global/rule allowlists; surviving findings reach `filter`. | Scanner allowlisting evaluates original values before report redaction. [Detector source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/detect.go). |
| Report transformation | `filter` applies generic-rule precedence before redaction. `Finding.Redact` replaces occurrences of that finding's secret in `Line` and `Match`, then replaces `Secret`; 100% uses `REDACTED`. Coordinates remain unchanged. `Line` is excluded from JSON. | Redacted text cannot reliably prove exact token equality or preserve match lengths. Retaining scanner output does not recover candidates already filtered internally. [Filter source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/utils.go), [Finding source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/report/finding.go). |

The pinned default `generic-api-key` expression includes assignment context and a captured value, with entropy threshold 3.5. A detection is therefore a heuristic, not provider authentication validation. [Default rule source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/gitleaks.toml).

## Allowlist behavior and same-line risk

- `regexTarget = "match"` selects `finding.Match`; `"line"` selects `currentLine`; default selects `Secret`. Decoded findings can use decoded context and adjusted original spans. [Detector source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/detect.go).
- `condition = "AND"` requires every populated criterion category; omitted condition means OR. Separate allowlist entries remain alternatives: any matching entry suppresses a finding. [Pinned configuration documentation](https://github.com/gitleaks/gitleaks/blob/v8.30.1/README.md), [Configuration parser](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/config.go).
- AND does **not** require all expressions within `regexes` or all paths: each list is combined as alternatives. Regex matching is not implicitly anchored. Stopwords inspect the extracted secret regardless of `regexTarget`. [Allowlist source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/allowlist.go).
- The detector iterates all regex matches. Fingerprints contain file, rule, start line, and optionally commit, but no columns or secret. Thus a fingerprint alone cannot distinguish same-rule findings on one line. [Detector source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/detect/detect.go).

Decision inference: a line regex recognizing the public ID can suppress a separate credential finding sharing that line; AND with a matching path still satisfies both categories. A match target narrows the evaluated text, but does not establish resource semantics or guarantee an unrelated token cannot enter an overly broad expression. Scanner allowlists remove findings from reports, reducing later review evidence. [Allowlist target source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/config/allowlist.go), [Suppression documentation](https://github.com/gitleaks/gitleaks/blob/v8.30.1/README.md).

## Decision and remaining uncertainties

Prefer retaining the unmodified scanner report and adding separate, reversible annotations tied to each finding's verified occurrence. Preserve unresolved findings and the original scan status/counts; a classified resource ID must not clear another finding on its line. Record evidence provenance and scanner version so decisions can be revisited. These are review recommendations, not an implemented design.

Here, “raw findings” means original scanner output before additional classification, including its existing redaction. It does not mean disabling redaction. If exact identity or occurrence cannot be established from authorized evidence, leave the finding unresolved. Unredacted artifacts, if already present, require credential-appropriate access and retention; this chunk neither reads nor creates them. The need for separate evidence follows from the report transformations above. [Finding source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/report/finding.go).

Unverified here: the active binary/build options and effective configuration; actual report columns/redaction for the two occurrences; provider verification provenance beyond the supplied facts; and classifier handling of newline, UTF-8, decoded, multiline, or ambiguous same-line matches. The source includes alternative regex backends selected by build tags. [Standard backend](https://github.com/gitleaks/gitleaks/blob/v8.30.1/regexp/stdlib_regex.go), [RE2 backend](https://github.com/gitleaks/gitleaks/blob/v8.30.1/regexp/wasilibs_regex.go).

Only this document was written, using `apply_patch`. No credentials, provider exports, untracked notes, production/provider state, or local fixtures were read or tested. The main agent's private post-scan prototype testing remains separate. No scanner/workflow/config changes, classification implementation, commit, push, or deployment occurred. Shell DNS blocked source retrieval; the official web tool supplied the primary sources.
