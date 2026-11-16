# Staging acceptance preflight — November 16, 2026

## Verified provider state

Read-only signed-in browser observations and Supabase catalog queries:

- GitHub Support ticket #4813900 is archived, with the October 8 response
  matching Nathan's supplied text. No message or follow-up was sent.
- GitHub `student` environment still stores `AZURE_SCALER_POSTGRES_CONNECTION`
  and `AZURE_SCALER_POSTGRES_PASSWORD`, both last updated September 10. Values
  were not read. The manual-only historical Azure workflow still references
  them; the Web MVP does not. Both staging and production catalog queries find
  no `peso_azure_scaler_student` role. `analysis_job_scaler` is NOLOGIN,
  non-superuser and cannot bypass RLS. These observations verify the selected
  databases' login state, not erasure of stored credentials or every provider.
- Azure resource inventory could not refresh: CLI authorization is expired/
  revoked (AADSTS50173). No logout, login or Azure change was attempted.
- Fresh Render staging API `srv-dbrrjqjrjlhs73cbn6b0` and worker
  `srv-dbrrjqjrjlhs73cbn6bg` are suspended. Historical pair is also suspended.
  Both fresh services select main, Dockerfile.mvp and Auto-Deploy Off.
  API: 0.5 CPU/512 MB, one instance observed, readiness `/health/ready`.
  Worker: 1 CPU/2 GB, command `python -m app.jobs.analysis_worker`.
  Last successful source for both: a43705709d1c1652bed86ee190a2afdd3ea7fcab.
  Deploy IDs: API dep-dbt4qpec6qcc73ao1u8g; worker dep-dbt4qqrbc2fs73d4agcg.
- Netlify peso-webapp main branch deployment 6afb8106499222f5b51fe231 completed
  from e9370d9f6675be3fe5567043b458ab51afae0933. Successful build/deploy is
  established; app functionality and private-media acceptance are not.

Backend application files differ between the deployed a4370570 source and
current main: phase timing, filename lookup, worker timing and asset handling
changed. Resuming old services alone cannot validate the newer analysis/UI
flow. An approved source-pinned staging deployment is needed after prerequisites.

## Full media test blocker

The current login/recording harness uses main--peso-webapp.netlify.app.
Blueprint and frontend private media flags remain deliberately off for that
smoke-test path. Existing media routes require HTTPS origins beneath usepeso.com,
exact CORS and Strict cookies. Current tests stop at authentication or recording
review and do not establish two-owner upload-to-analysis/media acceptance.

Public DNS and ordinary TLS checks observed:

| Host | Result |
| --- | --- |
| main.usepeso.com | CNAME main--peso-webapp.netlify.app; resolves, but certificate hostname validation fails |
| api-staging.usepeso.com | No DNS answer |
| main--peso-webapp.netlify.app | TLS 1.3 verifies normally |

Netlify's current certificate lists only usepeso.com and www.usepeso.com.
Chrome rejected main.usepeso.com with ERR_CERT_COMMON_NAME_INVALID; no bypass
was attempted. Existing external DNS is Cloudflare (dean/crystal nameservers).
The [Netlify staff guide](https://answers.netlify.com/t/support-guide-how-to-use-netlify-s-branch-deploy-feature-without-netlify-dns/128)
requires a successful branch deploy, correctly named CNAME and a Support request
to extend branch TLS. The first two prerequisites are now observed.

## Prepared Netlify Support request — not sent

Destination: Netlify Support forum, Support category, via the existing account.
The draft contains public site/domain/deployment identifiers only, no credentials.
Sending it requires Nathan's explicit authorization for external communication.

Subject: Extend branch TLS for main.usepeso.com on peso-webapp

Please extend the managed Let's Encrypt certificate for the main branch of
peso-webapp (site ID 230da8eb-f00e-45d4-ba54-95f2e26f21c4, primary domain
usepeso.com) to include main.usepeso.com using the external-DNS branch method.

The main branch deployed successfully: deploy 6afb8106499222f5b51fe231, source
e9370d9f6675be3fe5567043b458ab51afae0933. Its branch URL is
https://main--peso-webapp.netlify.app. Cloudflare DNS currently returns
main.usepeso.com CNAME main--peso-webapp.netlify.app. Ordinary HTTPS validation
fails for main.usepeso.com; the existing certificate lists usepeso.com and
www.usepeso.com only. Please preserve existing access controls and apex/www
routing. We are requesting branch TLS provisioning only, without a DNS migration
or paid-plan upgrade. Please tell us before any paid change would be needed.

## Work after TLS provisioning

1. Verify HTTPS and anonymous protection on the custom branch hostname, including
   direct app/deploy URLs. Do not enable media or provide fixtures beforehand.
2. Prepare the fresh API's api-staging.usepeso.com association and DNS-only
   CNAME to peso-public-beta-staging-api-mo9c.onrender.com. Verify current domain
   allowance/cost before requesting the exact provider/DNS change approval.
3. Prepare consistent staging source guards, Auth/Turnstile redirects, exact
   CORS, public media origin/browser-origin allowlist and frontend/backend flags.
   Keep these pending until both hosts have valid TLS and protected bindings.
4. Quote the existing pair's current rates and a bounded test window, exact
   source and rollback; obtain paid resumption/deployment and fixture approval.
   Historical budget grants do not authorize a new window. No cost is quoted
   here because account-specific rates/allowances have not been verified.
5. Run two-owner auth, upload/analysis, playback, save/export, discard/deletion,
   revoked/expired session and mobile/browser checks. Record queue wait separately
   from processing and repeat the two longest supported clips. Suspend the pair
   after the approved window and retain sanitized evidence.

GitHub CI for code head 889537a8 passed Security Checks run 43971866701 (22
successful jobs; expected production-source skip). Render validation run
43971866556 also passed its Blueprint/runtime job; hosted migration dry run
was skipped and is not acceptance. Gate 2's implemented evidence path works;
remaining hosted release gates are unchanged by these CI results.
