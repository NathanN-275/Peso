const NATIVE_AUTH_SCHEME = 'pesoapp:';
const NATIVE_DESTINATIONS = new Set(['login', 'reset-password']);
const REDACTED_PARAMETER_NAMES = new Set([
  'access_token',
  'refresh_token',
  'code',
  'token',
  'token_hash',
]);

function paramsToRecord(params) {
  return Array.from(params.entries()).reduce((result, [key, value]) => {
    result[key] = value;
    return result;
  }, {});
}

function parseHashParams(hash) {
  const hashValue = hash.startsWith('#') ? hash.slice(1) : hash;
  const source = hashValue.includes('?')
    ? hashValue.slice(hashValue.indexOf('?') + 1)
    : hashValue.includes('=')
      ? hashValue
      : '';
  return new URLSearchParams(source);
}

function readAuthValue(queryParams, hashParams, name) {
  return queryParams.get(name) ?? hashParams.get(name);
}

function authLinkErrorMessage(destination, errorCode, errorDescription) {
  if (!errorCode && !errorDescription) {
    return null;
  }

  if (errorCode === 'otp_expired' || /expired|already used|invalid/i.test(errorDescription ?? '')) {
    return destination === 'reset-password'
      ? 'Reset link expired or was already used. Please request a new reset email.'
      : 'Confirmation link expired or was already used. Please request a new confirmation email.';
  }

  return destination === 'reset-password'
    ? 'Unable to open this reset link. Please request a new reset email.'
    : 'Unable to confirm this email link. Please try again.';
}

function emptyNativeRedirect() {
  return {
    trusted: false,
    destination: null,
    queryParams: {},
    hashParams: {},
    code: null,
    accessToken: null,
    refreshToken: null,
    type: null,
    hasSessionParams: false,
    isRecovery: false,
    errorMessage: null,
  };
}

function parseNativeAuthRedirect(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return emptyNativeRedirect();
  }

  const destination = parsed.hostname.toLowerCase();
  const exactPath = parsed.pathname === '' || parsed.pathname === '/';
  if (
    parsed.protocol.toLowerCase() !== NATIVE_AUTH_SCHEME ||
    !NATIVE_DESTINATIONS.has(destination) ||
    !exactPath ||
    parsed.username ||
    parsed.password ||
    parsed.port
  ) {
    return emptyNativeRedirect();
  }

  const query = new URLSearchParams(parsed.search);
  const hash = parseHashParams(parsed.hash);
  const code = readAuthValue(query, hash, 'code');
  const accessToken = readAuthValue(query, hash, 'access_token');
  const refreshToken = readAuthValue(query, hash, 'refresh_token');
  const type = readAuthValue(query, hash, 'type');
  const errorCode = readAuthValue(query, hash, 'error_code');
  const errorDescription = readAuthValue(query, hash, 'error_description');

  return {
    trusted: true,
    destination,
    queryParams: paramsToRecord(query),
    hashParams: paramsToRecord(hash),
    code,
    accessToken,
    refreshToken,
    type,
    hasSessionParams: Boolean(code || (accessToken && refreshToken)),
    isRecovery: destination === 'reset-password' && type !== 'signup',
    errorMessage: authLinkErrorMessage(destination, errorCode, errorDescription),
  };
}

function parseWebAuthRedirect(pathname, search, hash) {
  const normalizedPath = pathname.replace(/\/+$/g, '').toLowerCase();
  const destination = ['/reset', '/app/reset'].includes(normalizedPath)
    ? 'reset-password'
    : ['/login', '/app/login'].includes(normalizedPath)
      ? 'login'
      : null;
  const query = new URLSearchParams(search);
  const hashParams = parseHashParams(hash);
  const type = readAuthValue(query, hashParams, 'type');
  const errorCode = readAuthValue(query, hashParams, 'error_code');
  const errorDescription = readAuthValue(query, hashParams, 'error_description');

  return {
    destination,
    queryParams: paramsToRecord(query),
    hashParams: paramsToRecord(hashParams),
    isRecovery: destination === 'reset-password' && type !== 'signup',
    errorMessage: authLinkErrorMessage(destination, errorCode, errorDescription),
  };
}

function redactAuthParams(params) {
  return Object.fromEntries(
    Object.entries(params).map(([key, value]) => [
      key,
      REDACTED_PARAMETER_NAMES.has(key.toLowerCase()) && value ? '[redacted]' : value,
    ])
  );
}

module.exports = {
  parseNativeAuthRedirect,
  parseWebAuthRedirect,
  redactAuthParams,
};
