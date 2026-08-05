const assert = require('node:assert/strict');
const { access, readFile, stat } = require('node:fs/promises');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const homePagePath = path.join(projectRoot, 'web/src/pages/index.astro');
const globalStylesPath = path.join(projectRoot, 'web/src/styles/global.css');
const netlifyConfigPath = path.join(projectRoot, 'netlify.toml');
const demoVideoPath = path.join(projectRoot, 'assets/demo/peso-pose-overlay.mp4');

test('marketing home defers the optimized demo video and preserves accessible controls', async () => {
  const homePage = await readFile(homePagePath, 'utf8');
  const globalStyles = await readFile(globalStylesPath, 'utf8');
  const demoVideoStats = await stat(demoVideoPath);

  assert.match(homePage, /src="\/demo\/peso-demo-thumbnail\.jpg"/);
  assert.match(homePage, /peso-pose-overlay\.mp4\?url/);
  assert.match(homePage, /data-src=\{demoVideoUrl\}/);
  assert.match(homePage, /poster="\/demo\/peso-pose-overlay\.jpg"/);
  assert.match(homePage, /\bcontrols\b/);
  assert.match(homePage, /\bloop\b/);
  assert.match(homePage, /\bmuted\b/);
  assert.match(homePage, /\bplaysinline\b/);
  assert.match(homePage, /preload="none"/);
  assert.match(homePage, /kind="descriptions"/);
  assert.match(homePage, /IntersectionObserver/);
  assert.match(homePage, /intersectionRatio >= 0\.25/);
  assert.match(homePage, /prefers-reduced-motion: reduce/);
  assert.doesNotMatch(homePage, /peso-demo-video\.gif/);
  assert.match(homePage, /class="product-outline"/);
  assert.match(homePage, /class="demo-outline"/);
  assert.match(globalStyles, /\.product-outline\s*\{[^}]*border:/s);
  assert.match(globalStyles, /\.demo-outline\s*\{[^}]*border:/s);
  assert.ok(
    demoVideoStats.size <= 600 * 1024,
    `expected demo video to be at most 600 KiB, received ${demoVideoStats.size} bytes`,
  );

  await access(path.join(projectRoot, 'web/public/demo/peso-demo-thumbnail.jpg'));
  await assert.rejects(
    access(path.join(projectRoot, 'web/public/demo/peso-demo-video.gif')),
    { code: 'ENOENT' },
  );
});

test('Netlify redirects the retired GIF and caches marketing media', async () => {
  const netlifyConfig = await readFile(netlifyConfigPath, 'utf8');

  assert.match(
    netlifyConfig,
    /from = "\/demo\/peso-demo-video\.gif"\s+to = "\/demo\/peso-pose-overlay\.jpg"\s+status = 301\s+force = true/s,
  );
  assert.match(
    netlifyConfig,
    /for = "\/marketing-assets\/\*"\s+\[headers\.values\]\s+Cache-Control = "public, max-age=31536000, immutable"/s,
  );
  assert.match(
    netlifyConfig,
    /for = "\/demo\/\*"\s+\[headers\.values\]\s+Cache-Control = "public, max-age=604800"/s,
  );
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
