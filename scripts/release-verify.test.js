const assert = require('node:assert/strict');
const test = require('node:test');

const { releaseChecks, runReleaseChecks } = require('./release-verify');

test('release verification runs serially and stops at the first failed gate', () => {
  const executed = [];
  const checks = [
    { name: 'first', command: 'one', args: [] },
    { name: 'second', command: 'two', args: [] },
    { name: 'third', command: 'three', args: [] },
  ];

  const result = runReleaseChecks(checks, (check) => {
    executed.push(check.name);
    return check.name === 'second' ? 1 : 0;
  });

  assert.equal(result, 1);
  assert.deepEqual(executed, ['first', 'second']);
});

test('configured release verification stops on web audit failure before any export', () => {
  const executed = [];
  const result = runReleaseChecks(undefined, check => {
    executed.push(check);
    return check.args.includes('scripts/npm-audit-web-ci.js') ? 1 : 0;
  });
  assert.equal(result, 1);
  assert.deepEqual(executed.slice(0, 2).map(check => check.args), [
    ['scripts/dependency-patches.js', 'verify'], ['scripts/release-env.js'],
  ]);
  assert.equal(executed.at(-1).command, process.execPath);
  assert.deepEqual(executed.at(-1).args, ['scripts/npm-audit-web-ci.js']);
  assert(!executed.some(check => /build|export/.test(check.args.join(' '))));
  assert(releaseChecks.some(check => check.args.includes('audit:ci')));
});
