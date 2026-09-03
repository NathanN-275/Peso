const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

test('web beta requires setup before upload or camera recording', () => {
  const routes = read('src/web/web-analysis-routes.tsx');
  const app = read('src/web/web-app.tsx');

  assert.match(routes, /if \(!pendingVideoSetup\) \{\s*return <Navigate to="\/setup" replace \/>;\s*\}/);
  assert.match(routes, /navigate\('\/submit'\)/);
  assert.match(routes, /selection\.exercise === SIDE_SQUAT_SETUP\.exercise/);
  assert.match(app, /path="\/setup" element=\{<WebVideoSetupRoute \/>\}/);
  assert.match(app, /path="\/submit" element=\{<WebSubmissionChoiceRoute \/>\}/);
});

test('web recording exposes a trim control before handing off the selected asset', () => {
  const recorder = read('src/screens/WebVideoRecorderScreen.tsx');

  assert.match(recorder, /testID="recording-trim-track"/);
  assert.match(recorder, /accessibilityLabel="Trim recording"/);
  assert.match(recorder, /duration: result\.durationMs/);
  assert.match(recorder, /mimeType: result\.file\.type/);
  assert.match(recorder, /file: result\.file/);
});
