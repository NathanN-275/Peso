const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const {
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  getQualityPreflightQueueDecision,
  requiresQualityPreflight,
} = require('../lib/qualityPreflightPolicy');

test('preflight applies only to side-view squat variations', () => {
  assert.equal(requiresQualityPreflight({ exercise: 'Squat', angle: 'Side' }), true);
  assert.equal(requiresQualityPreflight({ exercise: 'Goblet Squat', angle: 'Side' }), true);
  assert.equal(requiresQualityPreflight({ exercise: 'Squat', angle: 'Front' }), false);
  assert.equal(requiresQualityPreflight({ exercise: 'Bench Press', angle: 'Side' }), false);
});

test('pass, warning, and blocked results have distinct queue decisions', () => {
  assert.deepEqual(getQualityPreflightQueueDecision({ status: 'pass' }), {
    canQueue: true,
    needsConfirmation: false,
    mustReplaceVideo: false,
  });
  assert.deepEqual(getQualityPreflightQueueDecision({ status: 'warning' }), {
    canQueue: true,
    needsConfirmation: true,
    mustReplaceVideo: false,
  });
  assert.deepEqual(getQualityPreflightQueueDecision({ status: 'blocked' }), {
    canQueue: false,
    needsConfirmation: false,
    mustReplaceVideo: true,
  });
});

test('upload flow verifies the deployed version before sending a side squat', () => {
  const uploadSource = fs.readFileSync(path.join(__dirname, '../lib/videoUpload.ts'), 'utf8');
  const policySource = fs.readFileSync(
    path.join(__dirname, '../lib/qualityPreflightPolicy.js'),
    'utf8'
  );

  assert.match(uploadSource, /quality_preflight_versions/);
  assert.match(uploadSource, /QUALITY_PREFLIGHT_THRESHOLD_VERSION/);
  assert.match(policySource, new RegExp(QUALITY_PREFLIGHT_THRESHOLD_VERSION));
  assert.match(uploadSource, /before upload/);
});

test('upload review exposes warning continuation and blocked replacement copy', () => {
  const screenSource = fs.readFileSync(
    path.join(__dirname, '../src/screens/UploadVideoScreen.tsx'),
    'utf8'
  );

  assert.match(screenSource, /Continue With Warnings/);
  assert.match(screenSource, /will not enter full analysis/);
  assert.match(screenSource, /runVideoQualityPreflight[\s\S]*triggerVideoAnalysis/);
});
