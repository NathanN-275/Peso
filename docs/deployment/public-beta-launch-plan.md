# Public Web Beta Launch Plan

**Status:** Current project goal | **Source:** `peso_public_web_beta_launch_plan.pdf` | **Owner:** Nathan | **Updated:** 2026-09-21

This document records the approved interpretation of the attached launch plan.
It is the current release goal for Peso and supersedes older marketing-only
launch framing. It does not authorize external changes by itself.

## Release target

Launch the existing Peso homepage and existing Web App together at
`usepeso.com`, with the Web App mounted at `/app`. Preserve the historical
`peso-webapp` and `peso-marketing` projects, their deploy history, existing data,
account compatibility, and the deferred native app. Reuse functioning product
flows and visual design; changes must be justified by the launch gates.

The beta is US-IP-restricted, permits open signup after launch, and supports
the existing side-view squat workflow. IP location is an access restriction,
not proof of residency. An unlisted URL is not an access-control mechanism.

## Hard approval gates

- Keep all sites and app routes non-public until Nathan completes end-to-end
  acceptance and gives explicit action-time approval for public exposure.
- Obtain approval before paid provisioning, capacity or spend increases,
  destructive changes, DNS cutover, or any public visibility change.
- Do not declare launch complete until production acceptance passes and Nathan
  authorizes publication.

## Required work

1. Inspect and reconcile repository, Git, Netlify, Render, Supabase, DNS/TLS,
   migrations, credentials, security findings, costs, and release blockers.
2. Prepare the combined frontend, API, worker, database, authentication,
   retention, privacy, capacity, performance, and monitoring path.
3. Benchmark representative clips against the roughly 60-second target and
   90-second acceptable case; measure queue wait separately.
4. Preserve the three-day expiry for unsaved work, owner-scoped access,
   evidence-aware uncertainty, and existing native-app compatibility.
5. Run technical checks plus browser and mobile acceptance, including signup,
   email verification, reset, upload/recording, analysis, review, save/discard,
   history, deletion, recovery, isolation, and accessibility.
6. Produce a protected release PR, release manifest, acceptance evidence,
   rollback procedure, and launch-day monitoring checklist.

## Definition of done

The candidate passes the technical and human gates; all required operational,
security, legal, email, migration/backup, and provider facts are verified; the
intake stop is demonstrated; rollback boundaries are documented; and Nathan
approves final public exposure. Until then, the release remains private and
the goal is incomplete.
