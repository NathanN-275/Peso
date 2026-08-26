const AUTH_CHALLENGE_ACTIONS = Object.freeze([
  'login',
  'signup',
  'reset_password',
]);
const AUTH_CHALLENGE_STATUSES = new Set([
  'ready',
  'verified',
  'expired',
  'error',
]);

function isAuthChallengeAction(value) {
  return AUTH_CHALLENGE_ACTIONS.includes(value);
}

function parseAuthChallengeMessage(rawMessage, expectedAction) {
  let message;

  try {
    message = JSON.parse(rawMessage);
  } catch {
    return { ok: false, error: 'invalid-json' };
  }

  if (
    !message ||
    message.version !== 1 ||
    message.type !== 'peso.turnstile' ||
    message.action !== expectedAction ||
    !AUTH_CHALLENGE_STATUSES.has(message.status)
  ) {
    return { ok: false, error: 'invalid-message' };
  }

  if (
    message.status === 'verified' &&
    (typeof message.token !== 'string' || !message.token.trim())
  ) {
    return { ok: false, error: 'invalid-token' };
  }

  if (
    message.status === 'error' &&
    (typeof message.code !== 'string' ||
      !/^[a-z0-9-]{1,64}$/.test(message.code))
  ) {
    return { ok: false, error: 'invalid-error-code' };
  }

  const event = {
    action: message.action,
    status: message.status,
  };

  if (message.status === 'verified') {
    event.token = message.token;
  } else if (message.status === 'error') {
    event.code = message.code;
  }

  return { ok: true, event };
}

function buildAuthChallengeUrl(baseUrl, action, resetSignal) {
  if (!isAuthChallengeAction(action)) {
    throw new Error('Unsupported authentication challenge action.');
  }

  const challengeUrl = new URL(baseUrl);
  challengeUrl.username = '';
  challengeUrl.password = '';
  challengeUrl.search = '';
  challengeUrl.hash = '';
  challengeUrl.searchParams.set('action', action);
  challengeUrl.searchParams.set('reset', String(resetSignal));
  return challengeUrl.toString();
}

function isExactAuthChallengeDocument(requestUrl, configuredUrl) {
  try {
    const request = new URL(requestUrl);
    const configured = new URL(configuredUrl);
    const queryNames = Array.from(request.searchParams.keys());
    const action = request.searchParams.get('action');
    const reset = request.searchParams.get('reset');
    return (
      request.protocol === configured.protocol &&
      request.host === configured.host &&
      request.pathname === configured.pathname &&
      !request.username &&
      !request.password &&
      !request.hash &&
      queryNames.length === 2 &&
      queryNames.every((name) => name === 'action' || name === 'reset') &&
      request.searchParams.getAll('action').length === 1 &&
      request.searchParams.getAll('reset').length === 1 &&
      isAuthChallengeAction(action) &&
      typeof reset === 'string' &&
      /^\d+$/.test(reset)
    );
  } catch {
    return false;
  }
}

function isTrustedAuthChallengeNavigation(requestUrl, configuredUrl) {
  if (requestUrl === 'about:blank' || requestUrl === 'about:srcdoc') {
    return true;
  }

  return isExactAuthChallengeDocument(requestUrl, configuredUrl);
}

function isTrustedAuthChallengeMessageSource(requestUrl, configuredUrl) {
  return isExactAuthChallengeDocument(requestUrl, configuredUrl);
}

module.exports = {
  AUTH_CHALLENGE_ACTIONS,
  buildAuthChallengeUrl,
  isTrustedAuthChallengeMessageSource,
  isTrustedAuthChallengeNavigation,
  parseAuthChallengeMessage,
};
