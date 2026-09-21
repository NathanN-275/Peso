const assert = require('node:assert/strict');
const { access, readFile } = require('node:fs/promises');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const pagesRoot = path.join(projectRoot, 'docs/architecture');
const projectPages = [
  'index.html',
  'architecture.html',
  'backend-flow.html',
  'mobile-flow.html',
  'web-app-flow.html',
];
const requiredNavigation = [
  ['index.html', 'Overview'],
  ['architecture.html', 'Architecture'],
  ['backend-flow.html', 'Backend'],
  ['https://github.com/NathanN-275/Peso/tree/main/docs/product', 'Design docs'],
  ['web-app-flow.html', 'Web Beta'],
];

test('project pages retire the standalone Marketing flow without stale links', async () => {
  await assert.rejects(
    access(path.join(pagesRoot, 'marketing-flow.html')),
    { code: 'ENOENT' },
  );

  for (const pageName of projectPages) {
    const page = await readFile(path.join(pagesRoot, pageName), 'utf8');

    assert.doesNotMatch(page, /marketing-flow\.html/i, pageName);
    assert.doesNotMatch(page, />\s*Marketing\s*<\/a>/i, pageName);
  }
});

test('every project page keeps the required documentation navigation', async () => {
  for (const pageName of projectPages) {
    const page = await readFile(path.join(pagesRoot, pageName), 'utf8');
    const navigation = page.match(/<nav class="site-nav"[^>]*>([\s\S]*?)<\/nav>/)?.[1];

    assert.ok(navigation, `${pageName} must include the project documentation navigation`);
    for (const [href, label] of requiredNavigation) {
      assert.match(
        navigation,
        new RegExp(`<a[^>]*href="${href.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}"[^>]*>\\s*${label}\\s*<\\/a>`),
        `${pageName} must link to ${label}`,
      );

      if (!href.startsWith('https://')) {
        await access(path.join(pagesRoot, href));
      }
    }
  }
});

test('Overview flow cards use the simplified sequence', async () => {
  const overview = await readFile(path.join(pagesRoot, 'index.html'), 'utf8');

  assert.doesNotMatch(overview, /<h3>Marketing flow<\/h3>/);
  assert.match(overview, /03 · WEB BETA[\s\S]*?<h3>Web App flow<\/h3>/);
  assert.match(overview, /04 · PROCESSING[\s\S]*?<h3>Backend flow<\/h3>/);
});

test('architecture keeps the public-site node and Web App entry relationship', async () => {
  const architecture = await readFile(path.join(pagesRoot, 'architecture.html'), 'utf8');
  const webAppFlow = await readFile(path.join(pagesRoot, 'web-app-flow.html'), 'utf8');

  assert.match(architecture, /<h3>Marketing Site<\/h3>/);
  assert.match(architecture, /Landing page, product demo, privacy, and terms\. Links into the Web App\./);
  assert.match(webAppFlow, /<span class="flow-node__tag">From Marketing Site<\/span>/);
  assert.match(webAppFlow, /Public calls to action open the matching <code>\/app<\/code> route\./);
});

test('shared heading typography preserves readable project-page values', async () => {
  const stylesheet = await readFile(path.join(pagesRoot, 'assets/site.css'), 'utf8');

  assert.match(stylesheet, /h1\s*\{[^}]*letter-spacing:\s*-0\.045em;[^}]*line-height:\s*1;/s);
  assert.match(stylesheet, /h2\s*\{[^}]*letter-spacing:\s*-0\.035em;[^}]*line-height:\s*1\.06;/s);
  assert.match(stylesheet, /h3\s*\{[^}]*letter-spacing:\s*-0\.015em;[^}]*line-height:\s*1\.2;/s);
  assert.match(stylesheet, /h4\s*\{[^}]*letter-spacing:\s*-0\.01em;[^}]*line-height:\s*1\.25;/s);
  assert.match(stylesheet, /\.link-card h3\s*\{[^}]*line-height:\s*1\.16;/s);
  assert.match(
    stylesheet,
    /\.hero--compact h1\s*\{[^}]*max-width:\s*780px;[^}]*font-size:\s*clamp\(44px, 6\.2vw, 76px\);[^}]*letter-spacing:\s*-0\.04em;[^}]*line-height:\s*1\.04;/s,
  );
});
