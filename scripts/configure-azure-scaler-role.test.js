const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const scriptPath = path.join(__dirname, 'configure_azure_scaler_role.sh');
const ownerConnection =
  'postgresql://postgres:owner-password@db.iseqgaewjpjcxrndibep.supabase.co:5432/postgres?sslmode=require';

function makeFakePsql() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'peso-scaler-role-'));
  const executable = path.join(directory, 'psql');
  const argvPath = path.join(directory, 'argv');
  const stdinPath = path.join(directory, 'stdin');
  fs.writeFileSync(
    executable,
    '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$FAKE_PSQL_ARGV_PATH"\ncat > "$FAKE_PSQL_STDIN_PATH"\n'
  );
  fs.chmodSync(executable, 0o755);
  return { directory, argvPath, stdinPath };
}

function runScript(fakePsql, overrides = {}) {
  return spawnSync(scriptPath, [], {
    encoding: 'utf8',
    env: {
      ...process.env,
      PATH: `${fakePsql.directory}${path.delimiter}${process.env.PATH}`,
      FAKE_PSQL_ARGV_PATH: fakePsql.argvPath,
      FAKE_PSQL_STDIN_PATH: fakePsql.stdinPath,
      SUPABASE_DB_URL: ownerConnection,
      AZURE_SCALER_POSTGRES_PASSWORD: `quote' space $() ; & | < > \\ "`,
      AZURE_SCALER_POSTGRES_ROLE: 'peso_azure_scaler_student',
      ...overrides,
    },
  });
}

test('scaler password stays out of psql argv and is loaded from the environment', (context) => {
  const fakePsql = makeFakePsql();
  context.after(() => fs.rmSync(fakePsql.directory, { recursive: true, force: true }));

  const scalerPassword = `quote' space $() ; & | < > \\ "`;
  const result = runScript(fakePsql, { AZURE_SCALER_POSTGRES_PASSWORD: scalerPassword });

  assert.equal(result.status, 0, result.stderr);
  const argv = fs.readFileSync(fakePsql.argvPath, 'utf8');
  assert.doesNotMatch(argv, /--set=scaler_password=/);
  assert.equal(argv.includes(scalerPassword), false);
  assert.match(argv, /--set=scaler_role=peso_azure_scaler_student/);

  const sql = fs.readFileSync(fakePsql.stdinPath, 'utf8');
  assert.match(sql, /^\\getenv scaler_password AZURE_SCALER_POSTGRES_PASSWORD$/m);
  assert.match(sql, /:'scaler_password'/);
  assert.equal(sql.includes(scalerPassword), false);
});

test('approved scaler role executes psql and an unapproved role fails first', (context) => {
  const fakePsql = makeFakePsql();
  context.after(() => fs.rmSync(fakePsql.directory, { recursive: true, force: true }));

  const valid = runScript(fakePsql);
  assert.equal(valid.status, 0, valid.stderr);
  assert.equal(fs.existsSync(fakePsql.argvPath), true);

  fs.rmSync(fakePsql.argvPath);
  fs.rmSync(fakePsql.stdinPath);
  const invalid = runScript(fakePsql, { AZURE_SCALER_POSTGRES_ROLE: 'postgres' });
  assert.notEqual(invalid.status, 0);
  assert.match(invalid.stderr, /must be an approved environment-specific role name/);
  assert.equal(fs.existsSync(fakePsql.argvPath), false);
  assert.equal(fs.existsSync(fakePsql.stdinPath), false);
});
