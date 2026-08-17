const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const {
  QUALITY_PREFLIGHT_WARNING_CONFIDENCE,
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  getQualityPreflightQueueDecision,
  needsQualityPreflightWarning,
  requiresQualityPreflight,
  shouldShowQualityAdvisory,
} = require('../lib/qualityPreflightPolicy');

const passingChecks = {
  sideView: { status: 'pass' },
  bodyChain: { status: 'pass' },
  subjectScale: { status: 'pass' },
  motionBlur: { status: 'pass' },
  dominantLifter: { status: 'pass' },
  multiplePeople: { status: 'pass' },
};

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

test('advisory mode confirms low confidence before queueing without hard-blocking', () => {
  assert.equal(QUALITY_PREFLIGHT_WARNING_CONFIDENCE, 0.85);
  assert.deepEqual(
    getQualityPreflightQueueDecision({
      status: 'blocked',
      overallConfidence: 0.81,
      checks: passingChecks,
    }, { advisoryOnly: true }),
    {
      canQueue: true,
      needsConfirmation: true,
      mustReplaceVideo: false,
    }
  );

  assert.deepEqual(
    getQualityPreflightQueueDecision({
      status: 'pass',
      overallConfidence: 0.85,
      checks: passingChecks,
    }, { advisoryOnly: true }),
    {
      canQueue: true,
      needsConfirmation: false,
      mustReplaceVideo: false,
    }
  );

  assert.equal(
    getQualityPreflightQueueDecision({ status: 'unknown' }, { advisoryOnly: true }).canQueue,
    false
  );
});

test('critical tracking check warnings require confirmation even above 85 percent', () => {
  const checks = {
    ...passingChecks,
    bodyChain: { status: 'warning' },
  };

  assert.equal(needsQualityPreflightWarning({ overallConfidence: 0.92, checks }), true);
  assert.equal(needsQualityPreflightWarning({ overallConfidence: 0.85, checks: passingChecks }), false);
  assert.equal(needsQualityPreflightWarning({ status: 'blocked', overallConfidence: 0.92 }), true);
});

test('quality advisory appears only for new low-quality reviews', () => {
  const lowQuality = { status: 'warning', overallConfidence: 0.81, checks: passingChecks };
  assert.equal(shouldShowQualityAdvisory({ status: 'pass', overallConfidence: 0.9, checks: passingChecks }, 'pending'), false);
  assert.equal(shouldShowQualityAdvisory(lowQuality, 'pending'), true);
  assert.equal(shouldShowQualityAdvisory(lowQuality, 'saved'), false);
  assert.equal(shouldShowQualityAdvisory(null, 'pending'), false);
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

test('upload review exposes advisory continuation and replacement choices', () => {
  const screenSource = fs.readFileSync(
    path.join(__dirname, '../src/screens/UploadVideoScreen.tsx'),
    'utf8'
  );

  assert.match(screenSource, /Continue to Analysis/);
  assert.match(screenSource, /Choose Another Video/);
  assert.match(screenSource, /runVideoQualityPreflight[\s\S]*triggerVideoAnalysis/);
});

test('every upload surface uses concise guidance and confirms quality advisories', () => {
  const screenSource = fs.readFileSync(
    path.join(__dirname, '../src/screens/UploadVideoScreen.tsx'),
    'utf8'
  );
  const dialogSource = fs.readFileSync(
    path.join(__dirname, '../src/components/ConfirmationDialog.tsx'),
    'utf8'
  );
  const reviewSource = fs.readFileSync(
    path.join(__dirname, '../src/screens/AnalysisReviewScreen.tsx'),
    'utf8'
  );

  assert.match(screenSource, /advisoryOnly:\s*true/);
  assert.match(screenSource, /Continue to Analysis/);
  assert.match(screenSource, /Choose Another Video/);
  assert.match(screenSource, /qualityAdvisoryAcknowledged/);
  assert.match(screenSource, /variant="essential"/);
  assert.match(
    screenSource,
    /visible=\{Boolean\(pendingQualityUpload && qualityPreflight\)\}/
  );
  assert.match(screenSource, /cancelLabel="Choose Another Video"[\s\S]*stackActions/);
  assert.match(dialogSource, /stackActions\?: boolean/);
  assert.match(dialogSource, /stackedActions:\s*\{[\s\S]*flexDirection: 'column'/);
  assert.match(dialogSource, /stackedAction:\s*\{ width: '100%' \}/);
  assert.doesNotMatch(
    screenSource,
    /isWeb && !mobileUploadFlow && selectedVideo && qualityPreflight/
  );
  assert.match(screenSource, /label="Change Video"/);
  assert.match(screenSource, /scrollContentWithStickyFooter/);
  assert.match(reviewSource, /Video quality warning/);
  assert.match(reviewSource, /Tracking might not be accurate because of the video quality/);
  assert.match(reviewSource, /showCancel=\{false\}/);
});
