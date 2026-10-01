# Intake stop and manual recovery

Implementation prepared; production activation and monitoring are not verified.
Nathan approved PesoDatabase (`jfgiydtrskpqxyorvvbc`), a $50 monthly budget,
a $50 projected monthly spend intake stop, and actual monthly spend notifications
at $15, $25, $35 and $50 on September 22, 2026. No public launch, paid service
resumption or capacity increase is authorized by these preferences.

## Measurements and behavior

An authorized monitor can POST to `/internal/budget-admission/evaluate` with
`X-Budget-Token` taken from its secret store, never a URL or browser bundle.
The token is the backend's `BUDGET_SHUTDOWN_TOKEN`. JSON body:

```json
{
  "observed_at": "2026-09-22T00:00:00Z",
  "actual_monthly_usd": "15.00",
  "projected_monthly_usd": "35.00",
  "storage_used_bytes": 123456
}
```

The timestamp above is illustrative; a real measurement sent to this API must be at most five
minutes old and cannot be more than 30 seconds in the future. Negative,
non-finite, timezone-free and malformed measurements are rejected. Collect the
projected **total** monthly spend from provider billing/forecast data, including
compute, storage, transfer, email, monitoring, backups and applicable taxes.
Do not infer a forecast from suspended-service month-to-date billing. If any
provider value is missing or stale, report monitoring failure rather than
substituting zero. `storage_used_bytes` must be measured across the applicable
storage inventory, using complete paginated results.

`INTAKE_STOP_PROJECTED_MONTHLY_USD` must contain Nathan's reviewed integer dollar
threshold (1–50); blank configuration returns 503. The example environment leaves
it at Nathan's approved $50 value. Actual spend and projected spend are separate
required measurements. The response lists reached actual-spend milestones in
`actual_spend_milestones_usd` ($15, $25, $35, $50); this is **not** a notification
delivery receipt. A sample
at or above the selected stop, or at/above the configured storage block ratio
(currently 95% of configured storage quota), disables new admission durably.
The API logs `intake_stop` events without credentials.
Healthy samples never enable admission; `stop_triggered=false` is not evidence
that intake is currently open.

The existing `/internal/budget-admission/disable` remains the immediate manual
stop and can also receive verified resource-pressure alerts. It does not depend
on a spend measurement. OOM/disk-pressure integration still requires reviewed
provider alert wiring. Both endpoints require the budget token.

The database stop shares a transaction lock with upload admission. Once it
commits, new reservations fail with 503 without creating rows or upload URLs.
Already accepted reservations can finish upload/verification and queue their
analysis; existing jobs are not cancelled. Keep workers running while draining
accepted jobs. Never implement an intake stop by suspending the worker or
setting `UPLOAD_RESERVATIONS_ENABLED=false`, which may affect completion paths.

## Operator deployment checklist

1. Confirm the intended API/database identities, migration history and Nathan's
   chosen spend threshold. Apply the reviewed intake-reason migration only after
   the reservation migration and approved staging rehearsal.
2. Configure a non-browser budget token and the reviewed threshold. Do not print
   either credentials or complete authenticated request payloads in logs.
3. Wire a trusted monitor to actual monthly billing, current billing forecasts and measured storage,
   send samples within the five-minute freshness window, and alert the operator
   on missing measurements, non-2xx responses, stale samples and stop events.
   Verify provider billing delay; a recent timestamp cannot make stale billing
   current. Persist notification delivery per billing month and milestone, retry
   failures, and notify for every newly reached threshold if a sample crosses
   several at once. Reset milestone state only for a new billing month. Never
   mark delivery successful from this endpoint response alone. The separate
   hourly GitHub Actions monitor described below supplies manual-entry billing
   collection and email delivery; this endpoint remains available for other
   trusted monitors.
4. In isolated staging, accept one test upload, trip the stop, confirm a new
   upload fails clearly, then finish the accepted upload through actual worker
   playback. Confirm no rejected-request reservation exists. This live test is
   still required; database tests alone do not prove storage/worker completion.
5. Record the tested collector identity, schedule, threshold, notification
   destination and exact release candidate in the release manifest.

## Manual resume

Read `enabled`, `disabled_reason` and `updated_at` from the singleton
`public.upload_admission_control` row. Resolve the pressure condition, review
current spending and accepted-job backlog, and obtain Nathan's approval if
resuming increases capacity or expected spend. Keep the workers running.

Under the same `peso:upload-capacity` transaction advisory lock, update the row
to `enabled=true`, `disabled_reason=null`, `updated_at=now()` **only if** its
`updated_at` still equals the exact stopped timestamp reviewed by the operator.
If no row is updated, a newer stop occurred; reassess rather than overwrite it.
Commit, inspect the row, and run one approved staging/production smoke upload
as appropriate. Do not automate this reset or repeatedly fight a stopping
monitor. Any subsequent pressure sample is allowed to stop intake again.

An intake stop is not a provider spending cap: accepted work, provisioned
compute, stored data, egress and billing delay can keep accruing charges. The
$50 target is not guaranteed by this switch.

## Verification recorded

- Eight measurement/configuration tests cover alert versus stop, exact boundaries, stale and
  future samples, invalid numbers, missing threshold, token rejection, persistent
  stop behavior and database failure propagation.
- Focused intake/reservation/cleanup suite: 55 passed, 21 subtests passed.
- Nineteen disposable PostgreSQL tests passed, including preserving accepted
  upload verification/queue admission, stop/admission locking, capacity limits,
  retention races and client-role access denial.
- Hosted activation, collector scheduling, billing accuracy, notification
  delivery and full accepted-job completion remain open release gates.
- Ten focused spending-policy and monitor tests passed, covering thresholds,
  month rollover, malformed or stale data, email retry, and fail-closed stop.

## Combined monthly guardrail (prepared, inactive)

`.github/workflows/public-beta-budget.yml` runs hourly on the default branch,
but its job runs only when the repository variable
`PESO_PUBLIC_BETA_BUDGET_MONITOR_ENABLED` is exactly `true`. Leave that variable
unset until the release gates below are complete. The runner uses the existing
PesoDatabase project `jfgiydtrskpqxyorvvbc` directly, so it works even while
the paid Render backend remains stopped. It does not start Render, enable
uploads, or launch the public site.

Nathan enters three private GitHub Actions secrets at least daily:
`PESO_RENDER_BILLING_JSON`, `PESO_SUPABASE_BILLING_JSON`, and
`PESO_NETLIFY_BILLING_JSON`. Each must have this exact JSON shape, with values
verified from that provider's billing detail for the **current UTC calendar
month**:

```json
{
  "month": "2026-09",
  "period_start": "2026-09-01",
  "period_end_exclusive": "2026-10-01",
  "checked_at": "2026-09-23T20:00:00Z",
  "source_reference": "Private billing page and calendar-month line items checked by Nathan",
  "actual_usd": "0.00",
  "projected_usd": "0.00"
}
```

The dates and amounts above illustrate the format; do not use them as live
figures. `checked_at` is when the underlying billing information was checked,
not merely when the secret was edited. `actual_usd` is incurred charges for the
calendar month. `projected_usd` includes those charges plus expected remaining
charges for that same month. Include all relevant provider charges, including
taxes where applicable. If a dashboard reports only a billing cycle that
crosses calendar months, derive a verified calendar-month figure from its
line items. If that is not possible, leave uploads stopped and do not enter a
guess or zero. Do not put billing figures or credentials in commits, issues,
PR comments, or workflow dispatch inputs.

The workflow also needs private secrets `PESO_BUDGET_SUPABASE_SERVICE_ROLE_KEY`
for the **same** PesoDatabase project, `PESO_BUDGET_EMAIL_ADDRESS` for Nathan's
own Gmail address, and `PESO_BUDGET_GMAIL_APP_PASSWORD` for its app password.
Store them as GitHub Actions secrets; never paste them in chat or the repo. The
job uses a `public-beta-budget` environment and prints only a generic outcome
and delivered-alert count. Restrict who can edit the workflow and secrets,
because the service-role key can call the intake stop RPC and write the alert
ledger. The workflow intentionally has no GitHub write permission.

The runner rejects missing, malformed, future-dated, or more-than-24-hour-old
entries and calls `disable_video_upload_admission` directly in PesoDatabase.
It also stops intake when the sum of three projected monthly totals is at
least $50. Healthy runs never reopen intake. The `budget_alert_delivery` table
records each actual-spend milestone ($15, $25, $35, $50) once per UTC month.
Failed Gmail sends are retried; a send that succeeds just before an interrupted
acknowledgement may result in a duplicate email. If PesoDatabase itself is
unreachable, the runner cannot enforce a new stop and exits with a failure;
investigate the current intake state immediately. An already stopped intake
remains stopped. Existing accepted uploads and analysis continue after a stop.

Before enabling the repository variable, apply the reviewed
`20260923224101_budget_alert_delivery.sql` migration to PesoDatabase, configure
the six secrets, and run a private stop and email test. Confirm a new
reservation is rejected after stopping intake while one accepted upload and
its analysis finish. Check that the workflow logs expose no figures or
credentials and that the mail reaches Nathan's account. Review the source
figures and their UTC calendar-month attribution. Activate only after these
checks. Public launch and resuming paid infrastructure still require Nathan's
separate approval.
