const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const test = require('node:test');

const projectRoot = path.resolve(__dirname, '..');
const compileFontSources = `
  const fs = require('node:fs');
  const postcss = require('postcss');
  const { plugins } = require('./postcss.config');
  postcss(plugins).process(fs.readFileSync('global.css', 'utf8'), {
    from: 'global.css',
  }).then(result => {
    const sources = [];
    result.root.walkAtRules('font-face', rule => {
      rule.walkDecls('src', declaration => sources.push(declaration.value));
    });
    process.stdout.write(JSON.stringify(sources));
  }).catch(error => { console.error(error); process.exitCode = 1; });
`;

for (const routerBase of ['/', '/app']) {
  test(`font faces use only the ${routerBase} mount`, () => {
    const sources = JSON.parse(execFileSync(process.execPath, ['-e', compileFontSources], {
      cwd: projectRoot,
      env: { ...process.env, EXPO_PUBLIC_WEB_ROUTER_BASE: routerBase },
      encoding: 'utf8',
    }));
    const directory = routerBase === '/' ? '/fonts/' : '/app/fonts/';
    const source = filename => `url("${directory}${filename}") format("woff2")`;
    assert.deepEqual(sources, [
      source('archivo-black-latin.woff2'),
      ...Array(4).fill(source('inter-latin-variable.woff2')),
    ]);
  });
}
