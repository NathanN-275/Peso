const assert = require('node:assert/strict');
const path = require('node:path');
const crypto = require('node:crypto');
const forgePath = path.resolve(process.argv[2]);
const forge = require(forgePath);
const a = forge.asn1, U = a.Class.UNIVERSAL, T = a.Type;
let passed = 0, failed = 0;
function check(name, fn) {
  try { fn(); passed++; }
  catch (error) { failed++; console.log(`FAIL ${name}: ${error.message}`); }
}
const invalid = /valid RSASSA-PKCS1-v1_5 DigestInfo/;
for (const exponent of [3, 65537]) {
  // Synthetic keys are generated in memory only, never printed or saved.
  const keys = crypto.generateKeyPairSync('rsa', {
    modulusLength: 1024, publicExponent: exponent,
    privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
    publicKeyEncoding: { type: 'pkcs1', format: 'pem' },
  });
  const priv = forge.pki.privateKeyFromPem(keys.privateKey);
  const pub = forge.pki.publicKeyFromPem(keys.publicKey);
  const message = 'Peso NULL assessment';
  function md(algorithm = 'sha256') { return forge.md[algorithm].create().update(message); }
  function signature(parameters, algorithm = 'sha256', extra = false, ber = false) {
    const digest = md(algorithm).digest().getBytes();
    const children = [a.create(U, T.OID, false, a.oidToDer(forge.pki.oids[algorithm]).getBytes())];
    if (parameters !== undefined) children.push(a.create(U, T.NULL, false, parameters));
    if (extra) children.push(a.create(U, T.OCTETSTRING, false, 'extra'));
    const info = a.create(U, T.SEQUENCE, true, [a.create(U, T.SEQUENCE, true, children), a.create(U, T.OCTETSTRING, false, digest)]);
    let der = a.toDer(info).getBytes();
    if (parameters !== undefined) assert.equal(a.fromDer(der).value[0].value[1].value, parameters);
    if (ber) { assert.ok(der.charCodeAt(1) < 128); der = '\x30\x80' + der.slice(2) + '\x00\x00'; }
    return priv.sign(der, 'NONE');
  }
  for (const algorithm of ['sha1', 'sha256', 'sha384', 'sha512']) {
    const digest = md(algorithm).digest().getBytes();
    for (const parameters of [undefined, '']) {
      check(`e=${exponent} ${algorithm} valid NULL=${parameters === ''}`, () => assert.equal(pub.verify(digest, signature(parameters, algorithm)), true));
    }
    for (const bytes of ['x', 'x'.repeat(8), 'x'.repeat(32), '\x00', '\xff']) {
      check(`e=${exponent} ${algorithm} invalid NULL ${bytes.length} bytes`, () => assert.throws(() => pub.verify(digest, signature(bytes, algorithm)), invalid));
    }
    check(`e=${exponent} ${algorithm} changed digest`, () => assert.equal(pub.verify('y'.repeat(digest.length), signature('', algorithm)), false));
    for (const parameters of [undefined, '']) {
      check(`e=${exponent} ${algorithm} extra child NULL=${parameters === ''}`, () => assert.throws(() => pub.verify(digest, signature(parameters, algorithm, true)), invalid));
    }
  }
  const digest = md().digest().getBytes();
  check(`e=${exponent} legacy BER empty NULL`, () => assert.equal(pub.verify(digest, signature('', 'sha256', false, true)), true));
  check(`e=${exponent} legacy BER invalid NULL`, () => assert.throws(() => pub.verify(digest, signature('x', 'sha256', false, true)), invalid));
  check(`e=${exponent} native PKCS1 valid`, () => assert.equal(pub.verify(digest, crypto.sign('RSA-SHA256', Buffer.from(message), keys.privateKey).toString('binary')), true));
  check(`e=${exponent} native PKCS1 wrong digest`, () => assert.equal(pub.verify('y'.repeat(digest.length), crypto.sign('RSA-SHA256', Buffer.from(message), keys.privateKey).toString('binary')), false));
  const pss = forge.pss.create({ md: forge.md.sha256.create(), mgf: forge.mgf.mgf1.create(forge.md.sha256.create()), saltLength: 20 });
  const pssSignature = priv.sign(md(), pss);
  check(`e=${exponent} PSS valid`, () => assert.equal(pub.verify(digest, pssSignature, pss), true));
  check(`e=${exponent} PSS wrong digest`, () => assert.equal(pub.verify('y'.repeat(digest.length), pssSignature, pss), false));
  const rawSignature = priv.sign(digest, 'NONE');
  check(`e=${exponent} NONE valid`, () => assert.equal(pub.verify(digest, rawSignature, 'NONE'), true));
  check(`e=${exponent} NONE wrong digest`, () => assert.equal(pub.verify('y'.repeat(digest.length), rawSignature, 'NONE'), false));
}
if (process.argv[3]) {
  const consumer = require(path.resolve(process.argv[3]));
  check('Expo consumer loads assessed Forge copy', () => {
    const r = require('node:module').createRequire(path.join(path.resolve(process.argv[3]), 'build/main.js'));
    assert.equal(r.resolve('node-forge'), path.join(forgePath, 'lib/index.js'));
  });
  const keys = crypto.generateKeyPairSync('rsa', {
    modulusLength: 2048, publicExponent: 65537,
    privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
    publicKeyEncoding: { type: 'pkcs1', format: 'pem' },
  });
  const keyPair = consumer.convertKeyPairPEMToKeyPair({ privateKeyPEM: keys.privateKey, publicKeyPEM: keys.publicKey });
  let cert;
  check('Expo self-signed certificate creation', () => {
    cert = consumer.generateSelfSignedCodeSigningCertificate({ keyPair, validityNotBefore: new Date('2025-01-01T00:00:00Z'), validityNotAfter: new Date('2028-01-01T00:00:00Z'), commonName: 'Peso isolated assessment' });
  });
  check('Expo self-signed certificate validation', () => consumer.validateSelfSignedCertificate(cert, keyPair));
  check('Expo certificate PEM roundtrip', () => assert.equal(consumer.convertCertificatePEMToCertificate(consumer.convertCertificateToCertificatePEM(cert)).subject.getField('CN').value, 'Peso isolated assessment'));
  check('Expo buffer signing and verification', () => assert.equal(typeof consumer.signBufferRSASHA256AndVerify(keyPair.privateKey, cert, Buffer.from('Peso consumer check')), 'string'));
  check('Expo wrong private key rejected', () => {
    const other = crypto.generateKeyPairSync('rsa', { modulusLength: 2048, privateKeyEncoding: { type: 'pkcs1', format: 'pem' }, publicKeyEncoding: { type: 'pkcs1', format: 'pem' } });
    assert.throws(() => consumer.signBufferRSASHA256AndVerify(forge.pki.privateKeyFromPem(other.privateKey), cert, Buffer.from('Peso consumer check')));
  });
}
console.log(`Assessment ${process.version}: ${passed} pass, ${failed} fail; ${forgePath}`);
console.log('Synthetic private-key acceptance checks, not no-private-key forgery.');
process.exitCode = failed ? 1 : 0;
