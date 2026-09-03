const assert = require('node:assert/strict');
const test = require('node:test');

const { runReleaseChecks } = require('./release-verify');

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
