const assert = require('node:assert/strict');
const test = require('node:test');

const {
  cancelDemoAnalysis,
  progressDemoAnalysis,
  startDemoAnalysis,
} = require('../lib/webDemoSessionPolicy');

test('demo analysis spends its first two seconds queued', () => {
  assert.deepEqual(startDemoAnalysis(1_000), {
    phase: 'queued',
    percentage: 0,
    startTime: 1_000,
  });
  assert.equal(progressDemoAnalysis(1_000, 2_999).phase, 'queued');
  assert.equal(progressDemoAnalysis(1_000, 2_999).percentage, 0);
});

test('demo analysis progresses during the next six seconds', () => {
  const progress = progressDemoAnalysis(1_000, 6_000);

  assert.equal(progress.phase, 'analyzing');
  assert.equal(progress.percentage, 50);
});

test('demo analysis completes at eight seconds without changing its start time', () => {
  assert.deepEqual(progressDemoAnalysis(1_000, 9_000), {
    phase: 'ready',
    percentage: 100,
    startTime: 1_000,
  });
});

test('canceling a demo analysis returns it to idle', () => {
  assert.deepEqual(cancelDemoAnalysis(), {
    phase: 'idle',
    percentage: 0,
    startTime: null,
  });
});
