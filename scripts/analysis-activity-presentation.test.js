const assert = require('node:assert/strict');
const test = require('node:test');
const { analysisElapsed, analysisStageCopy, analysisStepState, formatElapsed } = require('../lib/analysisActivityPresentation');

test('elapsed time comes from server timestamps and freezes at the terminal event', () => {
  const start = '2026-11-16T01:00:00Z';
  const item = { status: 'processing', stage: 'pose', created_at: start, stage_started_at: '2026-11-16T01:00:05Z' };
  assert.deepEqual(analysisElapsed(item, Date.parse('2026-11-16T01:01:05Z')), { total: 65, stage: 60 });
  const ready = { ...item, status: 'ready', stage: 'ready', stage_timestamps: { ready: '2026-11-16T01:01:20Z' } };
  assert.deepEqual(analysisElapsed(ready, Date.parse('2026-11-16T02:00:00Z')), { total: 80, stage: null });
  assert.equal(formatElapsed(80), '1:20');
  assert.deepEqual(analysisElapsed({ created_at: 'invalid', stage_started_at: 'invalid' }, Date.now()), { total: null, stage: null });
});

test('progress distinguishes actual current and failed steps without percentages', () => {
  assert.equal(analysisStepState({ stage: 'pose' }, 'pose'), 'current');
  assert.equal(analysisStepState({ stage: 'pose' }, 'queued'), 'complete');
  assert.equal(analysisStepState({ stage: 'pose' }, 'saving'), 'pending');
  const failed = { stage: 'failed', stage_timestamps: { pose: '2026-11-16T01:00:05Z', saving: '2026-11-16T01:00:15Z' }, failure_class: 'analysis_runtime' };
  assert.equal(analysisStepState(failed, 'saving'), 'failed');
  assert.match(analysisStageCopy(failed).detail, /finish saving/);
  assert.doesNotMatch(analysisStageCopy(failed).detail, /Delete it/);
  assert.match(analysisStageCopy({ stage: 'barbell_tracking' }).detail, /Building your bar path/);
});
