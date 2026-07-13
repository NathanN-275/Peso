function getUrl(value) {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

function isPrivateIpv4(hostname) {
  const parts = hostname.split('.').map((part) => Number.parseInt(part, 10));

  if (parts.length !== 4 || parts.some((part) => Number.isNaN(part) || part < 0 || part > 255)) {
    return false;
  }

  const [first, second] = parts;
  return (
    first === 10 ||
    first === 127 ||
    first === 0 ||
    first === 169 && second === 254 ||
    first === 172 && second >= 16 && second <= 31 ||
    first === 192 && second === 168
  );
}

function isLocalOrPrivateHostname(hostname) {
  const normalizedHostname = hostname.trim().toLowerCase().replace(/^\[(.*)\]$/, '$1');

  return (
    normalizedHostname === 'localhost' ||
    normalizedHostname === '::1' ||
    normalizedHostname.endsWith('.localhost') ||
    normalizedHostname.endsWith('.local') ||
    isPrivateIpv4(normalizedHostname)
  );
}

function getProductionBackendUrlError(value) {
  const trimmedValue = typeof value === 'string' ? value.trim() : '';

  if (!trimmedValue) {
    return 'Missing production backend URL.';
  }

  const url = getUrl(trimmedValue);

  if (!url) {
    return 'Production backend URL must be an absolute HTTPS URL.';
  }

  if (url.protocol !== 'https:') {
    return 'Production backend URL must use HTTPS.';
  }

  if (isLocalOrPrivateHostname(url.hostname)) {
    return 'Production backend URL must not point at localhost or a private-network host.';
  }

  return null;
}

module.exports = {
  getProductionBackendUrlError,
  isLocalOrPrivateHostname,
};
