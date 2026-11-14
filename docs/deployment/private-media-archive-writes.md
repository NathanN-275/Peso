# ZIP archive write and publication

ZIP uploads now use retained `purpose=archive` attempts in the shared generated
ledger. Each owner/job/attempt has a unique create-only key. One dispatch is
allowed for a job's processing generation; both attempt count and start time are
immutable after processing begins. There is no blind retry after uncertainty.

## Frozen package and full selection

The plan RPC locks the active owner, every selected video in stable order and the
archive job. It returns compact ordered member metadata: current effective source,
latest analysis ID/model/contents fingerprint, variant and authoritative filename.
It validates all 1–50 live completed Saved members, deadlines and active analysis
jobs. Latest analysis uses timestamp and ID ordering; a reused ID cannot conceal
different contents. Raw pose histories load one member at a time in the worker.
Clean entries preserve their actual allowed source suffix; overlays use MP4.

The completed manifest also records each downloaded artifact's bucket, key, byte
size and SHA256. An overlay member must match an observed published analyzed-export
generation with that exact source, analysis fingerprint, variant, bucket and size.
A clean member must match the planned source. The actual ZIP size and SHA256 are
recorded before dispatch. These hashes describe locally observed bytes; they do
not establish provider physical erasure or backup retention.

Admission rechecks the entire ordered selection and job generation. The existing
shared capacity lock/limits charge all admitted archive bytes, including failed
and uncertain operations. A typed admission receipt and separate committed
readback must match the full manifest before create-only upload. API success is
observed independently, including after job/video/Auth loss. Object metadata must
match the admitted ZIP size before publication. Every read failure fails closed.

Publication atomically sets ledger publication/deadline and completed job/path in
one database transaction, with the complete selection/source/analysis rechecked.
Expiry is anchored to admission before object creation using the configured cache
lifetime; replay cannot extend it. The producer validates the publication receipt
and an independent committed ledger readback, then the completed owned job. A
lost response can reconcile only the exact committed nonce. Unknown publication
preserves bytes, never compensating-deletes them. Existing status/failure CAS
predicates prevent stale workers from reopening or overwriting completed work.

A published ZIP is a point-in-time package. Later analysis changes do not alter
or invalidate its contents. Owner/member revocation and expiry still deny access.
Archive resolution requires a published ledger row bound to the current completed
owned job and its full selection; metadata size must match before signing or
opening upstream bytes. Storage read errors never clear publication or regenerate
the ZIP. Historical untracked jobs remain removable but cannot serve as tracked
downloads; drain/expire legacy jobs in the separately approved cutover.

## Retention, evidence and deployment

Revocation and unsaved-video retention capture every admitted archive key in the
ZIP bucket cleanup array for every member, even when publication never happened
or the archive job disappeared. Video derivatives remain in the video bucket
array. The pending predicate includes archive selection membership, so finalizers
and Saved deletion receipts cannot report completion after metadata/Auth loss.
The ledger has no cascading resource/Auth foreign keys and no settlement setter.
Expired-archive API deletes do not settle the retained attempt or release quota.

Required CI includes the dedicated real PostgreSQL archive suite as well as the
existing owner, source, generated, analyzed-export, archive-publication, analysis,
revocation and Saved deletion regressions. Backend cases cover exact/deeply typed
receipts and readbacks, create-only dispatch, uncertainty, size/expiry checks,
sequential 50-member ZIPs and private downloads. Synthetic local tests are not
managed-provider acceptance. No hosted migration or setting is changed by this
source update, and media flags stay off.

Cutover must stop old ZIP workers and signing routes, drain or retire historical
jobs, and install the migration and matching producer before restarting work.
A publication trigger cannot stop an SDK upload already dispatched by an old
worker. Keep media disabled until historical write effects and capabilities are
reconciled under the supported provider contract.

[Avatar writes](private-media-avatar-writes.md) now have retained owner/session
attempts and atomic profile publication. Azure write capabilities and historical
dispatches still need coverage. Complete owner-wide deletion, coherent session replacement, retirement
of raw signed URL issuers/direct Storage policies and remaining launch gates are
unfinished. Provider exact-generation orphan/backup cleanup acknowledgement is
still unresolved; the approved support request was sent once, with no follow-up
or diagnostic access grant. Public/destructive/paid actions retain their required
action-time confirmations.
