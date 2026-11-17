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

## Dedicated staging checkpoint

Nathan selected the owner-only Netlify Free project `peso-staging-web` and
the fresh Render staging pair above. At 8:53 PM Eastern on November 16,
Netlify reported all-deploy sign-in protection, zero deploys and no linked
Git repository. Hosted content protection still needs to be tested after an
approved upload.

| Host | Current result |
| --- | --- |
| `staging.usepeso.com` | CNAME resolves to `peso-staging-web.netlify.app`. Netlify reports no installed certificate and ordinary HTTPS fails hostname verification. |
| `api-staging.usepeso.com` | CNAME resolves to the selected Render API. Ordinary HTTPS verifies and returns HTTP 503 while the API is suspended. |

The custom Netlify project domain replaces the historical branch-TLS path.
Ticket #1196583 below records work on `main.usepeso.com`. Dedicated staging
depends on the certificate for `staging.usepeso.com`.

Nathan approved a first-window scope of owner-only access, real Auth and
API readiness with media disabled. He selected a private static holding
page as the frontend rollback target. Its archive is prepared locally.
Timing, provider changes, uploads, paid compute and fixtures require
separate approval.

1. Verify ordinary HTTPS on the custom Netlify hostname. Obtain approval
   for the holding-page upload, then verify owner access, anonymous denial
   and the deploy ID before using it as a rollback target.
2. Finalize and verify the dedicated staging binding, exact Auth redirects,
   Turnstile and CORS. Run the committed-source and history checks against
   the final candidate. Keep API, worker and frontend media disabled.
3. Obtain approval for the bounded window, pinned deployment, fixtures and
   cleanup. Verify service and artifact identity, readiness, CORS,
   owner-only access, real email and CAPTCHA, and required browser checks.
   Reconcile fixtures and confirm worker and API suspension by the deadline.
4. Run two-owner media acceptance in a later approved window after provider
   settlement, scoped owner cleanup and hosted-role rehearsal pass. Capture
   queue wait and processing separately for the two longest supported clips.

## Historical staging observations

Backend application files differ between the deployed a4370570 source and
current main: phase timing, filename lookup, worker timing and asset handling
changed. Resuming old services alone cannot validate the newer analysis/UI
flow. An approved source-pinned staging deployment is needed after prerequisites.

### Earlier branch-host TLS blocker

The earlier login/recording harness used main--peso-webapp.netlify.app.
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

### Netlify Support request — submitted, ticket #1196583

Nathan explicitly authorized sending this request on November 16. It was
submitted through Netlify's direct support form under Something else, using the
existing account's contact identity and the exact subject/body below. The forum
SSO screen requested project-management access despite narrower description
text; that authorization was left untouched. The direct form avoided that grant.

Netlify's `/support/thanks/` page confirmed receipt. The reply email assigned
ticket **#1196583**, accurately summarized the TLS-only request and asked for
confirmation before routing to an agent. Sent the routine confirmation reply:
“Yes, this is correct. Please route this TLS certificate request to an agent.”
Gmail displayed Message sent. No duplicate forum topic was posted.

At submission, the agent response and branch TLS provisioning were pending.
The submission confirmation screenshot is retained outside Git in the chat's
visualization directory as `netlify-support-submitted.jpg`.

Submitted subject and body:

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

## Historical CI checkpoint

GitHub CI for code head 889537a8 passed Security Checks run 43971866701 (22
successful jobs; expected production-source skip). Render validation run
43971866556 also passed its Blueprint/runtime job; hosted migration dry run
was skipped and is not acceptance. Gate 2's implemented evidence path works;
remaining hosted release gates are unchanged by these CI results.
