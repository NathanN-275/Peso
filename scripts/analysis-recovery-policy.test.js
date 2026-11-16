const assert = require('node:assert/strict');
const test = require('node:test');

const {
  canRetryAnalysis,
  failureCopy,
} = require('../lib/analysisRecoveryPolicy');

test('invalid videos explain replacement and never offer retry', () => {
  const activity = {
    stage: 'failed',
    failure_class: 'invalid_video',
    recovery_action: 'replace_upload',
  };

  assert.match(failureCopy(activity), /couldn’t read this video/i);
  assert.equal(canRetryAnalysis(activity), false);
});

test('timeout and transient failures offer retry', () => {
  for (const failureClass of ['analysis_timeout', 'transient_infrastructure']) {
    const activity = {
      stage: 'failed',
      failure_class: failureClass,
      recovery_action: 'retry',
    };

    assert.match(failureCopy(activity), /try again/i);
    assert.equal(canRetryAnalysis(activity), true);
  }
});

test('an earlier saving attempt does not mislabel a later processing failure', () => {
  const activity = { failure_class: 'analysis_runtime', stage_timestamps: {
    saving: '2026-11-16T01:00:00Z', pose: '2026-11-16T01:01:00Z', failed: '2026-11-16T01:02:00Z',
  } };
  assert.match(failureCopy(activity), /processing error/);
  assert.doesNotMatch(failureCopy(activity), /finish saving/);
});
