const assert = require('node:assert/strict');
const { access, readFile } = require('node:fs/promises');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const homePagePath = path.join(projectRoot, 'web/src/pages/index.astro');
const globalStylesPath = path.join(projectRoot, 'web/src/styles/global.css');

test('marketing home uses the supplied demo GIF, a static thumbnail, and simple outlines', async () => {
  const homePage = await readFile(homePagePath, 'utf8');
  const globalStyles = await readFile(globalStylesPath, 'utf8');

  assert.match(homePage, /src="\/demo\/peso-demo-thumbnail\.jpg"/);
  assert.match(homePage, /src="\/demo\/peso-demo-video\.gif"/);
  assert.doesNotMatch(homePage, /peso-pose-overlay\.mp4/);
  assert.match(homePage, /class="product-outline"/);
  assert.match(homePage, /class="demo-outline"/);
  assert.match(globalStyles, /\.product-outline\s*\{[^}]*border:/s);
  assert.match(globalStyles, /\.demo-outline\s*\{[^}]*border:/s);

  await access(path.join(projectRoot, 'web/public/demo/peso-demo-thumbnail.jpg'));
  await access(path.join(projectRoot, 'web/public/demo/peso-demo-video.gif'));
});

test('content sections use blue titles followed by white subheadings', async () => {
  const homePage = await readFile(homePagePath, 'utf8');
  const globalStyles = await readFile(globalStylesPath, 'utf8');

  for (const title of ['Real analysis', 'How it works', 'Available feedback', 'Saved Lifts']) {
    assert.match(homePage, new RegExp(`<h2[^>]*class="section-title"[^>]*>${title}<\\/h2>`));
  }

  assert.match(globalStyles, /\.section-title\s*\{[^}]*color:\s*var\(--blue\)/s);
  assert.match(globalStyles, /\.section-subtitle\s*\{[^}]*color:\s*var\(--text\)/s);
});
