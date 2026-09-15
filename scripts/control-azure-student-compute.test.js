const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const controlScript = path.resolve(__dirname, 'control_azure_student_compute.sh');

function withAbsentAzureResources(run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-azure-control-'));
  const az = path.join(directory, 'az');
  const summary = path.join(directory, 'summary.md');
  fs.writeFileSync(az, `#!/bin/sh
case "$*" in
  "containerapp job show "*) exit 3 ;;
  "containerapp show "*) exit 3 ;;
  "containerapp revision list "*) exit 0 ;;
  *) echo "unexpected az invocation: $*" >&2; exit 99 ;;
esac
`);
  fs.chmodSync(az, 0o755);
  try {
    run({
      env: {
        ...process.env,
        PATH: `${directory}:${process.env.PATH}`,
        GITHUB_STEP_SUMMARY: summary,
      },
      summary,
    });
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

test('pause-all treats never-deployed Student workloads as zero compute and records evidence', () => {
  withAbsentAzureResources(({ env, summary }) => {
    const result = spawnSync(controlScript, ['pause-all'], { encoding: 'utf8', env });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /API resource present: false/);
    assert.match(result.stdout, /Worker resource present: false/);
    assert.match(result.stdout, /API replicas: 0/);
    assert.match(result.stdout, /Worker active executions: 0/);
    assert.match(result.stdout, /Worker scaler query: `resource absent`/);
    assert.equal(fs.readFileSync(summary, 'utf8'), result.stdout);
  });
});

test('resume fails closed when Student compute was never deployed', () => {
  withAbsentAzureResources(({ env }) => {
    const result = spawnSync(controlScript, ['resume-all'], { encoding: 'utf8', env });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Cannot resume absent Student worker/);
  });
});
