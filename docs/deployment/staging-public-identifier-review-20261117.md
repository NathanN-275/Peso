# Exact dedicated-staging binding occurrence review — November 17, 2026

Nathan's approved owner-only staging plan requires using the existing exact-occurrence review for verified Render ID findings. This review applies that established mechanism to one finalized dedicated staging binding occurrence. It does not add a prefix, rule, file or environment allowlist, and does not refresh any earlier pin.

The Render dashboard identifies the selected suspended API as srv-dbrrjqjrjlhs73cbn6b0. Its retained deployment is dep-dbt4qpec6qcc73ao1u8g, source a43705709d1c1652bed86ee190a2afdd3ea7fcab. The binding's API field holds that service identifier, which locates the service and does not authorize access. The selected worker is separately verified. No credential value qualifies through this review.

| Exact archived occurrence | Pin |
| --- | --- |
| File | config/staging-web-release-binding.json |
| Rule / scanner | generic-api-key / Gitleaks 8.30.1 |
| Line and columns | line 9, columns 5–47 |
| Complete file SHA-256 | d47124051176287bd2ba081162c350902fbf148a7b9a3c70e5b668cbe9ba3e65 |
| Exact source line SHA-256 | 247ff2f461b42d8eca2c173eac91fac5a8140cc5da4908fa2865947d530b8d42 |
| Redacted assignment | api_service_id": "REDACTED" |
| Classification | reviewed-public-resource-id |

The complete binding bytes include the real dedicated Netlify UUID, verified staging public-key and Turnstile site-key fingerprints, exact staging origins, and private-config-verified status. Provider receipts establish both TLS certificates, owner access, anonymous denial, matching staging CAPTCHA secret, exact Auth redirects and saved CORS/origin settings. API, worker and frontend media remain disabled. Configuration attestation is separate from hosted acceptance.

The existing matcher still requires the archived file and line hashes, exact scanner version, rule, line/columns, redacted assignment, redacted secret, empty tags and empty symlink field. Any change to the binding requires another review. Credentials substituted for the ID, copied occurrences, credential-field reuse and unrelated file edits stay blocking.

Retain the raw scanner exit and sanitized report. Acceptance must remain separately labeled accepted-with-reviewed-nonsecret-findings, never clean. The integration checks exercise the real scanner and archive for the new accepted occurrence and those four blocking controls, in addition to existing metadata corruption and coverage controls.

A Git history finding requires its own commit-specific fingerprint after the introducing commit exists. Record that exact historical occurrence in a follow-up commit; do not invent a fingerprint for a future SHA or suppress an entire path. Both history and exact-source checks must pass on the final reviewed source. This review authorizes no provider write, source publication, deployment, fixture write, compute resumption or media activation.


## Public-fingerprint extension — approved November 17

After finalizing the verified binding, Gitleaks also reports its public
Turnstile site-key SHA-256 on line 12, columns 5–98. This was not present while
the binding value was null. It is a fingerprint of the public site key, not a
Render ID or a source revision, so the existing two classification names do
not describe it. Nathan's Render-ID instruction alone is not credited as
approval for the additional classification.

The proposed policy adds reviewed-public-key-fingerprint for only this pinned
occurrence. It matches the same complete file SHA-256 above and exact line
SHA-256 2eb82450c4f118d00057e8433a404fe104f6a79bd33e74b6952c5cb7b8c5052a.
The exact redacted assignment is turnstile_site_key_sha256": "REDACTED".
The fingerprint is 729289ff12a9eed800320f0f582b9844c090082ecfec0a4b18947634e11320d3,
independently recalculated from the public widget site key
0x4AAAAAAEucSyDahQEkwtRY displayed in the selected widget's dashboard.
Neither this value nor that public site key authenticates server-side CAPTCHA
verification. The distinct private secret was compared privately and is absent
from this record.

Two lines in the same binding require selecting pins by file and line, rather
than choosing the first pin for a file. Exact columns, hashes, rule, scanner,
redaction, tags and symlink validation remain unchanged. Classification lookup
uses the same file and line. Duplicate reported occurrences still block.
The new classification is explicitly validated in both matching and counting;
unknown values fail closed.

The proposal includes real-Gitleaks tests for exact acceptance, ID and fingerprint
credential substitution, unrelated byte edits, copied paths, credential-field
reuse and unsupported fingerprint classification. Preserve the initial failed
scan as evidence that the new fingerprint remained blocked before this proposal.

Do not credit the proposed scanner acceptance to release readiness until Nathan
approves this exact extension and its patch. This approval would authorize local
policy/test/document changes only, not publication, provider writes, a deploy,
fixtures, compute or a window.


## Approval record

Nathan explicitly approved the exact local scanner proposal on November 17,
including the public-key-fingerprint classification, two pinned lines in one
binding and only the two actual historical fingerprints for introducing commit
c805784e16d3ea2ac07915d917446ffd1fb0f2ab at binding lines 9 and 12.
The reviewed proposal patch SHA-256 is
a77350cf1008f44f12e20d72ac5c84b3e9aa7864806281ae2edef362b73b4747.
The initial pending-authority scans remain prototype evidence. Fresh scans
after this approval and the follow-up history commit are the release results.
This approval is local and does not authorize source publication or provider,
deployment, fixture, compute or window actions.
