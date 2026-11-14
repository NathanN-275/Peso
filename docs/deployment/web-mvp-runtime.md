# Web MVP runtime and preservation boundary

Nathan set the active release scope on November 5, 2026: a combined marketing
site and authenticated /app with side-view squat analysis, using Render
for API/worker and Supabase for Auth, Postgres and video Storage. Azure is excluded
from MVP runtime and deployment. Security, recovery, monitoring and user-flow
acceptance remain required. Public exposure, destructive changes and paid services
still require action-time approval. Existing user data must be preserved.
The [November 11 scope decision](../adr/0021-scope-us-ip-signup-and-replace-render-pair.md)
requires a US IP at signup and permits uploads from abroad after sign-in.

Both fresh Render pairs select Dockerfile.mvp. Its
requirements keep the maintained backend pins except Azure SDK packages. Its
Dockerfile-specific build context excludes the legacy Azure Storage adapter.
The image selects PESO_RUNTIME_PROFILE=web-mvp, which requires Supabase uploads
and rejects Azure configuration. API, worker and upload cleanup import without
the omitted adapter. The existing offline media runtime gate additionally checks
that Azure packages and the adapter are absent. The legacy development/Student
image, resources and data remain outside the MVP release path.

Historical Student image publishing is manual-only, so main-branch MVP pushes
do not build Azure infrastructure or publish its separate image. Existing Azure
resources and their budget controls remain outside this release.

The required container-security job and Render candidate validation build this
MVP Dockerfile. Non-root execution, read-only offline runtime, native inference,
FFmpeg/model/version checks and HIGH/CRITICAL scan blocking remain required.
The Blueprints are review artifacts. Provision the fresh pairs only after
action-time approval. Retain the historical pair suspended.

[Render supports a selected Dockerfile path](https://render.com/docs/docker).
[Docker documents per-Dockerfile ignore files](https://docs.docker.com/build/concepts/context/#filename-and-location),
which override the root ignore file for that build. The local verification must
inspect the resulting image rather than infer exclusion from these source files.

## Existing data and remaining launch work

Do not infer a historical storage provider from an owner/source path or the
current global provider setting. Before cutover, inventory every MVP media
reference, all relevant private Storage objects and preserved bytes/checksums.
Bind that inventory to the actual project, frozen writers, candidate and private
manifest digest. Unknown or Azure-backed references block Azure-free cutover until
a reviewed preservation path resolves them. No existing metadata or object is
rewritten, migrated, deleted or marked erased by this runtime change.

A November 5 read-only production metadata observation found zero video rows,
one profile and no Storage object metadata rows. This snapshot does not prove
absence of provider backing bytes, historical capabilities or backup contents.
The hosted recovery, fresh protected recovery point, migration review, exact
provider cleanup contract and end-to-end owner lifecycle remain open.

The unfinished Azure capability-admission draft is retained outside the source
worktree and is not an MVP prerequisite. Azure-only provisioning and token work
must not be resumed as part of this release. Applicable Supabase migration
selection still needs explicit review; do not fabricate applied history or apply
an old full-chain plan solely because a local audit passed.
