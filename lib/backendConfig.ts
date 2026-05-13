import { Platform } from 'react-native';

export type BackendTarget =
  | 'auto'
  | 'physical-device'
  | 'ios-simulator'
  | 'android-emulator';

const DEFAULT_BACKEND_PORT = '8000';

export type BackendUrlSource =
  | 'env override'
  | 'web default localhost'
  | 'ios simulator default'
  | 'android emulator default'
  | 'native default localhost'
  | 'missing production env';

export type BackendApiConfig = {
  url: string;
  source: BackendUrlSource;
};

function normalizeBackendApiUrl(value?: string | null) {
  return value?.trim().replace(/\/+$/, '') ?? '';
}

function buildLocalUrl(hostname: string) {
  const port = process.env.EXPO_PUBLIC_BACKEND_PORT || DEFAULT_BACKEND_PORT;
  return `http://${hostname}:${port}`;
}

export function getBackendTarget(): BackendTarget {
  return (process.env.EXPO_PUBLIC_BACKEND_TARGET as BackendTarget | undefined) ?? 'auto';
}

function getHostname(value: string) {
  try {
    return new URL(value).hostname;
  } catch {
    return null;
  }
}

function isLoopbackBackendUrl(value: string) {
  const hostname = getHostname(value);
  return hostname === 'localhost' || hostname === '127.0.0.1';
}

export function resolveBackendApiConfig(): BackendApiConfig {
  const explicitUrl = normalizeBackendApiUrl(process.env.EXPO_PUBLIC_BACKEND_URL);

  if (!__DEV__) {
    return {
      url: explicitUrl,
      source: explicitUrl ? 'env override' : 'missing production env',
    };
  }

  const target = getBackendTarget();

  if (Platform.OS === 'web') {
    if (explicitUrl && isLoopbackBackendUrl(explicitUrl)) {
      return {
        url: explicitUrl,
        source: 'env override',
      };
    }

    return {
      url: buildLocalUrl('localhost'),
      source: 'web default localhost',
    };
  }

  if (target === 'physical-device' && explicitUrl) {
    return {
      url: explicitUrl,
      source: 'env override',
    };
  }

  if (Platform.OS === 'android') {
    if (explicitUrl && target !== 'android-emulator') {
      return {
        url: explicitUrl,
        source: 'env override',
      };
    }

    return {
      url: buildLocalUrl('10.0.2.2'),
      source: 'android emulator default',
    };
  }

  if (Platform.OS === 'ios') {
    if (explicitUrl && target !== 'ios-simulator') {
      return {
        url: explicitUrl,
        source: 'env override',
      };
    }

    return {
      url: buildLocalUrl('localhost'),
      source: 'ios simulator default',
    };
  }

  if (explicitUrl) {
    return {
      url: explicitUrl,
      source: 'env override',
    };
  }

  return {
    url: buildLocalUrl('localhost'),
    source: 'native default localhost',
  };
}

export function getBackendApiUrl() {
  return resolveBackendApiConfig().url;
}

export function getBackendConnectionDiagnostics() {
  const resolved = resolveBackendApiConfig();
  const explicitUrl = normalizeBackendApiUrl(process.env.EXPO_PUBLIC_BACKEND_URL);

  return {
    url: resolved.url,
    source: resolved.source,
    target: getBackendTarget(),
    platform: Platform.OS,
    isDev: __DEV__,
    explicitUrl: explicitUrl || null,
  };
}
