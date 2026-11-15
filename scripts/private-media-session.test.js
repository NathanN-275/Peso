const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createPrivateMediaSessionController } = require('../lib/privateMediaSession');
const AUTH = 'https://project.supabase.co/auth/v1';
const BACKEND = 'https://api.usepeso.com';
const STORAGE_KEY = 'sb-project-auth-token';
const JOURNAL = `${STORAGE_KEY}:peso-private-media-transition:v1`;
const COMPLETIONS = `${STORAGE_KEY}:peso-private-media-completions:v1`;
const OWNER = '11111111-1111-4111-8111-111111111111';
const OTHER = '22222222-2222-4222-8222-222222222222';
const OLD = '33333333-3333-4333-8333-333333333333';
const NEW = '44444444-4444-4444-8444-444444444444';
const THIRD = '55555555-5555-4555-8555-555555555555';
const STAMP = '2026-10-30T22:00:00Z';
function session(owner = OWNER, id = OLD, extras = {}) {
  const body = Buffer.from(JSON.stringify({ iss: AUTH, sub: owner, session_id: id, ...extras })).toString('base64url');
  return { access_token: `synthetic.${body}.signature`, refresh_token: 'synthetic-refresh', user: { id: owner } };
}
function page(owner = OWNER, id = OLD, extras = {}) {
  return { scope: 'local', owner_id: owner, session_id: id, completed_at: STAMP,
    replayed: false, next_cursor: null, cookie_cleanup_complete: true, ...extras };
}
const globalReceipt = () => ({ scope: 'global', completed_at: STAMP, replayed: false });
function deferred() { let resolve; const promise = new Promise((yes) => { resolve = yes; }); return { promise, resolve }; }
const tick = () => new Promise((resolve) => setImmediate(resolve));
function fixture(options = {}) {
  const data = options.data || new Map();
  if (!options.data && options.initial !== null) data.set(STORAGE_KEY, JSON.stringify(options.initial || session()));
  const calls = [];
  const storage = {
    async getItem(key) { calls.push(['get', key]); return data.get(key) ?? null; },
    async setItem(key, value) {
      calls.push(['set', key]);
      if (options.failWrite?.(key, value)) throw new Error('SYNTHETIC secret must be sanitized');
      data.set(key, value);
    },
    async removeItem(key) { calls.push(['remove', key]); if (options.failRemove?.(key)) throw new Error('SYNTHETIC'); data.delete(key); },
  };
  const controller = createPrivateMediaSessionController({ enabled: options.enabled ?? true,
    browserInventoryVersion: options.browserInventoryVersion ?? 1, storage, storageKey: STORAGE_KEY, authUrl: AUTH, getBackendUrl: options.getBackendUrl || (() => BACKEND),
    getAuthMutationKey: options.getAuthMutationKey || (() => null),
    getLogoutIntentKey: options.getLogoutIntentKey || (() => undefined),
    runExclusive: options.runExclusive || (async (action) => { calls.push(['lock']); return action(); }),
    stopMedia: async () => { calls.push(['stop']); if (options.stop) return options.stop(); },
    onActiveKey: (key) => calls.push(['active', key]),
    validateIncomingSession: options.missingValidation ? undefined : async (token, backend) => {
      calls.push(['validate', token, backend]);
      if (options.validate) return options.validate(token, backend);
      const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
      return { owner_id: claims.sub, session_id: claims.session_id, accepted: true };
    },
    getGlobalReceipt: async (...args) => { calls.push(['global', ...args]); return options.global ? options.global(...args) : null; },
    revokeSession: async (...args) => {
      calls.push(['revoke', ...args]);
      if (options.revoke) return options.revoke(...args);
      const claims = JSON.parse(Buffer.from(args[0].split('.')[1], 'base64url').toString());
      return page(claims.sub, claims.session_id);
    },
  });
  return { controller, data, calls, storage, write: (value) => controller.storage.setItem(STORAGE_KEY, JSON.stringify(value)),
    journal: () => JSON.parse(data.get(JOURNAL)), raw: () => data.has(STORAGE_KEY) ? JSON.parse(data.get(STORAGE_KEY)) : null };
}
const count = (f, name) => f.calls.filter(([what]) => what === name).length;

test('disabled storage and raw events preserve existing behavior without transition work', async () => {
  const f = fixture({ enabled: false }); assert.equal(f.controller.storage, f.storage);
  const next = session(OTHER, NEW); f.controller.authStateChanged('INITIAL_SESSION', next); await f.controller.initialize();
  assert.equal(f.controller.getSnapshot().session, next); assert.equal(await f.controller.waitForSession(next), next);
  assert.equal(count(f, 'lock'), 0); assert.equal(count(f, 'revoke'), 0);
});
test('fresh state and recovered session are accepted from actual storage', async () => {
  for (const initial of [null, session()]) { const f = fixture({ initial }); await f.controller.initialize();
    assert.equal(f.controller.getSnapshot().status, 'ready'); assert.deepEqual(f.controller.getSnapshot().session, initial); }
});
test('first login journals without revoking a nonexistent session', async () => {
  const f = fixture({ initial: null }); await f.controller.initialize(); await f.write(session());
  assert.equal(f.journal().from, null); assert.equal(f.journal().stage, 'committed'); assert.equal(count(f, 'revoke'), 0);
});
test('same provider-session refresh preserves media and fresh token', async () => {
  const f = fixture(); await f.controller.initialize(); const next = session(OWNER, OLD, { seq: 2 }); await f.write(next);
  assert.equal(count(f, 'stop'), 0); assert.equal(count(f, 'revoke'), 0); assert.deepEqual(f.controller.getSnapshot().session, next);
});
test('same-owner and different-owner replacement revoke captured outgoing session before overwrite', async () => {
  for (const owner of [OWNER, OTHER]) { const f = fixture({ revoke: async (token) => {
    assert.deepEqual(f.raw(), session()); assert.equal(token, session().access_token);
    assert.equal(f.journal().stage, 'pending'); assert.equal(f.controller.getSnapshot().session, null); return page();
  } }); await f.controller.initialize(); await f.write(session(owner, NEW));
  assert.equal(count(f, 'revoke'), 1); assert.equal(f.journal().stage, 'committed'); assert.equal(f.raw().user.id, owner);
  assert.ok(f.calls.findIndex(([x]) => x === 'stop') < f.calls.findIndex(([x]) => x === 'revoke')); }
});
test('verifier and user keys remain outside exact main-session interception', async () => {
  const f = fixture(); await f.controller.storage.setItem(`${STORAGE_KEY}-code-verifier`, 'pkce');
  await f.controller.storage.removeItem(`${STORAGE_KEY}-user`); assert.equal(count(f, 'lock'), 0); assert.equal(count(f, 'revoke'), 0);
});
test('release failure blocks remote dispatch and incoming persistence', async () => {
  const f = fixture({ stop: async () => { throw new Error('PRIVATE'); } }); await f.controller.initialize();
  await assert.rejects(f.write(session(OTHER, NEW)), /Unable/); assert.deepEqual(f.raw(), session());
  assert.equal(count(f, 'revoke'), 0); assert.equal(f.controller.getSnapshot().status, 'blocked');
});
test('lost revocation response retains old token and noncredential intent without replay', async () => {
  const f = fixture({ revoke: async () => { throw new Error('PRIVATE'); } }); await f.controller.initialize();
  await assert.rejects(f.write(session(OTHER, NEW)), /Unable/); assert.deepEqual(f.raw(), session());
  assert.equal(count(f, 'revoke'), 1); assert.equal(f.journal().stage, 'pending'); assert.ok(!JSON.stringify(f.journal()).includes('synthetic'));
});
test('journal intent write failure prevents revocation', async () => {
  const f = fixture({ failWrite: (key) => key === JOURNAL }); await f.controller.initialize();
  await assert.rejects(f.write(session(OTHER, NEW))); assert.equal(count(f, 'revoke'), 0); assert.deepEqual(f.raw(), session());
});
test('confirmation write failure after server acknowledgement retains old SDK credentials', async () => {
  const f = fixture({ failWrite: (key, value) => key === JOURNAL && JSON.parse(value).stage === 'revoked' });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.raw(), session());
  assert.equal(count(f, 'revoke'), 1); assert.equal(f.controller.getSnapshot().status, 'blocked');
});
test('main write failure retains receipt; explicit retry clears secured old main without another revocation', async () => {
  let fail = true; const f = fixture({ failWrite: (key) => key === STORAGE_KEY && fail }); await f.controller.initialize();
  await assert.rejects(f.write(session(OTHER, NEW))); assert.equal(f.journal().stage, 'revoked'); fail = false;
  await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(count(f, 'revoke'), 1);
  assert.equal(f.controller.getSnapshot().status, 'ready'); assert.match(f.controller.getSnapshot().error, /Sign in again/);
});
test('journal failure after main overwrite reconciles incoming session without revoking again', async () => {
  let fail = true; const f = fixture({ failWrite: (key, value) => key === JOURNAL && JSON.parse(value).stage === 'committed' && fail });
  await f.controller.initialize(); const next = session(OTHER, NEW); await assert.rejects(f.write(next)); assert.deepEqual(f.raw(), next);
  fail = false; await f.controller.retry(); assert.deepEqual(f.controller.getSnapshot().session, next); assert.equal(count(f, 'revoke'), 1);
});
test('retry unknown outcome never replays login and returns usable signed-out state', async () => {
  let lost = true; const f = fixture({ revoke: async () => { if (lost) throw new Error('lost'); return page(); } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW))); lost = false; await f.controller.retry();
  assert.equal(f.raw(), null); assert.equal(f.controller.getSnapshot().status, 'ready');
  await f.write(session(OTHER, THIRD)); assert.equal(count(f, 'revoke'), 2);
});
test('confirmed global logout authorizes removal without local revocation', async () => {
  const f = fixture({ global: async () => globalReceipt() }); await f.controller.initialize(); await f.controller.storage.removeItem(STORAGE_KEY);
  assert.equal(count(f, 'revoke'), 0); assert.equal(f.raw(), null); assert.equal(f.journal().receipt.scope, 'global');
});
test('malformed global receipt refuses removal instead of falling through', async () => {
  const f = fixture({ global: async () => ({ ...globalReceipt(), owner_id: OWNER }) }); await f.controller.initialize();
  await assert.rejects(f.controller.storage.removeItem(STORAGE_KEY)); assert.deepEqual(f.raw(), session()); assert.equal(count(f, 'revoke'), 0);
});
test('local completion rejects wrong identities, extra fields, invalid dates and incomplete pages', async () => {
  for (const receipt of [page(OTHER), page(OWNER, NEW), page(OWNER, OLD, { extra: true }), page(OWNER, OLD, { completed_at: 'invalid' }),
    page(OWNER, OLD, { next_cursor: `video:${NEW}`, cookie_cleanup_complete: false })]) {
    const f = fixture({ revoke: async () => receipt }); await f.controller.initialize();
    await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.raw(), session()); }
});
test('partial cleanup persists before continuing and resumes exact cursor on explicit retry', async () => {
  let attempt = 0; const partial = page(OWNER, OLD, { next_cursor: `archive:${NEW}`, cookie_cleanup_complete: false });
  const f = fixture({ revoke: async (_token, _backend, options) => {
    if (++attempt === 1) { assert.equal(options.progress, null); await options.onProgress(partial);
      assert.deepEqual(f.journal().receipt, partial); assert.deepEqual(f.raw(), session()); throw new Error('deadline'); }
    assert.deepEqual(options.progress, partial); await options.onProgress(page()); return page();
  } }); await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  assert.equal(f.controller.getSnapshot().status, 'blocked'); await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(count(f, 'revoke'), 2);
});
test('changed receipt binding or cursor regression cannot replace retained progress', async () => {
  for (const changed of [page(OWNER, OLD, { completed_at: '2026-10-30T23:00:00Z' }),
    page(OWNER, OLD, { next_cursor: `archive:${OLD}`, cookie_cleanup_complete: false }),
    page(OWNER, OLD, { next_cursor: 'video:00000000-0000-0000-0000-000000000000', cookie_cleanup_complete: false })]) {
    const partial = page(OWNER, OLD, { next_cursor: `video:${NEW}`, cookie_cleanup_complete: false });
    const f = fixture({ revoke: async (_token, _backend, options) => { await options.onProgress(partial); await options.onProgress(changed); return changed; } });
    await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.journal().receipt, partial); }
});
test('stale auth event cannot reactivate replaced session', async () => {
  const f = fixture(); await f.controller.initialize(); const next = session(OTHER, NEW); await f.write(next);
  f.controller.authStateChanged('SIGNED_IN', session()); await tick(); assert.deepEqual(f.controller.getSnapshot().session, next);
});
test('same-session stale notification uses actual fresh stored token', async () => {
  const f = fixture(); await f.controller.initialize(); const next = session(OWNER, OLD, { seq: 3 }); await f.write(next);
  f.controller.authStateChanged('TOKEN_REFRESHED', session()); await tick(); assert.deepEqual(f.controller.getSnapshot().session, next);
});
test('auth callback is synchronous and queues storage work after returning', async () => {
  const f = fixture(); const before = f.calls.length; assert.equal(f.controller.authStateChanged('SIGNED_IN', session()), undefined);
  assert.equal(f.calls.length, before); await tick(); assert.equal(f.controller.getSnapshot().status, 'ready');
});
test('own queue serializes writers even when external lock is a no-op', async () => {
  const hold = deferred(); let first = true;
  const f = fixture({ revoke: async (token) => { if (first) { first = false; await hold.promise; return page(); }
    const p = JSON.parse(Buffer.from(token.split('.')[1], 'base64url')); return page(p.sub, p.session_id); } });
  await f.controller.initialize(); const one = f.write(session(OTHER, NEW)); const two = f.write(session(OWNER, THIRD));
  await tick(); assert.equal(count(f, 'revoke'), 1); assert.deepEqual(f.raw(), session()); hold.resolve();
  await Promise.all([one, two]); assert.equal(count(f, 'revoke'), 2); assert.equal(f.raw().user.id, OWNER);
});
test('shared external lock coordinates independent tab controllers', async () => {
  const data = new Map([[STORAGE_KEY, JSON.stringify(session())]]); let lock = Promise.resolve();
  const runExclusive = (action) => { const next = lock.then(action); lock = next.catch(() => {}); return next; };
  const one = fixture({ data, runExclusive }); const two = fixture({ data, runExclusive }); await Promise.all([one.controller.initialize(), two.controller.initialize()]);
  await Promise.all([one.write(session(OTHER, NEW)), two.write(session(OWNER, THIRD))]);
  one.controller.authStateChanged('SIGNED_IN', session(OWNER, THIRD)); await tick();
  assert.deepEqual(one.controller.getSnapshot().session, session(OWNER, THIRD));
});
test('malformed, oversized and wrong-shape raw sessions fail closed', async () => {
  for (const raw of ['not json', 'x'.repeat(1024 * 1024 + 1), JSON.stringify({ access_token: 'bad' })]) {
    const f = fixture({ data: new Map([[STORAGE_KEY, raw]]) }); await assert.rejects(f.controller.initialize());
    assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.data.get(STORAGE_KEY), raw); }
});
test('wrong issuer or mismatched session user cannot overwrite old main', async () => {
  const mismatch = session(); mismatch.user.id = OTHER;
  for (const next of [session(OWNER, NEW, { iss: 'https://other.example/auth/v1' }), mismatch]) {
    const f = fixture(); await f.controller.initialize(); await assert.rejects(f.write(next)); assert.deepEqual(f.raw(), session()); assert.equal(count(f, 'revoke'), 0); }
});
test('missing main during pending transition is not first login', async () => {
  const f = fixture({ revoke: async () => { throw new Error('lost'); } }); await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  f.data.delete(STORAGE_KEY); const restart = fixture({ data: f.data }); await assert.rejects(restart.controller.initialize());
  await assert.rejects(restart.write(session(OTHER, NEW))); assert.equal(count(restart, 'revoke'), 0);
});
test('restart never reactivates confirmed revoked outgoing session', async () => {
  const f = fixture({ failWrite: (key) => key === STORAGE_KEY }); await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  const restart = fixture({ data: f.data }); await restart.controller.initialize(); assert.equal(restart.controller.getSnapshot().status, 'blocked');
  assert.equal(restart.controller.getSnapshot().session, null); await restart.controller.retry(); assert.equal(restart.raw(), null); assert.equal(count(restart, 'revoke'), 0);
});
test('old same-session refresh in uncertain transition does not restore activation', async () => {
  const f = fixture({ revoke: async () => { throw new Error('lost'); } }); await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  const next = session(OWNER, OLD, { seq: 7 }); await f.write(next); assert.deepEqual(f.raw(), next);
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.controller.getSnapshot().session, null);
});
test('implicit removal with unavailable old credential cannot discard it', async () => {
  const f = fixture({ revoke: async () => { throw new Error('expired'); } }); await f.controller.initialize();
  await assert.rejects(f.controller.storage.removeItem(STORAGE_KEY)); assert.deepEqual(f.raw(), session()); assert.equal(f.journal().to, null);
});
test('backend drift after acknowledgement blocks write and retry', async () => {
  let current = BACKEND; const f = fixture({ getBackendUrl: () => current, revoke: async () => { current = 'https://different.usepeso.com'; return page(); } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.raw(), session()); await assert.rejects(f.controller.retry());
});
test('malformed journal cannot authorize initial activation', async () => {
  const f = fixture(); f.data.set(JOURNAL, JSON.stringify({ version: 1, receipt: globalReceipt() }));
  await assert.rejects(f.controller.initialize()); assert.equal(f.controller.getSnapshot().status, 'blocked');
});
test('superseded SDK response rejects without hiding valid incoming accepted session', async () => {
  const f = fixture(); await f.controller.initialize(); const next = session(OTHER, NEW); await f.write(next);
  await assert.rejects(f.controller.waitForSession(session())); assert.deepEqual(f.controller.getSnapshot().session, next); assert.equal(f.controller.getSnapshot().status, 'ready');
});
test('observer failures cannot undo transition and unsubscribe works', async () => {
  const f = fixture(); let seen = 0; const unsubscribe = f.controller.subscribe(() => { seen += 1; throw new Error('observer'); });
  await f.controller.initialize(); unsubscribe(); const before = seen; await f.write(session(OTHER, NEW)); assert.equal(seen, before); assert.equal(f.controller.getSnapshot().status, 'ready');
});
test('external lock rejection is sanitized without mutation', async () => {
  const f = fixture({ runExclusive: async () => { throw new Error('PRIVATE'); } });
  await assert.rejects(f.controller.initialize(), (error) => !error.message.includes('PRIVATE'));
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.deepEqual(f.raw(), session());
});
test('uncoordinated raw replacement without journal cannot activate over already accepted identity', async () => {
  const f = fixture(); await f.controller.initialize(); f.data.set(STORAGE_KEY, JSON.stringify(session(OTHER, NEW)));
  f.controller.authStateChanged('SIGNED_IN', session(OTHER, NEW)); await tick(); assert.equal(f.controller.getSnapshot().status, 'blocked');
});


test('explicit retry cancels interrupted first login durably without any outgoing credential', async () => {
  let fail = true; const f = fixture({ initial: null, failWrite: (key) => key === STORAGE_KEY && fail });
  await f.controller.initialize(); await assert.rejects(f.write(session())); fail = false;
  await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(f.data.has(JOURNAL), false);
  const restart = fixture({ data: f.data }); await restart.controller.initialize();
  assert.equal(restart.controller.getSnapshot().status, 'ready'); assert.equal(count(f, 'revoke'), 0);
});
test('unexpected loss of accepted main preserves unknown outgoing identity across retry and restart', async () => {
  const f = fixture(); await f.controller.initialize(); f.data.delete(STORAGE_KEY);
  await assert.rejects(f.controller.waitForSession(null)); assert.equal(f.journal().from, `${OWNER}:${OLD}`);
  await assert.rejects(f.controller.retry()); assert.equal(f.controller.getSnapshot().status, 'blocked');
  const restart = fixture({ data: f.data }); await assert.rejects(restart.controller.initialize());
  await assert.rejects(restart.write(session(OTHER, NEW))); assert.equal(count(restart, 'revoke'), 0);
});


test('completed cleanup cannot regress to a partial page, and partial cursor must advance', async () => {
  for (const first of [page(), page(OWNER, OLD, { next_cursor: `video:${NEW}`, cookie_cleanup_complete: false })]) {
    const f = fixture({ revoke: async (_token, _backend, options) => {
      await options.onProgress(first);
      await options.onProgress(page(OWNER, OLD, { next_cursor: `video:${NEW}`, cookie_cleanup_complete: false })); return page();
    } });
    await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
    assert.deepEqual(f.journal().receipt, first); assert.deepEqual(f.raw(), session());
  }
});

test('retained exact outgoing proofs let a stale tab accept a later compliant handoff', async () => {
  const data = new Map([[STORAGE_KEY, JSON.stringify(session())]]); let lock = Promise.resolve();
  const runExclusive = (action) => { const next = lock.then(action); lock = next.catch(() => {}); return next; };
  const writer = fixture({ data, runExclusive }); const stale = fixture({ data, runExclusive });
  await Promise.all([writer.controller.initialize(), stale.controller.initialize()]);
  await writer.write(session(OTHER, NEW)); await writer.write(session(OWNER, THIRD));
  assert.equal(writer.journal().from, `${OTHER}:${NEW}`);
  const cache = JSON.parse(data.get(COMPLETIONS));
  assert.deepEqual(cache.entries.map(({ key }) => key), [`${OWNER}:${OLD}`, `${OTHER}:${NEW}`]);
  assert.ok(!data.get(COMPLETIONS).includes('synthetic')); assert.ok(!data.get(COMPLETIONS).includes('refresh_token'));
  stale.controller.authStateChanged('SIGNED_IN', session(OWNER, THIRD)); await tick();
  assert.equal(stale.controller.getSnapshot().status, 'ready');
  assert.deepEqual(stale.controller.getSnapshot().session, session(OWNER, THIRD));
  assert.equal(count(stale, 'revoke'), 0); assert.equal(count(stale, 'stop'), 1);
});

test('unrelated valid latest journal cannot mask an unknown outgoing session', async () => {
  const f = fixture(); await f.controller.initialize();
  f.data.set(STORAGE_KEY, JSON.stringify(session(OWNER, THIRD)));
  f.data.set(JOURNAL, JSON.stringify({ version: 1, backend: BACKEND, issuer: AUTH,
    from: `${OWNER}:${NEW}`, to: `${OWNER}:${THIRD}`, revision: 9, stage: 'committed', receipt: page(OWNER, NEW) }));
  f.controller.authStateChanged('SIGNED_IN', session(OWNER, THIRD)); await tick();
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.controller.getSnapshot().session, null);
  assert.equal(f.journal().from, `${OWNER}:${OLD}`); assert.equal(f.journal().receipt, null);
  assert.equal(f.raw().access_token, session(OWNER, THIRD).access_token); assert.equal(count(f, 'revoke'), 0);
  const restart = fixture({ data: f.data }); await assert.rejects(restart.controller.initialize());
  assert.equal(restart.controller.getSnapshot().status, 'blocked');
});

test('completion cache write failure blocks main overwrite after remote acknowledgement', async () => {
  let fail = true;
  const f = fixture({ failWrite: (key) => key === COMPLETIONS && fail }); await f.controller.initialize();
  await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.raw(), session());
  assert.equal(count(f, 'revoke'), 1); assert.equal(f.data.has(COMPLETIONS), false);
  assert.equal(f.controller.getSnapshot().status, 'blocked');
  fail = false; await f.controller.retry(); assert.equal(f.raw(), null);
  assert.equal(JSON.parse(f.data.get(COMPLETIONS)).entries[0].key, `${OWNER}:${OLD}`);
});

test('strict completion cache rejects malformed project shape identities partial proofs and duplicates', async () => {
  const entry = { key: `${OWNER}:${OLD}`, receipt: page() };
  const valid = { version: 1, backend: BACKEND, issuer: AUTH, entries: [entry] };
  for (const raw of ['not json', 'x'.repeat(65537), JSON.stringify({ ...valid, backend: 'https://other.invalid' }),
    JSON.stringify({ ...valid, issuer: 'https://other.invalid/auth/v1' }), JSON.stringify({ ...valid, extra: true }),
    JSON.stringify({ ...valid, entries: [entry, entry] }), JSON.stringify({ ...valid, entries: Array(65).fill(entry) }),
    JSON.stringify({ ...valid, entries: [{ ...entry, key: `${OWNER}:00000000-0000-0000-0000-000000000000` }] }),
    JSON.stringify({ ...valid, entries: [{ ...entry, receipt: page(OTHER) }] }),
    JSON.stringify({ ...valid, entries: [{ ...entry, receipt: page(OWNER, OLD, { next_cursor: `video:${NEW}`, cookie_cleanup_complete: false }) }] })]) {
    const f = fixture(); f.data.set(COMPLETIONS, raw); await assert.rejects(f.controller.initialize());
    assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(count(f, 'revoke'), 0);
  }
});

test('restart recognizes a known retired main even if its journal is missing', async () => {
  const f = fixture(); await f.controller.initialize(); await f.write(session(OTHER, NEW));
  f.data.set(STORAGE_KEY, JSON.stringify(session())); f.data.delete(JOURNAL);
  const restart = fixture({ data: f.data }); await restart.controller.initialize();
  assert.equal(restart.controller.getSnapshot().status, 'blocked'); assert.equal(restart.journal().receipt.scope, 'local');
  assert.deepEqual(restart.raw(), session()); await restart.controller.retry();
  assert.equal(restart.raw(), null); assert.equal(restart.controller.getSnapshot().status, 'ready');
  assert.equal(count(restart, 'revoke'), 0);
});

test('bounded cache evicts oldest proofs without treating their absence as completion', async () => {
  const data = new Map([[STORAGE_KEY, JSON.stringify(session())]]);
  const writer = fixture({ data }); const stale = fixture({ data });
  await writer.controller.initialize(); await stale.controller.initialize();
  for (let index = 1; index <= 65; index += 1) {
    const id = `00000000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`;
    await writer.write(session(OWNER, id));
  }
  const cache = JSON.parse(data.get(COMPLETIONS)); assert.equal(cache.entries.length, 64);
  assert.equal(cache.entries.some(({ key }) => key === `${OWNER}:${OLD}`), false);
  assert.ok(data.get(COMPLETIONS).length <= 65536);
  const latest = writer.raw(); stale.controller.authStateChanged('SIGNED_IN', latest); await tick();
  assert.equal(stale.controller.getSnapshot().status, 'blocked'); assert.equal(stale.journal().from, `${OWNER}:${OLD}`);
});

test('stale credential-update SDK write cannot retire or hide accepted incoming session', async () => {
  const expected = `${OWNER}:${OLD}`;
  const f = fixture({ initial: session(OTHER, NEW), getAuthMutationKey: () => expected });
  await f.controller.initialize(); const before = f.controller.getSnapshot();
  await assert.rejects(f.write(session()), /Unable/);
  assert.deepEqual(f.raw(), session(OTHER, NEW)); assert.equal(count(f, 'revoke'), 0); assert.equal(count(f, 'stop'), 0);
  assert.equal(f.data.has(JOURNAL), false); assert.equal(f.controller.getSnapshot(), before);
});

test('known retired incoming session cannot retire current session even without an Auth update intent', async () => {
  const f = fixture(); await f.controller.initialize(); await f.write(session(OTHER, NEW));
  const before = f.controller.getSnapshot(); const revocations = count(f, 'revoke'); const releases = count(f, 'stop');
  await assert.rejects(f.write(session()), /Unable/);
  assert.deepEqual(f.raw(), session(OTHER, NEW)); assert.equal(count(f, 'revoke'), revocations);
  assert.equal(count(f, 'stop'), releases); assert.equal(f.controller.getSnapshot(), before);
});

test('malformed Auth mutation intent fails closed before new main or remote dispatch', async () => {
  const f = fixture({ getAuthMutationKey: () => 'not-a-session-key' }); await f.controller.initialize();
  await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.raw(), session());
  assert.equal(count(f, 'revoke'), 0); assert.equal(f.controller.getSnapshot().status, 'blocked');
});

test('known-retired pending same-session refresh retains rotation without reactivation', async () => {
  let fail = true;
  const f = fixture({ failWrite: (key, value) => key === JOURNAL && JSON.parse(value).stage === 'revoked' && fail });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  assert.equal(JSON.parse(f.data.get(COMPLETIONS)).entries[0].key, `${OWNER}:${OLD}`);
  fail = false; const rotated = session(OWNER, OLD, { seq: 99 });
  await f.write(rotated);
  assert.deepEqual(f.raw(), rotated); assert.equal(f.controller.getSnapshot().status, 'blocked');
  assert.equal(f.controller.getSnapshot().session, null); assert.equal(count(f, 'revoke'), 1);
});

test('complete retirement proof is persisted before the incoming main SDK value', async () => {
  const f = fixture(); await f.controller.initialize(); await f.write(session(OTHER, NEW));
  const remembered = f.calls.findIndex(([what, key]) => what === 'set' && key === COMPLETIONS);
  const committed = f.calls.findIndex(([what, key]) => what === 'set' && key === STORAGE_KEY);
  assert.ok(remembered >= 0 && remembered < committed);
});

test('oversized parseable receipt dates cannot produce an unreadable retirement cache', async () => {
  const longDate = '2026-10-30T22:00:00.' + '1'.repeat(1000) + 'Z';
  assert.ok(Number.isFinite(Date.parse(longDate)));
  const f = fixture({ revoke: async () => page(OWNER, OLD, { completed_at: longDate }) });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  assert.deepEqual(f.raw(), session()); assert.equal(f.data.has(COMPLETIONS), false);
});

test('late global logout removal cannot revoke or hide an already accepted replacement session', async () => {
  let intent;
  const f = fixture({ getLogoutIntentKey: () => intent }); await f.controller.initialize();
  await f.write(session(OTHER, NEW)); const before = f.controller.getSnapshot();
  const revocations = count(f, 'revoke'); const releases = count(f, 'stop');
  intent = `${OWNER}:${OLD}`;
  await assert.rejects(f.controller.storage.removeItem(STORAGE_KEY), /Unable/);
  assert.deepEqual(f.raw(), session(OTHER, NEW)); assert.equal(f.controller.getSnapshot(), before);
  assert.equal(count(f, 'revoke'), revocations); assert.equal(count(f, 'stop'), releases);
});

test('an anonymous logout intent cannot remove a session accepted while logout was queued', async () => {
  const f = fixture({ initial: session(OTHER, NEW), getLogoutIntentKey: () => null });
  await f.controller.initialize(); const before = f.controller.getSnapshot();
  await assert.rejects(f.controller.storage.removeItem(STORAGE_KEY), /Unable/);
  assert.deepEqual(f.raw(), session(OTHER, NEW)); assert.equal(f.controller.getSnapshot(), before);
  assert.equal(count(f, 'revoke'), 0); assert.equal(count(f, 'stop'), 0); assert.equal(f.data.has(JOURNAL), false);
});

test('matching global logout intent permits only its actual old-session removal using acknowledged proof', async () => {
  const f = fixture({ getLogoutIntentKey: () => `${OWNER}:${OLD}`, global: async () => globalReceipt() });
  await f.controller.initialize(); await f.controller.storage.removeItem(STORAGE_KEY);
  assert.equal(f.raw(), null); assert.equal(f.controller.getSnapshot().status, 'ready');
  assert.equal(f.controller.getSnapshot().session, null); assert.equal(count(f, 'revoke'), 0);
  assert.equal(f.journal().from, `${OWNER}:${OLD}`); assert.equal(f.journal().receipt.scope, 'global');
});

test('malformed logout intent cannot authorize a main-session removal', async () => {
  const f = fixture({ getLogoutIntentKey: () => 'not-a-session-key' }); await f.controller.initialize();
  await assert.rejects(f.controller.storage.removeItem(STORAGE_KEY), /Unable/);
  assert.deepEqual(f.raw(), session()); assert.equal(count(f, 'revoke'), 0); assert.equal(f.controller.getSnapshot().status, 'blocked');
});

test('enabled controller requires incoming validation while disabled storage remains a passthrough', async () => {
  assert.throws(() => fixture({ missingValidation: true }), /Unable/);
  const f = fixture({ enabled: false, missingValidation: true });
  f.controller.authStateChanged('INITIAL_SESSION', session()); await f.controller.initialize();
  assert.deepEqual(f.controller.getSnapshot().session, session()); assert.equal(count(f, 'validate'), 0);
});

test('recovered main is not activated before its bound incoming validation finishes', async () => {
  const hold = deferred();
  const f = fixture({ validate: async (token, backend) => {
    assert.equal(token, session().access_token); assert.equal(backend, BACKEND);
    await hold.promise; return { owner_id: OWNER, session_id: OLD, accepted: true };
  } });
  const initialize = f.controller.initialize(); await tick();
  assert.equal(f.controller.getSnapshot().session, null); assert.equal(f.controller.getSnapshot().status, 'pending');
  assert.equal(f.calls.some(([kind, value]) => kind === 'active' && value !== null), false);
  hold.resolve(); await initialize; assert.deepEqual(f.controller.getSnapshot().session, session());
});

test('new incoming validation follows old retirement but precedes main persistence and activation', async () => {
  const hold = deferred(); let f;
  f = fixture({ validate: async (token) => {
    const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
    if (claims.session_id === NEW) {
      assert.equal(f.journal().stage, 'revoked'); assert.deepEqual(f.raw(), session());
      assert.equal(JSON.parse(f.data.get(COMPLETIONS)).entries[0].key, `${OWNER}:${OLD}`);
      await hold.promise;
    }
    return { owner_id: claims.sub, session_id: claims.session_id, accepted: true };
  } });
  await f.controller.initialize(); const operation = f.write(session(OTHER, NEW)); await tick();
  assert.equal(f.controller.getSnapshot().status, 'pending'); assert.deepEqual(f.raw(), session());
  assert.equal(f.calls.some(([kind, value]) => kind === 'active' && value === `${OTHER}:${NEW}`), false);
  hold.resolve(); await operation; assert.deepEqual(f.raw(), session(OTHER, NEW));
  assert.equal(f.controller.getSnapshot().status, 'ready'); assert.equal(count(f, 'revoke'), 1);
});

test('same-owner incoming token invalidated by provider cannot persist after global outgoing acknowledgement', async () => {
  const f = fixture({ global: async () => globalReceipt(), validate: async (token) => {
    const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
    return { owner_id: claims.sub, session_id: claims.session_id, accepted: claims.session_id === OLD };
  } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OWNER, NEW)), /Unable/);
  assert.deepEqual(f.raw(), session()); assert.equal(count(f, 'revoke'), 0);
  assert.equal(f.journal().receipt.scope, 'global'); assert.equal(f.journal().stage, 'revoked');
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.controller.getSnapshot().session, null);
  await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(f.controller.getSnapshot().status, 'ready');
});

test('false malformed wrong-owner and failed incoming validation keep old main and retirement proof', async () => {
  const invalid = [null, false, {}, { owner_id: OTHER, session_id: NEW, accepted: false },
    { owner_id: OWNER, session_id: NEW, accepted: true }, { owner_id: OTHER, session_id: OLD, accepted: true },
    { owner_id: [OTHER], session_id: NEW, accepted: true }, { owner_id: OTHER, session_id: [NEW], accepted: true },
    { owner_id: OTHER, session_id: NEW, accepted: true, extra: true }, 'throw'];
  for (const bad of invalid) {
    const f = fixture({ validate: async (token) => {
      const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
      if (claims.session_id === OLD) return { owner_id: OWNER, session_id: OLD, accepted: true };
      if (bad === 'throw') throw new Error('synthetic private provider-token response');
      return bad;
    } });
    await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)),
      (error) => error.message.startsWith('Unable') && !error.message.includes('synthetic') && !error.cause);
    assert.deepEqual(f.raw(), session()); assert.equal(f.journal().receipt.scope, 'local');
    assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(count(f, 'revoke'), 1);
  }
});

test('confirmed retirement journal and cache cannot substitute for incoming liveness on restart', async () => {
  const f = fixture(); await f.controller.initialize(); await f.write(session(OTHER, NEW));
  const restart = fixture({ data: f.data, validate: async () => ({ owner_id: OTHER, session_id: NEW, accepted: false }) });
  await assert.rejects(restart.controller.initialize(), /Unable/);
  assert.equal(restart.controller.getSnapshot().session, null); assert.equal(restart.controller.getSnapshot().status, 'blocked');
  assert.deepEqual(restart.raw(), session(OTHER, NEW)); assert.equal(count(restart, 'revoke'), 0);
});

test('post-main journal failure requires fresh incoming validation before retry can activate', async () => {
  let failJournal = true; let incomingLive = true;
  const f = fixture({ failWrite: (key, value) => key === JOURNAL && JSON.parse(value).stage === 'committed' && failJournal,
    validate: async (token) => {
      const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
      return { owner_id: claims.sub, session_id: claims.session_id, accepted: claims.session_id === OLD || incomingLive };
    } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW))); assert.deepEqual(f.raw(), session(OTHER, NEW));
  failJournal = false; incomingLive = false; await assert.rejects(f.controller.retry());
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.controller.getSnapshot().session, null);
  incomingLive = true; await f.controller.retry(); assert.equal(f.controller.getSnapshot().status, 'ready');
  assert.deepEqual(f.controller.getSnapshot().session, session(OTHER, NEW)); assert.equal(count(f, 'revoke'), 1);
});

test('same-provider refresh and focus preserve acceptance without repeated incoming probes', async () => {
  const f = fixture(); await f.controller.initialize(); assert.equal(count(f, 'validate'), 1);
  const refreshed = session(OWNER, OLD, { seq: 2 }); await f.write(refreshed);
  f.controller.authStateChanged('TOKEN_REFRESHED', refreshed); await tick();
  assert.equal(count(f, 'validate'), 1); assert.equal(count(f, 'revoke'), 0); assert.equal(count(f, 'stop'), 0);
});

test('same-key SDK refresh before initial acceptance still validates incoming identity', async () => {
  const f = fixture({ validate: async () => ({ owner_id: OWNER, session_id: OLD, accepted: false }) });
  await assert.rejects(f.write(session(OWNER, OLD, { seq: 2 })), /Unable/);
  assert.equal(count(f, 'validate'), 1); assert.deepEqual(f.raw(), session(OWNER, OLD, { seq: 2 }));
  assert.equal(f.controller.getSnapshot().status, 'blocked');
});

test('uncoordinated main drift during incoming validation cannot overwrite or activate a stale response', async () => {
  let f;
  f = fixture({ validate: async (token) => {
    const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
    if (claims.session_id === NEW) f.data.set(STORAGE_KEY, JSON.stringify(session(OWNER, THIRD)));
    return { owner_id: claims.sub, session_id: claims.session_id, accepted: true };
  } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  assert.deepEqual(f.raw(), session(OWNER, THIRD)); assert.equal(f.controller.getSnapshot().status, 'blocked');
  assert.equal(f.controller.getSnapshot().session, null); assert.equal(count(f, 'revoke'), 1);
});

test('startup same-session rotation retains fresh credentials during app outage and retry accepts without Auth replay', async () => {
  let unavailable = true;
  const rotated = { ...session(OWNER, OLD, { seq: 2 }), refresh_token: 'synthetic-rotated-refresh' };
  const f = fixture({ validate: async (token) => {
    assert.equal(token, rotated.access_token);
    if (unavailable) throw new Error('synthetic app-acceptance outage');
    return { owner_id: OWNER, session_id: OLD, accepted: true };
  } });
  await assert.rejects(f.write(rotated), /Unable/);
  assert.deepEqual(f.raw(), rotated); assert.equal(f.controller.getSnapshot().status, 'blocked');
  assert.equal(f.controller.getSnapshot().session, null); assert.equal(count(f, 'revoke'), 0);
  assert.equal(f.data.has(JOURNAL), false); assert.equal(f.data.has(COMPLETIONS), false);
  unavailable = false; await f.controller.retry();
  assert.deepEqual(f.raw(), rotated); assert.deepEqual(f.controller.getSnapshot().session, rotated);
  assert.equal(f.controller.getSnapshot().status, 'ready'); assert.equal(count(f, 'validate'), 2);
  assert.equal(count(f, 'revoke'), 0);
});

test('partial cookie progress keeps same-key rotated credentials blocked and uses them for remaining pages', async () => {
  let first = true;
  const rotated = { ...session(OWNER, OLD, { seq: 3 }), refresh_token: 'synthetic-partial-rotated-refresh' };
  const partial = page(OWNER, OLD, { next_cursor: `video:${NEW}`, cookie_cleanup_complete: false });
  const f = fixture({ revoke: async (token, _backend, options) => {
    if (first) { first = false; await options.onProgress(partial); throw new Error('synthetic cleanup deadline'); }
    assert.equal(token, rotated.access_token); assert.deepEqual(options.progress, partial); return page();
  } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  const validations = count(f, 'validate'); const revocations = count(f, 'revoke');
  await f.write(rotated); assert.deepEqual(f.raw(), rotated); assert.deepEqual(f.journal().receipt, partial);
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.controller.getSnapshot().session, null);
  assert.equal(count(f, 'revoke'), revocations); assert.equal(count(f, 'validate'), validations);
  assert.equal(f.calls.at(-1)[0], 'active'); assert.equal(f.calls.at(-1)[1], null);
  await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(f.controller.getSnapshot().status, 'ready');
  assert.equal(count(f, 'revoke'), revocations + 1);
});

test('final pending retirement keeps rotation without activation and retry removes it without another RPC', async () => {
  let failIncoming = true;
  const rotated = { ...session(OWNER, OLD, { seq: 4 }), refresh_token: 'synthetic-final-rotated-refresh' };
  const f = fixture({ validate: async (token) => {
    const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
    return { owner_id: claims.sub, session_id: claims.session_id, accepted: claims.session_id === OLD || !failIncoming };
  } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  assert.equal(f.journal().stage, 'revoked'); assert.equal(f.journal().receipt.cookie_cleanup_complete, true);
  const validations = count(f, 'validate'); const revocations = count(f, 'revoke');
  await f.write(rotated); assert.deepEqual(f.raw(), rotated); assert.equal(f.controller.getSnapshot().session, null);
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(count(f, 'revoke'), revocations);
  assert.equal(count(f, 'validate'), validations);
  failIncoming = false; await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(count(f, 'revoke'), revocations);
  assert.equal(f.controller.getSnapshot().status, 'ready'); assert.equal(f.controller.getSnapshot().session, null);
});

test('transition identity selects pending outgoing journal before a different raw SDK session', async () => {
  const data = new Map([[STORAGE_KEY, JSON.stringify(session(OTHER, NEW))],
    [JOURNAL, JSON.stringify({ version: 1, backend: BACKEND, issuer: AUTH,
      from: `${OWNER}:${OLD}`, to: `${OTHER}:${NEW}`, revision: 9, stage: 'pending', receipt: null })]]);
  const f = fixture({ data });
  assert.equal(await f.controller.getTransitionSessionKey(), `${OWNER}:${OLD}`);
  assert.equal(count(f, 'validate'), 0); assert.equal(count(f, 'revoke'), 0);
  assert.deepEqual(f.raw(), session(OTHER, NEW)); assert.equal(f.controller.getSnapshot().status, 'initializing');
});

test('transition identity reads actual main when no transition is pending and releases its lock before returning', async () => {
  let locked = false;
  const f = fixture({ runExclusive: async (action) => {
    assert.equal(locked, false); locked = true;
    try { return await action(); } finally { locked = false; }
  } });
  assert.equal(await f.controller.getTransitionSessionKey(), `${OWNER}:${OLD}`); assert.equal(locked, false);
  assert.equal(count(f, 'validate'), 0); assert.equal(count(f, 'revoke'), 0);
  await f.controller.initialize(); await f.write(session(OTHER, NEW));
  assert.equal(await f.controller.getTransitionSessionKey(), `${OTHER}:${NEW}`); assert.equal(locked, false);
});

test('disabled transition identity is null without storage locks or validation', async () => {
  const f = fixture({ enabled: false }); assert.equal(await f.controller.getTransitionSessionKey(), null);
  assert.deepEqual(f.calls, []);
});

test('avatar cookie cursor is retained across local transition failure and resumes before adopting another session', async () => {
  const progress = page(OWNER, OLD, { next_cursor: `avatar:${NEW}`, cookie_cleanup_complete: false });
  let first = true;
  const f = fixture({ revoke: async (_token, _backend, options) => {
    if (first) { first = false; await options.onProgress(progress); throw new Error('synthetic lost avatar page'); }
    assert.deepEqual(options.progress, progress); return page();
  } });
  await f.controller.initialize(); await assert.rejects(f.write(session(OTHER, NEW)));
  assert.deepEqual(f.journal().receipt, progress); assert.equal(f.controller.getSnapshot().session, null);
  await f.controller.retry(); assert.equal(f.raw(), null); assert.equal(f.controller.getSnapshot().status, 'ready');
  assert.equal(count(f, 'revoke'), 2);
});

test('stale cross-tab refresh and recovery hints release the old identity before accepting committed main', async () => {
  for (const event of ['TOKEN_REFRESHED', 'PASSWORD_RECOVERY']) {
    const data = new Map([[STORAGE_KEY, JSON.stringify(session())]]);
    const hold = deferred(); let pause = false;
    const old = fixture({ data, validate: async (token) => {
      const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
      if (pause) await hold.promise;
      return { owner_id: claims.sub, session_id: claims.session_id, accepted: true };
    } });
    const other = fixture({ data });
    await Promise.all([old.controller.initialize(), other.controller.initialize()]);
    const next = session(OTHER, NEW); await other.write(next); pause = true;
    old.controller.authStateChanged(event, session()); await tick();
    assert.equal(old.controller.getSnapshot().status, 'pending');
    assert.equal(old.controller.getSnapshot().session, null);
    assert.equal(count(old, 'stop'), 1); assert.deepEqual(old.calls.at(-2), ['stop']);
    assert.equal(old.calls.filter(([name]) => name === 'active').at(-1)[1], null);
    hold.resolve(); await tick();
    assert.deepEqual(old.controller.getSnapshot().session, next);
    assert.equal(old.controller.getSnapshot().status, 'ready');
    assert.equal(old.controller.getSnapshot().event, 'INITIAL_SESSION');
    assert.equal(count(old, 'revoke'), 0); assert.equal(count(old, 'validate'), 2);
    assert.deepEqual(old.calls.filter(([name]) => name === 'active').at(-1), ['active', `${OTHER}:${NEW}`]);
    await assert.rejects(old.controller.waitForSession(session()), /Unable/);
    assert.deepEqual(old.controller.getSnapshot().session, next);
  }
});

test('a stale recovery hint leaves the already accepted current identity and recovery event unchanged', async () => {
  const f = fixture(); await f.controller.initialize(); const next = session(OTHER, NEW); await f.write(next);
  f.controller.authStateChanged('PASSWORD_RECOVERY', next); await tick();
  const before = f.controller.getSnapshot();
  f.controller.authStateChanged('PASSWORD_RECOVERY', session()); await tick();
  assert.equal(f.controller.getSnapshot(), before); assert.equal(before.event, 'PASSWORD_RECOVERY');
  assert.equal(count(f, 'stop'), 1); assert.equal(count(f, 'validate'), 2);
});

test('a stale cross-tab callback observes committed signout and releases the old media', async () => {
  const data = new Map([[STORAGE_KEY, JSON.stringify(session())]]);
  const old = fixture({ data }); const other = fixture({ data });
  await Promise.all([old.controller.initialize(), other.controller.initialize()]);
  await other.controller.storage.removeItem(STORAGE_KEY);
  old.controller.authStateChanged('TOKEN_REFRESHED', session()); await tick();
  assert.equal(old.controller.getSnapshot().status, 'ready');
  assert.equal(old.controller.getSnapshot().session, null); assert.equal(old.controller.getSnapshot().event, 'SIGNED_OUT');
  assert.equal(count(old, 'stop'), 1); assert.equal(count(old, 'revoke'), 0);
  assert.equal(old.calls.filter(([name]) => name === 'active').at(-1)[1], null);
});

test('browser v1 completed local journal upgrades inventory before replacement and retains the app receipt time', async () => {
  const first = session(); const data = new Map([[STORAGE_KEY, JSON.stringify(first)], [JOURNAL, JSON.stringify({
    version: 1, backend: BACKEND, issuer: AUTH, from: OWNER + ':' + OLD, to: OWNER + ':' + NEW,
    revision: 1, stage: 'revoked', receipt: page(),
  })]]);
  const f = fixture({ data, browserInventoryVersion: 2, revoke: async (_token, _backend, options) => {
    assert.deepEqual(options.progress, page());
    const upgraded = page(OWNER, OLD, { cookie_inventory_version: 2 });
    await options.onProgress(upgraded); return upgraded;
  } });
  await f.controller.initialize(); await f.write(session(OWNER, NEW));
  assert.equal(count(f, 'revoke'), 1); assert.equal(f.journal().receipt.cookie_inventory_version, 2);
  assert.equal(f.journal().receipt.completed_at, STAMP); assert.equal(f.raw().user.id, OWNER);
});

test('durable global intent blocks replacement refresh and local retry before first app page and before provider ACK', async () => {
  const f = fixture({ browserInventoryVersion: 2 }); await f.controller.initialize();
  const phase = deferred(); let entered;
  const started = new Promise(resolve => { entered = resolve; });
  const work = f.controller.beginGlobalLogout(session().access_token, BACKEND, async intent => {
    assert.equal(intent.mode, 'global'); assert.equal(f.journal().version, 2); assert.equal(f.journal().stage, 'pending');
    assert.equal(f.controller.getSnapshot().session, null); entered(); await phase.promise;
    return { ...globalReceipt(), cookie_inventory_version: 2 };
  });
  await started; phase.resolve(); await work;
  assert.equal(f.journal().stage, 'provider-pending');
  assert.equal(await f.controller.hasPendingGlobalIntent(session().access_token, BACKEND), true);
  for (const next of [session(OWNER, NEW), session(OTHER, NEW)]) {
    await assert.rejects(f.write(next), /Unable to complete/); assert.deepEqual(f.raw(), session());
  }
  const rotated = session(OWNER, OLD, { seq: 3 }); await f.write(rotated);
  assert.deepEqual(f.raw(), rotated); assert.equal(f.controller.getSnapshot().session, null);
  await f.controller.retry(); assert.equal(count(f, 'revoke'), 0);
  assert.equal(f.controller.getSnapshot().status, 'blocked'); assert.equal(f.journal().mode, 'global');
  await assert.rejects(f.controller.completeGlobalLogout(session().access_token, BACKEND), /Unable to complete/);
  assert.equal(f.journal().stage, 'provider-pending');
});

test('global completion requires separately confirmed provider ACK and exact inventory version before local storage removal', async () => {
  let acknowledged = null;
  const f = fixture({ browserInventoryVersion: 2, global: async () => acknowledged }); await f.controller.initialize();
  const receipt = { ...globalReceipt(), cookie_inventory_version: 2 };
  await f.controller.beginGlobalLogout(session().access_token, BACKEND, async () => receipt);
  acknowledged = globalReceipt();
  await assert.rejects(f.controller.completeGlobalLogout(session().access_token, BACKEND), /Unable to complete/);
  acknowledged = receipt; await f.controller.completeGlobalLogout(session().access_token, BACKEND);
  assert.equal(f.journal().stage, 'revoked'); assert.equal(count(f, 'revoke'), 0);
  await f.controller.storage.removeItem(STORAGE_KEY); assert.equal(f.raw(), null); assert.equal(f.journal().stage, 'committed');
});

test('reload before any global app page retains global pending identity and never falls back to local cleanup', async () => {
  const first = fixture({ browserInventoryVersion: 2 }); await first.controller.initialize();
  await assert.rejects(first.controller.beginGlobalLogout(session().access_token, BACKEND, async () => {
    throw new Error('synthetic lost first app page');
  }), /Unable to complete/);
  assert.equal(first.journal().mode, 'global'); assert.equal(first.journal().receipt, null);
  const second = fixture({ data: first.data, browserInventoryVersion: 2 }); await second.controller.initialize();
  assert.equal(second.controller.getSnapshot().status, 'blocked');
  assert.equal(await second.controller.hasPendingGlobalIntent(session().access_token, BACKEND), true);
  await second.controller.retry(); assert.equal(count(second, 'revoke'), 0);
  await assert.rejects(second.write(session(OTHER, NEW)), /Unable to complete/);
  const rotated = session(OWNER, OLD, { seq: 9 }); await second.write(rotated);
  assert.deepEqual(second.raw(), rotated); assert.equal(second.controller.getSnapshot().session, null);
});


test('old global completion or journal becomes explicit pending global inventory upgrade without local revocation', async () => {
  for (const location of ['completion', 'journal']) {
    const data = new Map([[STORAGE_KEY, JSON.stringify(session())]]);
    const key = OWNER + ':' + OLD;
    if (location === 'completion') data.set(COMPLETIONS, JSON.stringify({ version: 1, backend: BACKEND, issuer: AUTH,
      entries: [{ key, receipt: globalReceipt() }] }));
    else data.set(JOURNAL, JSON.stringify({ version: 1, backend: BACKEND, issuer: AUTH, from: key, to: null,
      revision: 1, stage: 'revoked', receipt: globalReceipt() }));
    let confirmed = null;
    const f = fixture({ data, browserInventoryVersion: 2, global: async () => confirmed });
    await f.controller.initialize(); assert.equal(f.controller.getSnapshot().status, 'blocked');
    assert.equal(f.journal().version, 2); assert.equal(f.journal().mode, 'global'); assert.equal(f.journal().stage, 'pending');
    assert.deepEqual(f.journal().receipt, globalReceipt());
    await f.controller.retry(); assert.equal(count(f, 'revoke'), 0);
    const upgraded = { ...globalReceipt(), cookie_inventory_version: 2 };
    await f.controller.beginGlobalLogout(session().access_token, BACKEND, async intent => {
      assert.equal(intent.inventory_version, 2); return upgraded;
    });
    confirmed = upgraded; await f.controller.completeGlobalLogout(session().access_token, BACKEND);
    assert.equal(f.journal().stage, 'revoked'); assert.equal(f.journal().receipt.completed_at, STAMP);
    await f.controller.storage.removeItem(STORAGE_KEY); assert.equal(f.raw(), null); assert.equal(count(f, 'revoke'), 0);
  }
});
