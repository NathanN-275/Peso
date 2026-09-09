const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const { validateDatabaseUrl, validateStudentEnvironment, STUDENT_PROJECT, PRODUCTION_PROJECT,
  STUDENT_SUPABASE_URL, STUDENT_ORIGIN, verifyStudentKeys } = require('./student-environment');

const direct = `postgresql://postgres:test@db.${STUDENT_PROJECT}.supabase.co:5432/postgres?sslmode=require`;
const scaler = `postgresql://peso_azure_scaler_student.${STUDENT_PROJECT}:test@aws-0-us-west-2.pooler.supabase.com:5432/postgres?sslmode=require`;
const jwt = (ref, role) => `eyJhbGciOiJIUzI1NiJ9.${Buffer.from(JSON.stringify({ref, role})).toString('base64url')}.test`;
const environment = () => ({
  SUPABASE_DB_URL: direct,
  SCALER_POSTGRES_CONNECTION: scaler,
  RUNTIME_SUPABASE_URL: STUDENT_SUPABASE_URL,
  EXPO_PUBLIC_SUPABASE_URL: STUDENT_SUPABASE_URL,
  STUDENT_NETLIFY_ORIGIN: STUDENT_ORIGIN,
  RUNTIME_SUPABASE_SERVICE_ROLE_KEY: jwt(STUDENT_PROJECT, 'service_role'),
  RUNTIME_SUPABASE_JWT_SECRET: 'student-jwt-secret',
  EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: jwt(STUDENT_PROJECT, 'anon'),
});

test('Student accepts only its exact direct and pooler database identities', () => {
  assert.equal(validateDatabaseUrl(direct), true);
  assert.equal(validateDatabaseUrl(scaler, {scaler: true}), true);
  assert.deepEqual(validateStudentEnvironment(environment()), []);
  for (const url of [
    direct.replace(STUDENT_PROJECT, PRODUCTION_PROJECT),
    direct.replace('.supabase.co', '.supabase.co.attacker.test'),
    direct.replace('sslmode=require', 'sslmode=disable'),
    direct + '&host=db.' + PRODUCTION_PROJECT + '.supabase.co',
    direct + '&sslmode=disable',
    direct.replace('/postgres?', '/other?'),
    scaler.replace(STUDENT_PROJECT, PRODUCTION_PROJECT),
    scaler.replace('peso_azure_scaler_student.', 'postgres.'),
  ]) assert.equal(validateDatabaseUrl(url, {scaler: url.includes('pooler')}), false);
});

test('Student rejects production URLs, JWTs, wrong roles and unrelated origins', () => {
  for (const [name, value] of Object.entries({
    RUNTIME_SUPABASE_URL: `https://${PRODUCTION_PROJECT}.supabase.co`,
    EXPO_PUBLIC_SUPABASE_URL: `https://${PRODUCTION_PROJECT}.supabase.co`,
    RUNTIME_SUPABASE_SERVICE_ROLE_KEY: jwt(PRODUCTION_PROJECT, 'service_role'),
    RUNTIME_SUPABASE_JWT_SECRET: '',
    EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY: jwt(STUDENT_PROJECT, 'service_role'),
    STUDENT_NETLIFY_ORIGIN: 'https://peso-webapp.netlify.app',
  })) assert.ok(validateStudentEnvironment({...environment(), [name]: value}).length, name);
});

test('Missing connections and malformed keys fail without exposing credentials', () => {
  assert.ok(validateStudentEnvironment({}).length);
  const errors = validateStudentEnvironment({...environment(), RUNTIME_SUPABASE_SERVICE_ROLE_KEY: 'eyJ-secret'});
  assert.ok(errors.length);
  assert.doesNotMatch(errors.join('\n'), /eyJ-secret/);
});

test('online verification proves the JWT secret against only peso-staging', async (context) => {
  const calls = [];
  context.mock.method(global, 'fetch', async (url, options) => {
    calls.push({url, options});
    return {ok: true, body: {cancel: async () => {}}};
  });
  const env = environment();
  await verifyStudentKeys(env);
  assert.equal(calls.length, 3);
  assert.ok(calls.every(({url}) => url.startsWith(STUDENT_SUPABASE_URL + '/')));
  const token = calls[2].options.headers.Authorization.replace('Bearer ', '');
  const [header, payload, signature] = token.split('.');
  const expected = crypto.createHmac('sha256', env.RUNTIME_SUPABASE_JWT_SECRET)
    .update(`${header}.${payload}`).digest('base64url');
  assert.equal(signature, expected);
  assert.equal(JSON.parse(Buffer.from(payload, 'base64url')).ref, STUDENT_PROJECT);
});

test('online verification fails closed when peso-staging rejects the JWT secret', async (context) => {
  let call = 0;
  context.mock.method(global, 'fetch', async () => ({
    ok: ++call < 3,
    body: {cancel: async () => {}},
  }));
  await assert.rejects(verifyStudentKeys(environment()), /JWT_SECRET was rejected/);
});
