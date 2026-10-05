const assert = require('node:assert/strict');
const { test } = require('node:test');
const braces = require('braces');
const forge = require('node-forge');
const { generateKeyPairSync } = require('node:crypto');
const vm = require('node:vm');

// Fixture keys exist only in memory, never in Git, logs, or provider state.
const keys = generateKeyPairSync('rsa', {
  modulusLength: 1024, publicExponent: 3,
  privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
  publicKeyEncoding: { type: 'pkcs1', format: 'pem' },
});
const privateKey = forge.pki.privateKeyFromPem(keys.privateKey);
const publicKey = forge.pki.publicKeyFromPem(keys.publicKey);
const digest = forge.md.sha256.create().update('Peso dependency regression').digest().getBytes();
function signature(extra, withNull = true) {
  const a = forge.asn1, U = a.Class.UNIVERSAL, T = a.Type;
  const algorithm = [a.create(U, T.OID, false, a.oidToDer(forge.pki.oids.sha256).getBytes())];
  if (withNull) algorithm.push(a.create(U, T.NULL, false, ''));
  if (extra) algorithm.push(a.create(U, T.OCTETSTRING, false, 'unconsumed child'));
  const info = a.create(U, T.SEQUENCE, true, [
    a.create(U, T.SEQUENCE, true, algorithm), a.create(U, T.OCTETSTRING, false, digest),
  ]);
  // Sign a deliberately malformed structure; this tests acceptance, not no-key forgery.
  return privateKey.sign(a.toDer(info).getBytes(), 'NONE');
}

test('installed braces rejects excessive nesting before recursive processing', () => {
  assert.throws(() => braces.parse('{'.repeat(101) + 'a,b' + '}'.repeat(101)), /exceeds max depth/);
});

test('installed RSA verifier rejects an extra nested DigestAlgorithm child', () => {
  assert.throws(() => publicKey.verify(digest, signature(true)), /valid RSASSA-PKCS1-v1_5 DigestInfo/);
});

for (const method of ['parse', 'compile', 'expand', 'stringify']) {
  test(`installed braces ${method} enforces depth limits and accepts ordinary patterns`, () => {
    for (const n of [101, 3000, 4998]) {
      assert.throws(() => braces[method]('{'.repeat(n) + 'a,b' + '}'.repeat(n)), /exceeds max depth/);
    }
    assert.doesNotThrow(() => braces[method]('{'.repeat(100) + 'a,b' + '}'.repeat(100)));
    assert.throws(() => braces[method]('('.repeat(101) + 'a' + ')'.repeat(101)), /exceeds max depth/);
    assert.throws(() => braces[method]('{{a,b},c}', { maxDepth: 1.5 }), /exceeds max depth/);
    assert.throws(() => braces[method]('{'.repeat(101) + 'a' + '}'.repeat(101), { maxDepth: Infinity }), /exceeds max depth/);
  });
}

test('installed brace walkers reject caller-supplied deep ASTs', () => {
  for (const method of ['compile', 'expand', 'stringify']) {
    let ast = { type: 'text', value: 'a' };
    for (let n = 0; n < 101; n++) ast = { type: 'brace', nodes: [ast] };
    ast = { type: 'root', nodes: [ast] };
    assert.throws(() => braces[method](ast), /exceeds max depth/);
  }
});

test('installed brace expansion rejects cyclic parent chains within a bounded run', () => {
  for (const size of [1, 2]) {
    const ast = { type: 'paren', nodes: [{ type: 'text', value: 'a' }] };
    ast.parent = size === 1 ? ast : { type: 'paren', parent: ast };
    assert.throws(() => vm.runInNewContext('expand(ast)', { expand: braces.expand, ast }, { timeout: 250 }),
      error => error instanceof RangeError && /parent chain contains a cycle/.test(error.message));
  }
});

test('installed braces retains published expansion, compilation, and escaped stringify behavior', () => {
  assert.deepEqual(braces.expand('app/*.{ts,tsx}'), ['app/*.ts', 'app/*.tsx']);
  assert.equal(braces.compile('a{b,c}d'), 'a(b|c)d');
  for (const input of ['{{a}}', '{a,{b}}', '{{x}y}', '{a,{b,{c}}}', '{}{a}', '{1..8}']) {
    assert.equal(braces.stringify(input, { escapeInvalid: true }), input);
  }
});

for (const withNull of [false, true]) {
  test(`installed RSA verifier accepts valid DigestAlgorithm optional NULL=${withNull}`, () => {
    assert.equal(publicKey.verify(digest, signature(false, withNull)), true);
    assert.equal(publicKey.verify('x'.repeat(digest.length), signature(false, withNull)), false);
    assert.throws(() => publicKey.verify(digest, signature(true, withNull)), /valid RSASSA-PKCS1-v1_5 DigestInfo/);
  });
}
