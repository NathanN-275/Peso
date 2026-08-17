const assert = require('node:assert/strict');
const { access, readFile, stat } = require('node:fs/promises');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const homePagePath = path.join(projectRoot, 'web/src/pages/index.astro');
const globalStylesPath = path.join(projectRoot, 'web/src/styles/global.css');
const netlifyConfigPath = path.join(projectRoot, 'netlify.toml');
const demoVideoPath = path.join(projectRoot, 'assets/demo/peso-pose-overlay.mp4');
const projectLogPath = path.join(projectRoot, 'docs/architecture/index.html');
const coachingPositioningPath = path.join(projectRoot, 'docs/marketing/coaching-positioning.md');

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

  for (const title of ['See the evidence', 'How it works', 'Coaching connected to the lift', 'Coaching today', 'Saved Lifts']) {
    assert.match(homePage, new RegExp(`<h2[^>]*class="section-title"[^>]*>${title}<\\/h2>`));
  }

  assert.match(globalStyles, /\.section-title\s*\{[^}]*color:\s*var\(--blue\)/s);
  assert.match(globalStyles, /\.section-subtitle\s*\{[^}]*color:\s*var\(--text\)/s);
});

test('marketing home leads with evidence-backed coaching without overstating the product', async () => {
  const homePage = await readFile(homePagePath, 'utf8');

  assert.match(homePage, /<h1 id="hero-title">Improve each set<\/h1>/);
  assert.match(homePage, /new and self-coached lifters/);
  assert.match(homePage, /Observation<\/span><strong>Depth varied/);
  assert.match(homePage, /Evidence<\/span><strong>Rep by rep/);
  assert.match(homePage, /Next-set cue<\/span><strong>Match your deepest rep/);
  assert.match(homePage, /If the footage is uncertain/);
  assert.match(homePage, /limited detected rep-count context/);
  assert.doesNotMatch(homePage, /replace(?:s|d)? (?:a|your) coach/i);
  assert.doesNotMatch(homePage, /prevent(?:s|ing)? injur/i);
  assert.doesNotMatch(homePage, /guarantee(?:s|d)? (?:strength|results|progress)/i);
});

test('project log documents implemented coaching separately from planned personalization', async () => {
  const projectLog = await readFile(projectLogPath, 'utf8');
  const positioning = await readFile(coachingPositioningPath, 'utf8');

  assert.match(projectLog, /<h1>Improve each <span class="hero-word">set\.<\/span><\/h1>/);
  assert.match(projectLog, /Explainable cues, built from visible evidence/);
  assert.match(projectLog, /coaching-build-card__status">Implemented/);
  assert.match(projectLog, /coaching-build-card__status">Limited today/);
  assert.match(projectLog, /Rules plus history before machine learning/);
  assert.match(projectLog, /0001-rules-plus-history-before-ml\.md/);
  assert.match(positioning, /Tracking is evidence for the coaching result/);
  assert.match(positioning, /Do not claim that Peso/);
});
