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
