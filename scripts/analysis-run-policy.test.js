const assert = require('node:assert/strict');
const test = require('node:test');

const {
  cancelAnalysisRun,
  createAnalysisRun,
  isAnalysisRunCurrent,
} = require('../lib/analysisRunPolicy');

test('cancel aborts the active run and invalidates stale responses', () => {
  const run = createAnalysisRun(4);
  assert.equal(isAnalysisRunCurrent(5, run), true);

  const nextGeneration = cancelAnalysisRun(5, run);

  assert.equal(run.controller.signal.aborted, true);
  assert.equal(nextGeneration, 6);
  assert.equal(isAnalysisRunCurrent(nextGeneration, run), false);
});

test('starting again creates a current non-aborted generation', () => {
  const canceled = createAnalysisRun(2);
  const generation = cancelAnalysisRun(3, canceled);
  const retry = createAnalysisRun(generation);

  assert.equal(isAnalysisRunCurrent(retry.generation, retry), true);
  assert.equal(isAnalysisRunCurrent(retry.generation, canceled), false);
});
