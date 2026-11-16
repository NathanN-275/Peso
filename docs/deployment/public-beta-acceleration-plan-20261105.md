# Public Web Beta Acceleration Plan

**Prepared:** November 5, 2026
**Release source:** managed `public-web-beta` worktree at `/Users/nathan/.codex/worktrees/public-web-beta/peso-app`, branch `codex/public-web-beta`
**Status:** Execution in progress; public beta remains blocked. This plan does not authorize deployment, paid service resumption, merge, or public exposure.

**November 9 isolated migration rehearsal passed:** Nathan separately approved the exact 30-file pending chain on recovery target `uhivjkfpfqtpicyjtmie`. CLI application exited zero at `22:51:37.932814Z`. Readback confirms all 51 expected versions/names through `20261103022851`, all 33 original rows' values preserved, expected profile revision/owner backfill and disabled control rows, all 20 public tables with RLS, reviewed client grants, unchanged buckets/old public counts and zero objects. Full schema capture is 275,604 bytes, SHA-256 `ea42ef016c02892c3059bb4860205d9620b75efb55fcb85c56bdd5146ad32c6c`. Post-migration dashboard readback confirms signup/manual linking/anonymous sign-ins/Data API disabled. Production history remains its original 21 versions/content. No production application, new test accounts, API activation, paid-plan change or project pause occurred. [Rehearsal result, diagnostics, advisor observations and remaining scope](pesodatabase-migration-rehearsal-20261109.md). Fresh cutover recovery evidence and separate production approval remain required.

**November 9 current result:** Nathan's separately approved deletion of the two exact tagged synthetic recovery accounts is complete. Auth Admin identity checks/deletes/readbacks and SQL verification passed: no synthetic users, sessions, refresh records, identities or MFA factors remain; all 33 original rows and schema/grants are unchanged. Fresh dashboard readback confirms signup/manual linking/anonymous sign-ins/Data API disabled. Recovery is retained active and isolated; no project pause or capacity change is approved. [Recovery result](pesodatabase-hosted-recovery-rehearsal-20261108.md).

**November 9 migration preparation:** Supabase CLI 2.98.2 linked dry runs passed against production at 22:31 UTC and recovery at 22:37 UTC, each listing exactly the same 30 pending files from the 51-file byte-pinned Web MVP selection. Temporary, separately linked evidence workspaces preserve the source checkout and immutable production manifest. Production history/content and counts were unchanged after its dry run; recovery still has 21 versions ending `202608270001`. No SQL migrations were applied. The target-specific isolated rehearsal action packet is prepared under the chat evidence directory's `recovery-migration-rehearsal-20261109/`; applying its exact chain to recovery requires separate approval. Production application still requires fresh cutover recovery evidence and its own approval. Dry-run safety comes from the reviewed pinned CLI branch, not database startup read-only enforcement.

**November 9 protected-release readback:** GitHub's active `Protect production` ruleset `22210122` targets only `production`, requires a pull request and nine up-to-date checks, blocks deletion/force pushes, and has no bypass actors (`current_user_can_bypass=never`). Its required review count is zero; this does not replace Nathan's release approval. The seven internal required check names all exist in the candidate security workflow. Its required `reservation-database-security` job always evaluates the private-media matrix result and fails unless it succeeds, so no rule removal/addition is needed merely to cover that matrix. The two external required contexts still name the historical `peso-webapp` and `peso-marketing` projects; neither establishes the combined project's check identity or artifact. Remote `main` remains `98bad175cf2025741632244f4dd2da6b9866f87f`, `production` remains `d92dfea5334d338cf7af842f0d1b3672ca3d1cc9`, and there are no open production-target PRs. The candidate `b141cf205152f9c1142d60fba2e0ba2aac01d363` check lookup returns 422, commit not found; no hosted check acceptance exists for it. Keep existing protections intact. Receipt: `github-release-protection-readback-20261109.json` in the chat evidence directory. No push, PR, ruleset change or merge was performed.

Earlier dated updates below are historical checkpoints. The current result above and gate table supersede their pending/blocked statements; original failures remain preserved.

**November 8 hosted API verification:** Nathan approved the two-owner Auth/Storage suite. Exactly two synthetic accounts were created without emails; password identity/session checks passed. The first attempt retained an immediate overwrite-read checksum failure after 23 passing checkpoints. Read-only review confirmed all original rows intact and later fixture reads matched; the same suite continued with the same two subjects using documented cache-nonce fresh reads and no settings/policy changes. Its 114 checks completed owner CRUD/isolation, service checks across three buckets and four downloaded-backup/delete/restore byte round trips. All 33 original rows, schema/grants, policies/buckets/history and public counts remain unchanged; current objects are zero. Total Auth/Storage requests: 160 including diagnostics. Signup/anonymous/manual linking/Data API remain disabled after dashboard reloads. Two synthetic accounts and two sessions await separate cleanup approval. [Evidence and retained failure/limits](pesodatabase-hosted-recovery-rehearsal-20261108.md). Immediate unversioned-cache coherence, physical provider-byte erasure, fresh production cutover backup and candidate E2E remain unproven; Gates 6/9/12 are not waived.

**November 8 grant repair passed:** Nathan separately approved the prepared permission correction on recovery target `uhivjkfpfqtpicyjtmie`. It committed at 11:27 PM Eastern after pre-commit grant/data/policy checks. Full schema readback now matches the immutable snapshot after blank-line normalization (digest `537346c393ff3cc1e7182bbb3711cfedf9c5b193f5f8a81ee1548a85a78d955e`); full data SQL matches after the recorded blank/comment normalization. Non-client/default privileges, data and policies/history remain unchanged. Post-repair dashboard reloads confirm signup/manual linking/anonymous sign-ins/Data API remain disabled. The earlier grant mismatch is preserved as a counterexample and is resolved on this target. A separate real Auth/Storage test packet is prepared with two synthetic accounts and five tiny offline fixtures; no real API test or account cleanup has been authorized or executed. [Current restore and repair result](pesodatabase-hosted-recovery-rehearsal-20261108.md).

**November 8 approved restore result:** Nathan approved restoring the verified snapshot into recovery target `uhivjkfpfqtpicyjtmie`. The data/history transaction and guarded eight-policy transaction committed at 11:09 PM Eastern. All source counts, private INSERT values/sequence statements, 14 policies, bucket metadata and 21 migration rows match. A full application-schema read-back found extra `anon`/`authenticated` grants on twelve functions and five tables; all other exported application definitions match. Further writes stopped. Signup and Data API were rechecked disabled after restoration. Hosted recovery remains **unaccepted** pending separately approved grant repair and subsequent hosted behavior tests. A narrow 34-revoke/three-source-grant transaction is prepared, not executed. See [the restore result and counterexample](pesodatabase-hosted-recovery-rehearsal-20261108.md). Production, staging, old recovery and HootRoute were not restore targets; the original backup is unchanged.

**November 8 protected-copy verification passed:** Nathan attached the downloaded Proton archive, resolving the macOS content-access dependency. It is exactly 51,074 bytes with SHA-256 `8d7cb655997b7c1ab579f99825b11d3aab93f36bdbf9d5de58ac0d4beaa00ea7`, byte-identical to the original. All ten internal files match the original snapshot and all six SQL manifest checks pass. Protected off-device copy verification is now **true for this November 6 rehearsal snapshot**; the expired freeze still requires fresh production cutover evidence. Receipt: `proton-current-archive-verification-20261108.json` in this chat's private evidence directory.

Before restore approval, fresh provider/dashboard readback confirms the organization remains Free, target `uhivjkfpfqtpicyjtmie` remains healthy/empty, and signup/manual linking/anonymous sign-ins/Data API remain disabled. The current provider new-project quote is $0/month; the proposed restore uses the existing target without a paid-plan change. Its dashboard-confirmed session pooler is `aws-0-us-east-1.pooler.supabase.com:5432`, distinct from production's `aws-1` route. A target-specific TLS `verify-full` read-only connection passed at `2026-11-09T03:59:15.443539Z`; zero users/sessions/buckets/objects/public relations and no migration history were independently rechecked. The initial direct-route CLI template was retained privately; route assertions stopped before connecting, then the explicitly verified session-pooler route passed. The complete target-specific restore packet is ready for separate approval, with no private data restored and no hosted settings changed during this verification.

**November 8 current update:** Nathan manually uploaded `peso-recovery-20261106-private.tar.gz`. The exact file is now present in Proton Drive's **My files** root; its sharing panel lists Nathan as the only owner and Public link **Not active**. Proton reports **1 of 1 transfers completed** and the exact filename **Downloaded**. The browser download event timed out, but the completed UI state was inspected instead of restarting the transfer. The saved file exists at `/Users/nathan/Downloads/peso-recovery-20261106-private.tar.gz` and is 51,074 bytes. macOS denies content reads, including an escalated exact-file read, so archive/internal checksums and protected-copy verification remain **pending**. Chrome's download-history URL is blocked by browser URL policy; no workaround was attempted. The user must attach the downloaded copy or move it into an accessible private directory. Existing source bytes are not a substitute for verifying the downloaded copy. Receipts/screenshots: `proton-transfer-observed-20261108.json`, `proton-current-archive-private-20261108.jpg`, and `proton-current-archive-downloaded-20261108.jpg` in this chat's private evidence directory. The earlier missing-upload blocker is resolved; the remaining dependency is access to the actual downloaded bytes.

Read-only recovery revalidation at `2026-11-09T03:37:37.141061Z` (November 8 Eastern) confirms target `uhivjkfpfqtpicyjtmie` remains `ACTIVE_HEALTHY` with zero Auth users/sessions, buckets/objects, public relations and Storage object policies, and no migration-history relation. A target-specific restore action packet with pinned inputs, transaction boundaries, expected counts, stop conditions and retention limits is prepared privately under `restore-preparation/hosted-restore-action-packet-20261108.md`. It is neither approved nor executed. Protected-copy verification, fresh isolation/cost/connection checks and separate restore approval remain required. The November 6 writer freeze remains expired; no production cutover recovery point or hosted acceptance is claimed.

**Renewed goal block, November 8:** After the user-confirmed permission setting still produced a failed chooser upload, Nathan resumed the goal again. Three consecutive resumed turns have reached the same dependency without a changed browser/upload-state answer or downloaded-copy path. The last recorded transfer failed, no transfer process remains live, and protected-copy verification is false. Do not repeat the same failed upload or infer that enabling the goal changed browser permissions. The existing upload approval persists; continue when the browser connection/permission state actually changes or a protected downloaded copy is supplied. The full public-launch objective remains incomplete.

**November 8 upload retry:** Nathan confirmed the file-URL setting is enabled and directed the already-approved upload to continue. The exact local archive still matches its approved size/hash. Destination sharing was rechecked: owner only, public link inactive. The documented file-chooser retry again failed because the extension reports local-file URL access unavailable. The controlled browser identifies its profile as `Person 1`; the reason for the mismatch with the user's setting is unknown. The loaded folder still contains only the historical files, with no new archive. No protected copy or downloaded-copy verification is claimed. The tab is retained for a user handoff; do not bypass the upload control or the internal-URL policy. Receipt: `proton-upload-retry-20261108.json` in the current evidence directory.

**Execution blocked, November 8:** The resumed run reached the same protected-copy/upload dependency across three consecutive goal turns. The approved Proton destination was fully loaded and inspected again; it contains the seven historical files and not `peso-recovery-20261106-private.tar.gz` (receipt `proton-backup-presence-20261108.json`). Chrome's internal extension-settings URL is blocked by browser URL policy, so the agent cannot verify or change that permission through an alternate surface. No user confirmation that “Allow access to file URLs” is enabled, and no manually downloaded-copy path, has arrived. The exact archive upload/download approval remains valid, but execution cannot advance safely until that prerequisite changes. No upload retry, hosted restore or release action was performed in this audit. The November 6 freeze remains expired; the complete public-launch objective is unachieved.

**November 6 update at 9:12 PM Eastern:** Nathan resumed the goal, explicitly authorized scoped Proton account/Drive inspection, then separately authorized uploading the exact private archive to the existing owner-only backup folder and downloading it for verification. Exact-name search found no current archive. Folder access readback lists only Nathan as owner and public link inactive. The approved upload was attempted through the browser's file chooser, but `setFiles` was blocked because the ChatGPT Chrome extension lacks “Allow access to file URLs”; no uploaded archive is shown. The destination tab is retained for the user handoff. The 60-minute source writer-freeze authorization expired at 9:09:20 PM Eastern; no extension was granted. The exported snapshot remains preserved for rehearsal, but is not a current cutover recovery point. Private-data restore is still unauthorized and unexecuted.

**Execution blocked, November 6 at 8:43 PM Eastern:** The local backup bundle still matches its verified hash, but no downloaded protected-copy path or off-device verification has been supplied. This dependency has persisted across more than three consecutive goal turns while independent authorized preparation was completed. Automated Proton inspection was denied for broader account-origin access; manual protected-copy verification is the available route. No hosted restore is authorized. Current readback confirms HootRoute `INACTIVE` and the recovery target `ACTIVE_HEALTHY`; signup and Data API restrictions were saved/reload-verified earlier. The writer-freeze authorization expires at 9:09:20 PM Eastern and is not extended by this blocked state. Recovery/migrations and their dependent cutover gates cannot advance without the protected copy, subsequent restore approval and hosted acceptance; final public launch remains unachieved.

**November 6 update:** Computer Use now works. Dashboard-confirmed session pooler `aws-1-us-east-1.pooler.supabase.com:5432` passed hostname/TLS and read-only authentication checks using the retained Supabase CA. Nathan confirmed all writers stopped for a 60-minute window recorded as 8:09:20–9:09:20 PM Eastern. All six logical dumps succeeded at 8:10 PM, independent hashes/private permissions passed, and before/after counts matched. The local archive is verified; protected off-device copy and Hosted Restore Rehearsal remain pending. No migration, service resumption, merge or public transition has occurred; all release requirements remain in force.

## Objective and scope

Reach the earliest safe public launch of the Peso Web Beta while retaining every mandatory gate in the [Public Web Beta Deployment Plan](public-beta-launch-plan.md) and [Production Readiness Review](../product/PRR.md). The release includes the combined homepage and authenticated `/app`, US-only signup and upload admission, and supported side-view squat workflow. Existing production data and projects remain preserved.

The completion condition remains: all 14 release gates have current, candidate-matched evidence; the public release is authorized and exposed; public smoke checks pass; and first-cycle monitoring begins. A faster schedule comes from collecting fresh evidence, eliminating duplicate work only when identities and coverage match, and running independent preparation tracks concurrently. No gate is waived or inferred from an old status summary.

## Evidence rules

1. Reinspect current source, Git status, provider state, and evidence before relying on any historical result. Record exact source SHA, artifact/runtime identities, timestamps, commands, results, and evidence paths.
2. Reuse evidence only when its input identities, scope, environment, and coverage match the current candidate. Rebind evidence explicitly; otherwise rerun the applicable check. Local or synthetic results do not establish hosted behavior.
3. Preserve failed and incomplete attempts in the evidence history. Do not turn missing evidence into a pass or make a failing gate pass by changing its acceptance criteria.
4. Keep credentials and backup contents outside Git. Store sanitized receipts and hashes in the repository; never commit tokens, raw media, or private backup contents.
5. Keep the older dirty checkout untouched. The managed `public-web-beta` worktree is the release source. Inspect its status before each change and preserve pre-existing work, including the existing `CONTEXT.md` terminology edit.

## Current gate tracker — November 16, 2026

Current source is GitHub `main` at `e9370d9f6675be3fe5567043b458ab51afae0933`.
The [readiness refresh](public-beta-readiness-20261116.md) records source-matched
CI evidence and limits. Earlier dated narrative below remains historical.
This table is the live all-14-gate tracker; partial passes do not close a gate.

| Gate | Status | Evidence / next requirement |
| --- | --- | --- |
| 1. Freeze candidate | Open | Current main is published and its Security Checks pass. Final production candidate/artifact reconciliation remains. |
| 2. Security and offline runtime | Pass for verified CI checkpoint; production artifact open | Run 43968645784: 22 successful jobs, one expected production-PR-only skip. Downloaded root/web reports match source and checksums; no HIGH/CRITICAL findings. Container/offline logs pass. Retention passed and downloaded artifacts matched inspected/scanned images in PR run 43970160990. Documentation head 889537a8 passed subsequent Security Checks run 43971866701; security/runtime inputs are unchanged. Actual production artifact acceptance remains open. |
| 3. Credential history | Blocked | Current Gitleaks and PR #52 GitGuardian checks pass for the earlier code checkpoint. Nathan supplied GitHub Support ticket #4813900 response: revocation is the remedy. Existing provider-confirmed New Relic deletion resolves that key's history-removal subitem; no purge claimed. [Disposition](gate-3-support-disposition-20261116.md). Remaining credential/provider/consumer disposition is still open; retired Azure credentials require verified retirement or rotation if used. |
| 4. Staging authentication | Open | Supabase staging is ACTIVE_HEALTHY with 52 recorded migrations through 20261103022851. Source contains accepted staging Render binding at a4370570. Fresh pair is suspended at a4370570, behind current backend changes. Netlify main deploy e9370d9 completed; custom branch TLS and API DNS are missing for full media testing. [Current preflight and prepared Support request](staging-next-actions-20261116.md). Auth/browser/native and normal application media acceptance remain open. |
| 5. Hosted recovery | Passed for November 6 snapshot scope | November 8 hosted restore report and November 9 rehearsal preserve the scoped pass. Current recovery project uhivjkfpfqtpicyjtmie is INACTIVE; this does not invalidate the historical rehearsal or prove new candidate recovery. |
| 6. Fresh recovery point | Open | Protected copy and rehearsal succeeded for old snapshot; fresh writer freeze/export/protected copy required at cutover. |
| 7. Production migrations | Blocked on fresh recovery and application approval | Production still records 21 migrations through 202608270001. Isolated 30-file rehearsal passed; current MVP selection/dry run must be reviewed before approved production application. |
| 8. US-IP signup | Open | Current CI signup-hook/expiry tests pass. Live geography refresh, trusted proxy and Auth-hook acceptance remain required. Signed-in uploads from abroad follow ADR 0021. |
| 9. Guardrails | Open | CI budget/retention controls pass within tested scope. Hosted collector, alerts/delivery, cleanup, intake stop, accepted-job draining and quotas remain unaccepted. |
| 10. Render cutover | Open | Fresh staging and production pairs follow ADR 0021. Current production service identities, matching credentials, image, readiness, cost and two-longest-clip evidence remain required. |
| 11. Private Web App | Open | Combined production binding remains pending. Verify current private deployment/configuration, release build/budget, visual/accessibility and historical URL privacy. |
| 12. End-to-end acceptance | Open | Record exact-candidate two-owner upload, analysis, save, export, deletion/recovery, session isolation and required browser/mobile flows. UI/performance work requires current hosted acceptance. |
| 13. Protected release | Open | Main security checks pass; main-to-production PR, current protections/check contexts and complete frontend/backend/migration/model manifest remain required. |
| 14. Public launch | Blocked | Mandatory gates, final cost/rollback packet and Nathan's action-time public exposure approval remain required. |

**Historical independent checks (earlier checkpoint):** `npm run deps:verify` passed; `npm run typecheck` passed; `npm run test:policy` passed (698/698); `npm run dashboard:typecheck` passed; `npm run dashboard:test` passed (17/17); `npm run dashboard:build` passed; `npm run audit:ci` passed with no HIGH/CRITICAL findings; `git diff --check` passed. These checks are local evidence only. The production-bound Gate 11 build and hosted release acceptance have not been performed.

## Work sequence and parallel tracks

### November 6 Netlify privacy review

Provider readback identified exactly three Peso projects in the selected team: `peso-public-beta` (`76ffb7be-b126-4ae0-a972-ca5a244895fa`), `peso-webapp` (`230da8eb-f00e-45d4-ba54-95f2e26f21c4`) and `peso-marketing` (`19cbad85-dd2d-4d3b-a24a-242de78d30af`). All show Private production and Deploy Preview visibility and private deploy logs. The new project still publishes the old bootstrap source `98bad175cf2025741632244f4dd2da6b9866f87f`; production branch is `main`, automatic publishing/builds are active, Node is `24.x`, and build/publish settings remain the recorded dispatcher and `dist`. All deployment methods are currently permitted. The preview drawer is enabled on `peso-public-beta` and `peso-webapp`, disabled on `peso-marketing`; review these settings as part of the protected release configuration. No setting changed and no deployment was triggered.

The complete visible `peso-webapp` deploy list ended with a disabled Next button on page seven: 77 unique deploy entries and 48 actual artifact permalink links. The marketing list has six entries and four artifact links; the bootstrap project has one artifact link. Entries without artifact links are retained as IDs and are not assumed to contain deployed assets. Anonymous GET checks at `2026-11-07T01:36:38Z`–`01:36:48Z` covered all 53 observed artifact permalinks at root and `/app/`, plus the three project roots, the known private `main--peso-webapp` alias and the two custom-domain hosts. Of 118 requests, 116 returned 401; the two `www.usepeso.com` requests returned 301 to the corresponding `usepeso.com` path, each separately verified to return 401. No cookies or credentials were sent, redirects were inspected explicitly, and response bodies were not retained. Individual hashed assets and unlisted/deleted URLs are not claimed covered.

Receipts under `/Users/nathan/.codex/visualizations/2026/11/05/01a1add7-d3fe-7203-a616-5ea6caa842e7`: `netlify-config-readback-20261106.json`, `netlify-webapp-deploy-inventory-20261106.json`, `netlify-marketing-deploy-inventory-20261106.json`, `netlify-anonymous-artifacts-20261106.json` and `netlify-www-redirect-check-20261106.json`. These are privacy evidence for the current infrastructure, not release acceptance for a new combined artifact.

### 0. Revalidate baseline and establish the tracker

- Read the canonical launch plan, PRR, execution contract, Gate 2 checkpoint review, recovery instructions, and current terminology in `CONTEXT.md`.
- Inspect the managed worktree status and current branch/HEAD; identify user changes and do not overwrite them.
- Revalidate the PRR status line, which was last dated September 30, 2026, and the active 14-gate tracker. Carry forward no historical status without current evidence.
- Reinspect the latest recovery packet. The handoff identifies the November 5 packet as `INCOMPLETE`: writer freeze, off-device copy, hosted restore, and Storage byte verification were false, and `roles.sql` was empty after a failed dump. Treat these as blockers to a fresh accepted recovery point, not as passed work.
- Rebind the October 28 Gate 2 acceptance to the current candidate inputs. It covers checkpoint `57f013de0b650b7e5f5bf89ea4d7cc1338c936b3`; it does not by itself accept later source or deployed artifacts.
- Record a dated gate table with: gate, owner/action, prerequisite, evidence required, status, blocker, and next decision. Keep this as the single live status record, updating the existing tracker if identified; do not create a competing status ledger.

### 1. Critical path: fresh recovery and hosted restore rehearsal (Gates 5–6)

These gates block safe production migrations and remain the critical path.

1. Read-only verify the identity, organization, isolation, contents, plan, and current provider state of the existing inactive recovery project. Confirm whether it is still isolated and suitable for reuse. Do not restore or otherwise mutate it during inspection.
2. Prepare the fresh backup procedure and checklist: verify a complete writer freeze, export all required database/auth/storage metadata, inventory Storage objects, capture object bytes when present, generate and verify checksums, and create a protected off-device copy. Keep contents private and outside Git.
3. Obtain required action-time approval before any hosted restore or recovery-project mutation. If the existing project is unsuitable, stop and prepare the exact alternative and its cost/impact for separate approval. Do not create, activate, delete, or repurpose projects without the required approval.
4. In the approved isolated target only, conduct the Hosted Restore Rehearsal using the reviewed restore procedure. Verify restored database state, custom Storage policies, Auth behavior, owner/non-owner access, object inventory, and byte-level read-back/checksums where objects exist. Capture failures and stop on unexplained mismatch.
5. Verify protected off-device backup integrity independently. Record writer-freeze evidence, export time, inventory, checksums, copy verification, target identity, restore results, and cleanup/retention state.

**Exit:** A fresh verified recovery point and approved hosted restore rehearsal pass with complete evidence. No production restore is part of this rehearsal.

Protected-copy verification passed on November 8 after Nathan attached the actual downloaded archive. Directly observed Proton provenance and private sharing are recorded separately from independently verified bytes: exact archive hash/size, byte equality to the original, all ten internal files and all six SQL manifest entries passed. The original archive and its exporter flags remain immutable; `proton-current-archive-verification-20261108.json` records the new verification. Hosted restore acceptance and a fresh production cutover recovery point remain required.

November 6 restore preparation is retained privately in the fresh export attempt's `restore-preparation` directory. Its receipt pins source/adjusted role SQL and reviewed Storage policy SQL, leaves `targetRef=null`, and forbids using production, staging, old recovery or HootRoute as the test target. Before any new target is created, separately approve the selected capacity action and project creation after a current quote. After creation, verify emptiness, project identity, connection username and managed Auth/Storage schema compatibility. Preserve managed schemas; restore only the reviewed application/history/data material and separately reviewed customizations under a separately approved transaction. Stop on any unexpected error or schema difference. Synthetic two-owner Auth/Storage API tests, rollback checks, byte round trips, private target retention/pause and final comparison remain required. The eight-policy comparison is source preparation, not hosted acceptance. See [provider backup/restore guidance](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore) and [free-project limits](https://supabase.com/docs/guides/platform/billing-on-supabase).

The November 6 rerun of `python3 scripts/rehearse_storage_policy_recovery.py` passed all 61 synthetic local isolation, rollback, restore and RLS assertions. The disposable PostgreSQL container had networking disabled, used no real backup data or hosted credentials, and was removed successfully. Restored policy catalog digest: `3bfdb81204916071fb7f6aa552329f1ae9cf6a129c429bb880481f93bba17445`. This is fresh local preparation evidence; the hosted Auth/Storage API tests remain open.

Read-only target isolation review on November 6 found signup and Data API enabled, anonymous sign-in/manual linking disabled, email confirmation enabled, email provider enabled, and listed external/phone providers disabled. Site URL is `http://localhost:3000` with no redirect allowlist entries. Approval is pending to disable signup and Data API on this empty target before private restoration. No setting has been changed. Target SQL confirms `auth.uid()`, `storage.foldername(text)` and `storage.extension(text)` exist, `storage.objects` RLS is enabled and there are zero existing object policies. `anon` and `authenticated` lack superuser/RLS bypass; `service_role` has the expected RLS bypass and is not superuser. These observations meet preliminary policy-recovery prerequisites, not hosted restore acceptance.

Nathan then explicitly approved disabling signup and Data API on the recovery target. Both controls were saved and independently reloaded: `Allow new users to sign up=off`, `Enable Data API=off`, with the provider's `Data API disabled` confirmation and `No schemas can be queried` readback. No other setting or project changed. Before/after screenshots and `recovery-isolation-applied-20261106.json` are retained under the current chat's private visualization directory. Private backup data remains unimported; Data API re-enablement for tests and the restore itself remain separately gated.

### 2. Parallel preparation: source, credentials, admission, and operations

Start these tracks after baseline inspection; they may progress while recovery approval or evidence is pending, but they cannot claim dependent hosted acceptance.

**A. Candidate and security/runtime (Gates 1–2)**
- Reconcile release-source changes and choose a candidate checkpoint only after current diffs are understood.
- Run the approved source checks, fixture-only local build, migration audit, security/dependency review, patch integrity, and isolated offline runtime checks against exact candidate inputs.
- Reuse the October 28 Gate 2 evidence only for inputs and coverage proven unchanged; otherwise rerun relevant checks. Keep all current CI enforcement and the no-HIGH-exceptions guard.
- Do not deploy the Gate 1 fixture build. Any later source change receives fresh applicable checks and a new recorded SHA.

**B. Credentials and history (Gate 3)**
- Inventory outstanding rotation or verified retirement, provider verification, Support disposition and secret-scan requirements from the canonical evidence.
- Prepare a credential disposition matrix without exposing secret values. Complete only actions already authorized; record provider confirmations and exact scope.
- Keep any unavailable provider or human action as a named blocker with the smallest specific request required.

Credential disposition prepared from the September 13 provider follow-up and current source bindings (secret values are excluded):

| Item | Available evidence | Required next evidence / action |
| --- | --- | --- |
| Exposed New Relic license key | September 13 note records provider deletion without replacement. | History-removal subitem resolved by the existing deletion confirmation and Nathan-supplied October 8 Support response; [review](gate-3-support-disposition-20261116.md). PR #52 earlier code checkpoint passed GitGuardian. No purge claimed; recheck scanners on final source. |
| Student scaler database password | Rotation script was tested locally; no current production rotation receipt exists. | Review the current consumer inventory, separately approve provider credential changes, rotate the role and dependent GitHub/Key Vault connection secrets, and verify every remaining deployed consumer. Historical local tests do not establish current revocation. |
| Render API/worker Supabase credentials | Combined binding is pending; existing services were historically bound to staging. | Read current provider settings privately and verify both credentials identify the chosen project before any separately approved rebind/resumption. A URL-only edit is insufficient. |
| Cleanup, intake-stop, geography and alert-delivery credentials | Activation and delivery acceptance remain open. | Verify purpose, scope, provider storage and recipients at the applicable activation gate; retain identifiers/results without values. New credential creation and hosted activation require their action-time approval. |

**C. US-only admission (Gate 8)**
- Revalidate the authoritative geography source and dataset freshness; prepare refresh evidence.
- Verify Auth hook behavior, trusted proxy chain assumptions, IPv4/IPv6 handling, spoofing resistance, expiration, and fail-closed behavior.
- Distinguish local policy tests from deployed/provider verification; do not mark hosted admission accepted until its actual production path is verified.

**D. Guardrails and monitoring (Gate 9)**
- Verify retention and cleanup behavior, budget alert configuration, intake stop, delivery behavior, accepted-job draining, quotas, and monitoring signals against current runtime/provider state.
- Resolve the known Storage cleanup/provider support uncertainty before accepting the affected erasure/cleanup contract. Preserve current counterexamples and provider response evidence.
- No new paid service activation or budgeted resource is included in preparation without separate approval.

### 3. Sequential hosted release preparation (Gates 7, 10–12)

Proceed only when named prerequisites pass. Batch evidence collection within each approved operation.

**Gate 7 — Production migrations**
- Reinspect the live migration history and current dry run after the recovery gates pass.
- Review the exact chain, apply only the approved production migration operation, then verify migration history, RPCs, RLS, grants, and Data API behavior. Keep recovery evidence and rollback/forward-repair facts ready before execution.
- Any destructive or data-changing step remains subject to its own action-time approval.

**Gate 10 — Render cutover**
- Read back existing service IDs, production bindings, suspended/running state, and the exact reviewed configuration. Resolve the documented worker-plan mismatch before any Blueprint synchronization.
- Prepare the cutover with reviewed IDs and matching production credentials. Verify API readiness, then worker acceptance and two longest-clip measurements.
- Manual deployment, service resumption, and any paid resumption are separate actions; confirm cost and obtain required approval immediately before each action. Do not silently change the validated workload or downgrade it to fit a plan.

**Gate 11 — Private Web App build**
- Verify the combined Netlify project and exact production binding/configuration while deployment visibility remains private.
- Run the production release validator, build, and budget check against the verified production variables and same output artifact. Never deploy the fixture build or bypass validation.
- Verify preview privacy, historical app-containing URL privacy, current login/signup shell, fonts, reload behavior, and required WebKit keyboard skip-link checks at 1280x900 with reduced motion and at a mobile width. Run current visual regressions for Marketing Site and Web App. Required accessibility failures block launch.

**Gate 12 — End-to-end acceptance**
- Use two test owners and verify upload through analysis, review/save, export, deletion, recovery, mobile compatibility, owner isolation, and expired-session behavior.
- Verify real authentication and required browser user flows against the private candidate and actual configured services. Keep supported scope to side-view squat.
- Treat tracking identity reacquisition as **Tracking Recovery**. Preserve known failure cases and require correct identity continuity; a plausible-looking path is not proof of identity.

### 4. Protected release and public transition (Gates 13–14)

**Gate 13 — Protected release**
- Prepare one protected `main` → `production` PR containing the accepted candidate. Require all configured checks on the release SHA and record frontend, backend, migration, and model identities.
- Confirm production bindings, security evidence, recovery, US admission, two-owner acceptance, and rollback evidence all refer to the exact release candidate.
- Do not merge or publish under this planning authorization. The protected release action requires the applicable approval and must use the accepted SHA.

**Gate 14 — Public launch**
- Before any public exposure, assemble a concise action packet with final cost/billing facts, production identities, passed gate evidence, rollback procedure, smoke-check plan, and unresolved limitations (none may be a mandatory blocker).
- Obtain Nathan’s action-time confirmation for public exposure. This approval is distinct from approvals for restore, paid resumption, destructive changes, or merge/release.
- After approval and exposure, run public smoke checks for anonymous homepage, signup and US admission behavior, authenticated `/app`, upload/analysis path, and privacy of previews/staging/historical deploy URLs. Restore private visibility or execute the approved rollback if isolation or required behavior fails.
- Begin first-cycle monitoring immediately and record the initial queue, failure, latency, completion, Tracking Recovery, and support baselines. Review outcomes within the first beta cycle as required by the PRR.

## Approval boundaries

This plan authorizes writing and maintaining the plan and the already-approved routine local preparation described in the current execution contract. It does not authorize:

- hosted restores or other project/data mutations;
- new or resumed paid services, new spend, or plan changes;
- destructive changes, production migration application, or irreversible cleanup;
- merge, production deployment, domain/public visibility changes, or public exposure.

Present each necessary approval separately, only after preparing concrete evidence, exact target/identity, cost or impact, rollback, and verification steps. Do not bundle distinct decisions into one approval request. Continue independent authorized local preparation while an unrelated approval is pending.

## Completion record

The plan is complete as an execution plan when the active tracker points to current evidence for all 14 gates, clearly identifies the critical path and each approval boundary, and uses the agreed terms **Tracking Recovery** and **Hosted Restore Rehearsal**. The release itself is complete only when the PRR exit criteria, public smoke checks, and first-cycle monitoring condition above are met.
