const { getPrivateMediaSessionKey } = require('./privateMediaLogout');

const FAILURE = 'Unable to complete the session change. Check your connection and retry.';
const REENTER = 'The previous session is secured. Sign in again to finish the session change.';
const MAX_SESSION_BYTES = 1024 * 1024;
const MAX_COMPLETIONS = 64;
const MAX_COMPLETION_BYTES = 65536;
const STALE_AUTH_WRITE = Symbol('stale auth write');
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const NIL = '00000000-0000-0000-0000-000000000000';
const SESSION_KEY = new RegExp(`^(${UUID}):(${UUID})$`);
const CURSOR = new RegExp(`^(archive|avatar|video):(${UUID})$`);
const CURSOR_V2 = new RegExp(`^(archive|avatar|video):(${UUID}):(${UUID})$`);

function createPrivateMediaSessionController({ enabled, storage, storageKey, authUrl, getBackendUrl,
  runExclusive, stopMedia, onActiveKey, revokeSession, getGlobalReceipt = async () => null,
  getAuthMutationKey = () => null, getLogoutIntentKey = () => undefined, validateIncomingSession, browserInventoryVersion = 1 }) {
  if (![1, 2].includes(browserInventoryVersion)) throw new Error(FAILURE);
  const journalKey = `${storageKey}:peso-private-media-transition:v1`;
  const completionKey = `${storageKey}:peso-private-media-completions:v1`;
  let snapshot = { session: null, event: 'INITIAL_SESSION', status: 'initializing', error: null, revision: 0 };
  let queue = Promise.resolve();
  let lastAcceptedKey = null;
  const subscribers = new Set();
  let issuer;
  if (enabled) {
    const url = new URL(authUrl);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash
        || !url.pathname.endsWith('/auth/v1') || !storageKey || typeof runExclusive !== 'function'
        || typeof validateIncomingSession !== 'function') throw new Error(FAILURE);
    issuer = url.href.replace(/\/$/, '');
  }

  function identity(session) {
    if (!session || typeof session !== 'object' || Array.isArray(session)) throw new Error(FAILURE);
    const key = getPrivateMediaSessionKey(session.access_token, issuer);
    if (!key || session.user?.id !== key.split(':')[0]) throw new Error(FAILURE);
    return key;
  }
  function parseMain(raw) {
    if (raw === null) return null;
    if (typeof raw !== 'string' || raw.length > MAX_SESSION_BYTES) throw new Error(FAILURE);
    const session = JSON.parse(raw);
    identity(session);
    return session;
  }
  function backend() {
    const url = new URL(getBackendUrl());
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) throw new Error(FAILURE);
    return url.href.replace(/\/$/, '');
  }
  const keyOf = (session) => session === null ? null : identity(session);
  async function validateIncoming(session, selectedBackend) {
    const key = identity(session);
    const response = await validateIncomingSession(session.access_token, selectedBackend);
    if (!response || typeof response !== 'object' || Array.isArray(response)
        || Object.keys(response).sort().join(',') !== 'accepted,owner_id,session_id'
        || response.accepted !== true || typeof response.owner_id !== 'string' || typeof response.session_id !== 'string'
        || `${response.owner_id}:${response.session_id}` !== key
        || backend() !== selectedBackend) throw new Error(FAILURE);
  }
  const validDate = (value) => typeof value === 'string' && value.length <= 64 && /^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(value)
    && Number.isFinite(Date.parse(value));
  function validReceipt(receipt, from, partial = false, legacy = false) {
    if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return false;
    const keys = Object.keys(receipt).sort().join(',');
    if (!validDate(receipt.completed_at) || typeof receipt.replayed !== 'boolean') return false;
    const version = Object.hasOwn(receipt, 'cookie_inventory_version') ? receipt.cookie_inventory_version : 1;
    if (![1, 2].includes(version) || (!legacy && version !== browserInventoryVersion)) return false;
    if (receipt.scope === 'global') return keys === (version === 2
      ? 'completed_at,cookie_inventory_version,replayed,scope' : 'completed_at,replayed,scope');
    const expected = ['completed_at','cookie_cleanup_complete','next_cursor','owner_id','replayed','scope','session_id',
      ...(version === 2 ? ['cookie_inventory_version'] : [])].sort().join(',');
    const match = typeof receipt.next_cursor === 'string' ? (version === 2 ? CURSOR_V2 : CURSOR).exec(receipt.next_cursor) : null;
    return receipt.scope === 'local' && keys === expected
      && receipt.owner_id === from?.split(':')[0] && receipt.session_id === from?.split(':')[1]
      && typeof receipt.cookie_cleanup_complete === 'boolean'
      && (receipt.next_cursor === null ? receipt.cookie_cleanup_complete === true
        : partial && match && match[2] !== NIL && receipt.cookie_cleanup_complete === false);
  }

  const validKey = (key) => typeof key === 'string' && SESSION_KEY.test(key)
    && SESSION_KEY.exec(key).slice(1).every((id) => id !== NIL);
  function readCompletions(raw, selectedBackend) {
    if (raw === null) return [];
    if (typeof raw !== 'string' || raw.length > MAX_COMPLETION_BYTES) throw new Error(FAILURE);
    const value = JSON.parse(raw);
    if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== 'backend,entries,issuer,version'
        || value.version !== 1 || value.backend !== selectedBackend || value.issuer !== issuer
        || !Array.isArray(value.entries) || value.entries.length > MAX_COMPLETIONS) throw new Error(FAILURE);
    const seen = new Set();
    for (const entry of value.entries) {
      if (!entry || Array.isArray(entry) || Object.keys(entry).sort().join(',') !== 'key,receipt'
          || !validKey(entry.key) || seen.has(entry.key) || !validReceipt(entry.receipt, entry.key, false, true)) throw new Error(FAILURE);
      seen.add(entry.key);
    }
    return value.entries;
  }
  async function retainedCompletions(selectedBackend) {
    return readCompletions(await storage.getItem(completionKey), selectedBackend);
  }
  async function rememberCompletion(key, receipt, selectedBackend) {
    if (!validKey(key) || !validReceipt(receipt, key)) throw new Error(FAILURE);
    const entries = await retainedCompletions(selectedBackend);
    const existing = entries.find((entry) => entry.key === key);
    if (existing && validReceipt(existing.receipt, key)) return;
    // Bounded old-session proofs preserve fast cross-tab handoffs; evicted proofs fail closed.
    const next = [...entries.filter((entry) => entry.key !== key), { key, receipt }].slice(-MAX_COMPLETIONS);
    const raw = JSON.stringify({ version: 1, backend: selectedBackend, issuer, entries: next });
    if (raw.length > MAX_COMPLETION_BYTES) throw new Error(FAILURE);
    await storage.setItem(completionKey, raw);
  }
  function readJournal(raw, selectedBackend) {
    if (raw === null) return null;
    if (typeof raw !== 'string' || raw.length > 16384) throw new Error(FAILURE);
    const value = JSON.parse(raw);
    const global = value?.version === 2 && value?.mode === 'global';
    const keys = global ? 'backend,from,inventory_version,issuer,mode,provider_receipt,receipt,revision,stage,to,version'
      : 'backend,from,issuer,receipt,revision,stage,to,version';
    if (!value || Array.isArray(value) || Object.keys(value).sort().join(',') !== keys
        || (!global && value.version !== 1) || value.backend !== selectedBackend || value.issuer !== issuer
        || (global && (value.inventory_version !== browserInventoryVersion || !validKey(value.from) || value.to !== null))
        || !Number.isSafeInteger(value.revision) || value.revision < 1
        || !(global ? ['pending', 'provider-pending', 'revoked', 'committed'] : ['pending', 'revoked', 'committed']).includes(value.stage)
        || ![value.from, value.to].every((key) => key === null || validKey(key)) || value.from === value.to
        || (value.receipt !== null && !validReceipt(value.receipt, value.from, true, true))
        || (value.from !== null && !['pending', 'provider-pending'].includes(value.stage) && !validReceipt(value.receipt, value.from, false, true))
        || (value.from === null && value.receipt !== null)
        || (global && value.receipt !== null && value.receipt.scope !== 'global')
        || (global && value.provider_receipt !== null && (!validReceipt(value.provider_receipt, value.from, false, true)
          || value.provider_receipt.scope !== 'global' || value.receipt && value.provider_receipt.completed_at !== value.receipt.completed_at))) throw new Error(FAILURE);
    return value;
  }
  function publish(session, event, status, error = null) {
    snapshot = { session, event, status, error, revision: snapshot.revision + 1 };
    if (enabled && status === 'ready') lastAcceptedKey = keyOf(session);
    onActiveKey?.(status === 'ready' && session ? (enabled ? identity(session)
      : getPrivateMediaSessionKey(session.access_token, authUrl)) : null);
    for (const fn of subscribers) {
      try { fn(snapshot); } catch { /* A consumer cannot undo a committed boundary. */ }
    }
  }
  function block(error = FAILURE) { publish(null, snapshot.event, 'blocked', error); }
  function enqueue(action) {
    const next = queue.then(action);
    queue = next.catch(() => {});
    return next;
  }
  async function exclusive(action) {
    try { return await runExclusive(action); }
    catch (error) {
      if (error === STALE_AUTH_WRITE) throw new Error(FAILURE);
      publish(null, snapshot.event, 'pending');
      try { await stopMedia(); } catch {}
      block();
      throw new Error(FAILURE);
    }
  }
  async function readState() {
    const selectedBackend = backend();
    const current = parseMain(await storage.getItem(storageKey));
    let journal = readJournal(await storage.getItem(journalKey), selectedBackend);
    const completions = await retainedCompletions(selectedBackend);
    const currentKey = keyOf(current);
    const completionFor = (key) => completions.find((entry) => entry.key === key)?.receipt;
    const legacyGlobal = journal?.from === currentKey && journal.mode !== 'global' && journal.receipt?.scope === 'global'
      ? journal.receipt : completionFor(currentKey)?.scope === 'global' ? completionFor(currentKey) : null;
    if (journal?.mode !== 'global' && currentKey !== null && browserInventoryVersion === 2 && legacyGlobal
        && validReceipt(legacyGlobal, currentKey, false, true) && !validReceipt(legacyGlobal, currentKey)
        && (!journal || journal.from === currentKey || journal.stage === 'committed')) {
      journal = { version: 2, mode: 'global', inventory_version: 2, backend: selectedBackend, issuer, from: currentKey, to: null,
        revision: Math.max(snapshot.revision + 1, (journal?.revision ?? 0) + 1), stage: 'pending', receipt: legacyGlobal, provider_receipt: legacyGlobal };
      await storeJournal(journal);
    }
    if (lastAcceptedKey !== null && lastAcceptedKey !== currentKey
        && !(journal?.from === lastAcceptedKey && validReceipt(journal.receipt, lastAcceptedKey))
        && !completionFor(lastAcceptedKey) && journal?.mode !== 'global') {
      // An unrelated latest journal cannot prove this runtime's outgoing session ended.
      await storeJournal({ version: 1, backend: selectedBackend, issuer, from: lastAcceptedKey, to: currentKey,
        revision: Math.max(snapshot.revision + 1, (journal?.revision ?? 0) + 1), stage: 'pending', receipt: null });
      throw new Error(FAILURE);
    }
    if (journal?.mode !== 'global' && currentKey !== null && completionFor(currentKey)
        && (!journal || journal.from !== currentKey || journal.stage === 'committed')) {
      journal = { version: 1, backend: selectedBackend, issuer, from: currentKey, to: null,
        revision: Math.max(snapshot.revision + 1, (journal?.revision ?? 0) + 1), stage: validReceipt(completionFor(currentKey), currentKey) ? 'revoked' : 'pending', receipt: completionFor(currentKey) };
      await storeJournal(journal);
    }
    return { selectedBackend, current, currentKey, journal, completions };
  }
  async function storeJournal(journal) { await storage.setItem(journalKey, JSON.stringify(journal)); }
  async function obtainReceipt(journal, current) {
    if (journal.mode === 'global') throw new Error(FAILURE);
    let progress = journal.receipt;
    if (validReceipt(progress, journal.from)) return progress;
    const retained = (await retainedCompletions(journal.backend)).find((entry) => entry.key === journal.from);
    if (retained && validReceipt(retained.receipt, journal.from)) return retained.receipt;
    if (progress === null && retained) progress = retained.receipt;
    if (progress?.scope === 'global') throw new Error(FAILURE);
    if (progress === null) {
      const global = await getGlobalReceipt(current.access_token, journal.backend);
      if (global !== null) {
        if (!validReceipt(global, journal.from) || global.scope !== 'global') throw new Error(FAILURE);
        return global;
      }
    }
    function checkPage(page) {
      if (!validReceipt(page, journal.from, true, true) || page.scope !== 'local'
          || (progress && (page.completed_at !== progress.completed_at
            || (((progress.cookie_inventory_version ?? 1) === (page.cookie_inventory_version ?? 1))
              && ((progress.next_cursor === null && page.next_cursor !== null)
                || (progress.next_cursor !== null && page.next_cursor !== null && page.next_cursor <= progress.next_cursor)))
            || ((page.cookie_inventory_version ?? 1) < (progress.cookie_inventory_version ?? 1))
            || ((page.cookie_inventory_version ?? 1) > (progress.cookie_inventory_version ?? 1) && !progress.cookie_cleanup_complete)))) {
        throw new Error(FAILURE);
      }
    }
    const receipt = await revokeSession(current.access_token, journal.backend, {
      progress,
      async onProgress(page) {
        checkPage(page);
        await storeJournal({ ...journal, receipt: page, stage: 'pending' });
        progress = page;
      },
    });
    checkPage(receipt);
    if (!validReceipt(receipt, journal.from)) throw new Error(FAILURE);
    return receipt;
  }
  async function suspend() {
    publish(null, snapshot.event, 'pending');
    await stopMedia();
  }
  async function reconcile(event = 'INITIAL_SESSION', hintedSession) {
    const state = await readState();
    const { current, currentKey, journal, selectedBackend } = state;
    if (journal?.mode === 'global' && !['revoked', 'committed'].includes(journal.stage)) {
      await suspend(); block(); return;
    }
    if (journal) {
      const confirmed = journal.from === null || validReceipt(journal.receipt, journal.from);
      if (currentKey === journal.to && confirmed) {
        if (journal.stage !== 'committed') await storeJournal({ ...journal, stage: 'committed' });
      } else if (currentKey === journal.from && journal.stage !== 'committed') {
        await suspend();
        block(journal.receipt ? REENTER : FAILURE);
        return;
      } else throw new Error(FAILURE);
    }
    const staleHint = hintedSession !== undefined && keyOf(hintedSession) !== currentKey;
    if (staleHint && snapshot.status === 'ready' && keyOf(snapshot.session) === currentKey) return;
    if (!journal && snapshot.session && keyOf(snapshot.session) !== currentKey) throw new Error(FAILURE);
    if (snapshot.session && keyOf(snapshot.session) !== currentKey) await suspend();
    // Another tab's committed identity wins; a stale recovery event cannot label it.
    if (staleHint) event = 'INITIAL_SESSION';
    if (current !== null && currentKey !== lastAcceptedKey) {
      if (snapshot.status !== 'pending') publish(null, event, 'pending');
      await validateIncoming(current, selectedBackend);
      if (keyOf(parseMain(await storage.getItem(storageKey))) !== currentKey) throw new Error(FAILURE);
    }
    publish(current, current ? event : 'SIGNED_OUT', 'ready');
  }
  async function mutate(value) {
    const next = value === null ? null : parseMain(value);
    const to = keyOf(next);
    let { selectedBackend, current, currentKey: from, journal, completions } = await readState();
    if (journal?.mode === 'global' && !['revoked', 'committed'].includes(journal.stage)) {
      if (value !== null && to === from && from === journal.from) {
        await storage.setItem(storageKey, value); block(); return;
      }
      throw new Error(FAILURE);
    }
    const mutationKey = getAuthMutationKey();
    const logoutKey = getLogoutIntentKey();
    if ((mutationKey !== null && !validKey(mutationKey))
        || (logoutKey !== undefined && logoutKey !== null && !validKey(logoutKey))) throw new Error(FAILURE);
    if ((value === null && logoutKey !== undefined && from !== logoutKey)
        || (mutationKey !== null && to === mutationKey && from !== mutationKey)
        || (to !== from && completions.some((entry) => entry.key === to))) {
      if (snapshot.status === 'ready' && keyOf(snapshot.session) === from
          && !completions.some((entry) => entry.key === from)) throw STALE_AUTH_WRITE;
      throw new Error(FAILURE);
    }
    if (journal && from === journal.to && (journal.from === null || validReceipt(journal.receipt, journal.from))) {
      if (journal.stage !== 'committed') {
        journal = { ...journal, stage: 'committed' };
        await storeJournal(journal);
      }
    } else if (journal && (from !== journal.from || journal.stage === 'committed')) throw new Error(FAILURE);
    if (snapshot.session && from === null) {
      if (journal && journal.to === null && (journal.from === null || validReceipt(journal.receipt, journal.from))) await suspend();
      else throw new Error(FAILURE);
    }
    if (from === to) {
      if (from === null && journal && journal.from === null) {
        await storage.removeItem(storageKey);
        await storage.removeItem(journalKey);
        publish(null, 'SIGNED_OUT', 'ready');
        return;
      }
      if (journal && journal.stage !== 'committed') {
        // Keep rotated credentials for cleanup retry; a pending transition never reactivates its old identity.
        if (value !== null) await storage.setItem(storageKey, value);
        block();
        return;
      }
      if (from !== null && completions.some((entry) => entry.key === from)) throw new Error(FAILURE);
      // Preserve rotated credentials for the same provider identity even if app acceptance is unavailable.
      if (value === null) await storage.removeItem(storageKey);
      else await storage.setItem(storageKey, value);
      if (next !== null && to !== lastAcceptedKey) {
        await validateIncoming(next, selectedBackend);
        if (keyOf(parseMain(await storage.getItem(storageKey))) !== from) throw new Error(FAILURE);
      }
      publish(next, next ? 'TOKEN_REFRESHED' : 'SIGNED_OUT', 'ready');
      return;
    }
    let receipt = journal && journal.stage !== 'committed' ? journal.receipt : null;
    journal = { version: 1, backend: selectedBackend, issuer, from, to,
      revision: Math.max(snapshot.revision + 1, (journal?.revision ?? 0) + 1), stage: 'pending', receipt };
    await storeJournal(journal);
    await suspend();
    if (from !== null) {
      receipt = await obtainReceipt(journal, current);
      await rememberCompletion(from, receipt, selectedBackend);
    }
    journal = { ...journal, receipt, stage: 'revoked' };
    await storeJournal(journal);
    if (next !== null) await validateIncoming(next, selectedBackend);
    if (backend() !== selectedBackend) throw new Error(FAILURE);
    // Never overwrite a raw value another runtime changed outside the shared lock protocol.
    if (keyOf(parseMain(await storage.getItem(storageKey))) !== from) throw new Error(FAILURE);
    if (value === null) await storage.removeItem(storageKey);
    else await storage.setItem(storageKey, value);
    await storeJournal({ ...journal, stage: 'committed' });
    publish(next, next ? 'SIGNED_IN' : 'SIGNED_OUT', 'ready');
  }
  const wrappedStorage = enabled ? {
    getItem: (key) => storage.getItem(key),
    setItem: (key, value) => key === storageKey ? enqueue(() => exclusive(() => mutate(value))) : storage.setItem(key, value),
    removeItem: (key) => key === storageKey ? enqueue(() => exclusive(() => mutate(null))) : storage.removeItem(key),
    ...(storage.isServer === undefined ? {} : { isServer: storage.isServer }),
  } : storage;
  function initialize() {
    if (!enabled) { publish(snapshot.session, snapshot.event, 'ready'); return Promise.resolve(); }
    return enqueue(() => exclusive(() => reconcile()));
  }
  function authStateChanged(event, session) {
    if (!enabled) { publish(session ?? null, event, 'ready'); return; }
    // Auth callbacks return immediately; no Auth API or callback-held lock re-entry.
    void Promise.resolve().then(() => enqueue(() => exclusive(() => reconcile(event, session ?? null)))).catch(() => {});
  }
  async function waitForSession(session) {
    if (!enabled) return session;
    const accepted = await enqueue(() => exclusive(async () => {
      await reconcile(snapshot.event, session);
      return snapshot.status === 'ready' && keyOf(session) === keyOf(snapshot.session)
        ? { session: snapshot.session } : null;
    }));
    if (!accepted) throw new Error(FAILURE);
    return accepted.session;
  }
  async function retry() {
    if (!enabled) return;
    return enqueue(() => exclusive(async () => {
      const { current, currentKey, journal, selectedBackend } = await readState();
      if (journal?.mode === 'global' && !['revoked', 'committed'].includes(journal.stage)) { await suspend(); block(); return; }
      if (!journal || journal.stage === 'committed') { await reconcile(); return; }
      if (currentKey === journal.to && (journal.from === null || validReceipt(journal.receipt, journal.from))) {
        await reconcile(); return;
      }
      if (currentKey !== journal.from) throw new Error(FAILURE);
      await suspend();
      const receipt = journal.from === null ? null : await obtainReceipt(journal, current);
      if (journal.from !== null) await rememberCompletion(journal.from, receipt, selectedBackend);
      await storeJournal({ ...journal, receipt, stage: 'revoked' });
      // An explicit retry cannot recreate a consumed login response. Clear only the secured old
      // credential, letting normal login run again instead of reactivating a revoked session.
      await mutate(null);
      if (journal.to !== null) publish(null, 'SIGNED_OUT', 'ready', REENTER);
    }));
  }
  async function beginGlobalLogout(token, expectedBackend, action) {
    if (!enabled) return action(undefined);
    return enqueue(() => exclusive(async () => {
      const { current, currentKey, journal, selectedBackend } = await readState();
      const selectedKey = getPrivateMediaSessionKey(token, issuer);
      if (!validKey(selectedKey) || currentKey !== selectedKey || selectedBackend !== expectedBackend
          || (journal && journal.stage !== 'committed' && (journal.mode !== 'global' || journal.from !== selectedKey))) throw new Error(FAILURE);
      const pending = journal?.mode === 'global' && journal.stage !== 'committed' ? journal : {
        version: 2, mode: 'global', inventory_version: browserInventoryVersion, backend: selectedBackend, issuer,
        from: selectedKey, to: null, revision: Math.max(snapshot.revision + 1, (journal?.revision ?? 0) + 1), stage: 'pending', receipt: null, provider_receipt: null,
      };
      await storeJournal(pending);
      await suspend();
      const [owner_id, session_id] = selectedKey.split(':');
      const receipt = await action({ version: 2, mode: 'global', inventory_version: browserInventoryVersion, owner_id, session_id, backend: selectedBackend }, pending.provider_receipt);
      if (!validReceipt(receipt, selectedKey) || receipt.scope !== 'global' || backend() !== selectedBackend
          || keyOf(parseMain(await storage.getItem(storageKey))) !== selectedKey) throw new Error(FAILURE);
      await storeJournal({ ...pending, receipt, stage: 'provider-pending' });
      return receipt;
    }));
  }
  async function completeGlobalLogout(token, expectedBackend) {
    if (!enabled) return;
    return enqueue(() => exclusive(async () => {
      const { currentKey, journal, selectedBackend } = await readState();
      const key = getPrivateMediaSessionKey(token, issuer);
      if (key !== currentKey || expectedBackend !== selectedBackend || journal?.mode !== 'global'
          || journal.from !== key || !['provider-pending', 'revoked'].includes(journal.stage)) throw new Error(FAILURE);
      const receipt = await getGlobalReceipt(token, selectedBackend);
      if (!validReceipt(receipt, key) || receipt.scope !== 'global' || receipt.completed_at !== journal.receipt?.completed_at) throw new Error(FAILURE);
      await rememberCompletion(key, receipt, selectedBackend);
      await storeJournal({ ...journal, receipt, provider_receipt: receipt, stage: 'revoked' });
      block(REENTER);
    }));
  }
  async function hasPendingGlobalIntent(token, expectedBackend) {
    if (!enabled) return false;
    return enqueue(() => exclusive(async () => {
      const { currentKey, journal, selectedBackend } = await readState();
      const key = getPrivateMediaSessionKey(token, issuer);
      if (!validKey(key) || expectedBackend !== selectedBackend) throw new Error(FAILURE);
      return currentKey === key && journal?.from === key && journal.mode === 'global'
        && !['revoked', 'committed'].includes(journal.stage);
    }));
  }
  async function getTransitionSessionKey() {
    if (!enabled) return null;
    return enqueue(() => exclusive(async () => {
      const { currentKey, journal } = await readState();
      return journal && journal.stage !== 'committed' ? journal.from : currentKey;
    }));
  }
  return { storage: wrappedStorage, authStateChanged, initialize, getSnapshot: () => snapshot, getTransitionSessionKey, beginGlobalLogout, completeGlobalLogout, hasPendingGlobalIntent,
    subscribe(fn) { subscribers.add(fn); return () => subscribers.delete(fn); }, waitForSession, retry };
}

module.exports = { createPrivateMediaSessionController };
