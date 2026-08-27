const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const migrationSource = fs.readFileSync(
  path.join(
    __dirname,
    '../supabase/migrations/202608270001_add_analysis_job_scaler_signal.sql'
  ),
  'utf8'
);

test('analysis scaler role is inert and non-privileged in tracked migrations', () => {
  assert.match(migrationSource, /create role analysis_job_scaler[\s\S]*nologin/i);
  assert.match(migrationSource, /nosuperuser/i);
  assert.match(migrationSource, /nocreatedb/i);
  assert.match(migrationSource, /nocreaterole/i);
  assert.match(migrationSource, /noreplication/i);
  assert.match(migrationSource, /nobypassrls/i);
  assert.match(
    migrationSource,
    /revoke all privileges on all tables in schema public from analysis_job_scaler/i
  );
  assert.doesNotMatch(migrationSource, /password\s+'/i);
});

test('analysis scaler signal counts only due non-discarded video analysis work', () => {
  assert.match(
    migrationSource,
    /create or replace function public\.pending_video_analysis_job_count\(\)/i
  );
  assert.match(migrationSource, /returns integer[\s\S]*security definer/i);
  assert.match(migrationSource, /set search_path = pg_catalog/i);
  assert.match(migrationSource, /analysis_jobs\.job_type = 'video_analysis'/i);
  assert.match(migrationSource, /analysis_jobs\.status in \('queued', 'retry_wait'\)/i);
  assert.match(migrationSource, /analysis_jobs\.available_at <= pg_catalog\.now\(\)/i);
  assert.match(migrationSource, /videos\.discarded_at is null/i);
});

test('only the analysis scaler role can execute the scale signal', () => {
  assert.match(
    migrationSource,
    /revoke execute on function public\.pending_video_analysis_job_count\(\)[\s\S]*from public, anon, authenticated/i
  );
  assert.match(
    migrationSource,
    /grant execute on function public\.pending_video_analysis_job_count\(\)[\s\S]*to analysis_job_scaler/i
  );
});
