# Security, retention, and incident runbook

## Provider release settings

- Supabase: require email confirmation, enforce the agreed password length/strength and breached-password protection where available, review signup/login/reset rate limits, restrict redirect URLs, and require MFA for every privileged operator. Record screenshots/settings exports without secrets. Application code cannot enforce organization/operator MFA on Supabase's behalf.
- Azure/GitHub: require privileged-operator MFA, protect deployment environments with reviewers, enable secret scanning/push protection, require dependency, container, migration/RLS, and security tests, and retain immutable image digests.
- Web: verify CSP, HSTS, `frame-ancestors`, `nosniff`, referrer policy, and permissions policy on actual production responses. Do not infer deployed headers from source alone.

## Signals and response

Central JSON logs use event markers for reservation issuance/denial, media rejection, cleanup, and budget shutdown. Alert on auth failures, reservation/service failures, quota-denial spikes, unusual reservation volume per user, failed analysis jobs, failed cleanup executions, and failed admission Logic App runs. Keep logs at 30 days and within the configured daily ingestion cap. Logs must not contain tokens, signed URL query strings, request bodies, or video data.

For suspected upload abuse or an unexpected cost spike:

1. Disable admission with the authenticated budget route or `select public.disable_video_upload_admission();` through a privileged database session. Keep owner reads and deletion available.
2. Inspect sanitized event counts, queue depth, active leases, total source bytes, and Cost Management evidence. Preserve timestamps/resource IDs; do not copy user media into incident notes.
3. For a compromised SAS, stop new reservations and revoke user-delegation keys with a privileged storage operator if immediate revocation is needed. Key revocation affects all current delegated URLs, including playback. Rotating an unrelated app secret does not revoke an existing SAS.
4. If needed, pause the analysis job using the existing worker-control workflow. Preserve database job state for recovery; never delete the resource group as incident response.
5. Confirm cleanup after the last possible SAS expiry. Investigate failed deletes; do not mark cleanup confirmed when Azure did not acknowledge deletion.
6. Re-enable only after root cause, spend, user impact, and safeguards are reviewed. The explicit reset is `update public.upload_admission_control set enabled = true, disabled_reason = null, updated_at = now() where id = 1;`. A deployment must not perform that reset automatically.

## Retention and deletion verification

- Upload reservations default to ten minutes. Issued/uploaded reservations expire automatically; rejected/expired objects are deleted by the five-minute cleanup job after the token expires.
- Deleting a source before token expiry records a tombstone. Capacity remains charged until a post-expiry deletion is confirmed, preventing token replay from creating an unaccounted object.
- Unverified account-deletion tombstones survive without an auth-user reference until cleanup finishes; completed tombstones without a video are purged after seven days. Saved metadata and private derived assets follow the existing saved-video/export retention rules; unsaved videos default to 24 hours and cached exports to six hours.
- For each deletion drill, check the live blob, snapshots, legacy provider paths, derived playback, thumbnails, exports, reservation state, and database ownership rows. Check again after the latest SAS expiry. Treat inaccessible-by-URL and physically-deleted as different results.
- Source Blob versioning and soft deletion are disabled in this beta so deletion does not silently retain extra copies. Database backup retention remains a separate policy and must be disclosed to users.

## Backup/restore drill (before cutover and quarterly)

1. Record a Supabase backup/PITR restore point and an inventory of a dedicated test user's metadata and private assets. Use test media only.
2. Restore into an isolated target with no production client traffic or production worker credentials. Confirm schema, functions, RLS, role grants, owners, job leases, and reservation state.
3. Verify that an unrelated user cannot read the restored lift, acquire a URL, queue work, or invoke service-only reservation/admission functions.
4. Verify saved playback/export availability against the object inventory. Explicitly record which ephemeral source objects cannot be recovered; database backups alone are not video backups.
5. Rehearse deletion and the post-SAS-expiry check, then remove only the dedicated drill resources with the operator's approval. Record recovery time, data loss window, outcomes, and follow-up actions.
