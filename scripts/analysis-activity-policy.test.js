const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const { shouldPollAnalysisActivity } = require('../lib/analysisActivityPolicy');

test('analysis activity polls only for active queued or processing work', () => {
  assert.equal(shouldPollAnalysisActivity([{ status: 'queued' }], true), true);
  assert.equal(shouldPollAnalysisActivity([{ status: 'processing' }], true), true);
  assert.equal(shouldPollAnalysisActivity([{ status: 'ready' }, { status: 'failed' }], true), false);
  assert.equal(shouldPollAnalysisActivity([{ status: 'processing' }], false), false);
});

test('successful queue handoff leaves the upload screen and restores from Home', () => {
  const uploadSource = fs.readFileSync(
    path.join(__dirname, '../src/screens/UploadVideoScreen.tsx'),
    'utf8'
  );
  const rootSource = fs.readFileSync(path.join(__dirname, '../src/native-root.tsx'), 'utf8');
  const homeSource = fs.readFileSync(path.join(__dirname, '../src/screens/HomeScreen.tsx'), 'utf8');

  assert.match(uploadSource, /triggerVideoAnalysis[\s\S]*onAnalysisQueued/);
  assert.match(rootSource, /onAnalysisQueued=\{handleAnalysisQueued\}/);
  assert.match(rootSource, /pendingAnalysisReview/);
  assert.match(homeSource, /getAnalysisActivity/);
  assert.match(homeSource, /\{analysisActivity\.length > 0 \|\| activityError \? \(/);
  assert.doesNotMatch(homeSource, /activityLoading/);
  assert.match(homeSource, /Ready to review/);
  assert.match(homeSource, /Tracking barbell/);
  assert.match(homeSource, /Download failed — Retry/);
  assert.match(homeSource, /ui_ready_delay_ms/);
  assert.match(rootSource, /throw error/);
});

test('durable queue schema deduplicates active jobs and recovers expired leases', () => {
  const migrationSource = fs.readFileSync(
    path.join(__dirname, '../supabase/migrations/20260713233319_durable_analysis_jobs.sql'),
    'utf8'
  );

  assert.match(migrationSource, /analysis_jobs_one_active_video_idx[\s\S]*where status in \('queued', 'processing', 'retry_wait'\)/i);
  assert.match(migrationSource, /pg_advisory_xact_lock/);
  assert.match(migrationSource, /if found then[\s\S]*return query select v_job\.id/i);
  assert.match(migrationSource, /max_attempts integer not null default 3/i);
  assert.match(migrationSource, /recover_expired_video_analysis_jobs/i);
  assert.match(migrationSource, /revoke all on table public\.analysis_jobs from anon, authenticated/i);
});

test('analysis job observability persists stages, heartbeats, and failure classes', () => {
  const migrationSource = fs.readFileSync(
    path.join(__dirname, '../supabase/migrations/202608170001_analysis_job_observability.sql'),
    'utf8'
  );

  assert.match(migrationSource, /stage_timestamps jsonb/i);
  assert.match(migrationSource, /last_heartbeat_at timestamptz/i);
  assert.match(migrationSource, /failure_class text/i);
  assert.match(migrationSource, /report_video_analysis_job_progress/i);
  assert.match(migrationSource, /record_video_analysis_job_failure/i);
  assert.match(migrationSource, /p_retryable boolean/i);
});
