# Saved Lift archive admission and publication

`20261027194638_archive_publication_fence.sql` adds a service-invoker trigger on
`public.saved_lift_export_jobs`. It applies to the existing repository and direct
service-role writes. It takes all selected video locks in UUID order and checks
the complete distinct 1–50 selection before archive admission, processing or
completion: every member must exist, belong to the owner, still be saved under
either legacy saved flag, have an analysis, have no tombstone/deletion outbox or
pruned storage, and have a null or finite future video deadline. A wall-clock
check runs after any wait on the archive row. An archive writer that already
holds its row uses NOWAIT video locks to avoid waiting against revocation's
video-before-archive lock order. Contention aborts the whole write for retry.

The archive ID, owner and ordered membership are immutable. Failed and expired
jobs cannot reopen; processing cannot return to queued; completed jobs cannot
return to queued/processing or change their completion, expiry or artifact.
Completion accepts only the deterministic owner/job ZIP path and a finite future
archive deadline. Incomplete jobs cannot publish a path. Worker failures only
match queued/processing jobs; only `archive_missing` may retire a completed job.
Revocation may expire any job and clear its path, including malformed historical
rows. A stale worker cannot change an expired job to failed or completed.

The repository predicates transitions on the expected current state and returns
`None` when another transaction already moved the job. Successful responses must
contain one canonical matching ID and the expected state/artifact. The service
checks these results and treats a denied completion as rejection. An
archive-missing projection reads the current record when its conditional failure
update loses a race. Lock/deadlock/serialization errors (SQLSTATE 55P03, 40P01,
40001, which guarantee transaction rollback) are retried at most three times,
with 100ms and 200ms backoff. Exhaustion uses the existing guarded failure
transition with `capacity_unavailable`; it does not leave a processing job
silently stuck. There is no new background scheduler, processing lease or crash
recovery.

Transport errors are never blindly retried. After a post-upload exception the
service rereads the owned job: a confirmed completed record pointing to that
exact archive preserves its bytes. A confirmed active/failed/expired record
permits best-effort cleanup. Failed or malformed confirmation preserves bytes
without claiming completion; a guarded worker failure cannot overwrite a
completed or expired job. Durable cleanup for such uncertain objects remains
part of the outstanding upload-intent protocol.

## Verification

`test_video_revocation_postgres.py` loads this migration and verifies both lock
orders: admission first is captured by revocation; revocation first rejects later
admission. Its malformed historical rows are constructed only in the disposable
localhost fixture with this one trigger disabled in the fixture transaction.
`test_archive_publication_postgres.py` covers direct writes, ACL/search path,
selection bounds/ownership, legacy saved flags, expiry, terminal states,
immutable identity, busy video locks and completion after a row-lock wait.
`test_saved_lift_exports.py` covers service rejection/cleanup and repository
transition predicates. These tests do not inspect hosted data or actual Storage.

## Remaining launch work

This fence protects database admission and metadata publication. It does not make
an external Storage upload atomic with revocation. A late or ambiguous upload
can still recreate a ZIP after the deletion consumer has removed and acknowledged
its snapshot; best-effort deletion can fail or the process can crash first.
Durable object upload intents and cleanup acknowledgements shared by every
publisher are still required before activating the revocable-media path. It also
does not provide owner-level account deletion, session revocation or native/web
media-client acceptance. No hosted migration is applied by this change.
