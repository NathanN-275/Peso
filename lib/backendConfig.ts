import Constants from 'expo-constants';
import { Platform } from 'react-native';

export type BackendTarget =
  | 'auto'
  | 'physical-device'
  | 'ios-simulator'
  | 'android-emulator';

const DEFAULT_BACKEND_PORT = '8000';

export type BackendUrlSource =
  | 'env override'
  | 'web local default'
  | 'expo-go lan auto'
  | 'expo-go lan fallback localhost'
  | 'web default localhost'
  | 'ios simulator default'
  | 'android emulator default'
  | 'native default localhost'
  | 'missing production env';

export type BackendApiConfig = {
  url: string;
  source: BackendUrlSource;
};

let loggedLanFallbackWarning = false;

function normalizeBackendApiUrl(value?: string | null) {
  return value?.trim().replace(/\/+$/, '') ?? '';
}

function getBackendPort() {
  return process.env.EXPO_PUBLIC_BACKEND_PORT || DEFAULT_BACKEND_PORT;
}

function buildLocalUrl(hostname: string) {
  return `http://${hostname}:${getBackendPort()}`;
}

function getWebBackendHost() {
  return process.env.EXPO_PUBLIC_WEB_BACKEND_HOST || 'localhost';
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

function getHostnameFromDevServerUri(value?: string | null) {
  const trimmedValue = value?.trim();

  if (!trimmedValue) {
    return null;
  }

  try {
    const url = new URL(trimmedValue.includes('://') ? trimmedValue : `http://${trimmedValue}`);
    return url.hostname || null;
  } catch {
    return null;
  }
}

function isPrivateLanHostname(hostname: string) {
  return (
    /^10\.\d+\.\d+\.\d+$/.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[01])\.\d+\.\d+$/.test(hostname) ||
    /^192\.168\.\d+\.\d+$/.test(hostname)
  );
}

function getExpoDevServerLanHostname() {
  const manifest2 = Constants.manifest2 as
    | { extra?: { expoGo?: { debuggerHost?: string | null } } }
    | null;
  const hostname =
    getHostnameFromDevServerUri(Constants.expoConfig?.hostUri) ??
    getHostnameFromDevServerUri(manifest2?.extra?.expoGo?.debuggerHost);

  return hostname && isPrivateLanHostname(hostname) ? hostname : null;
}

function resolveExpoGoLanBackendConfig(): BackendApiConfig {
  const lanHostname = getExpoDevServerLanHostname();

  if (lanHostname) {
    return {
      url: buildLocalUrl(lanHostname),
      source: 'expo-go lan auto',
    };
  }

  if (__DEV__ && !loggedLanFallbackWarning) {
    loggedLanFallbackWarning = true;
    console.warn(
      '[BackendConfig] Unable to determine Expo dev server LAN IP. Falling back to localhost; physical devices may not reach the backend.'
    );
  }

  return {
    url: buildLocalUrl('localhost'),
    source: 'expo-go lan fallback localhost',
  };
}

function isIosSimulatorTarget(target: BackendTarget) {
  if (Platform.OS !== 'ios') {
    return false;
  }

  if (target === 'ios-simulator') {
    return true;
  }

  if (target === 'physical-device') {
    return false;
  }

  const platform = Constants.platform?.ios?.platform?.toLowerCase();
  return platform === 'i386' || platform === 'x86_64' || platform === 'arm64';
}

function isAndroidEmulatorTarget(target: BackendTarget) {
  if (Platform.OS !== 'android') {
    return false;
  }

  if (target === 'android-emulator') {
    return true;
  }

  if (target === 'physical-device') {
    return false;
  }

  const constants = Platform.constants;
  const fingerprint = constants.Fingerprint?.toLowerCase() ?? '';
  const model = constants.Model?.toLowerCase() ?? '';
  const brand = constants.Brand?.toLowerCase() ?? '';
  const manufacturer = constants.Manufacturer?.toLowerCase() ?? '';
  const emulatorSignal = `${fingerprint} ${model} ${brand} ${manufacturer}`;

  return /(emulator|simulator|generic|sdk_gphone|google_sdk|ranchu|goldfish)/.test(emulatorSignal);
}

function shouldUseLanAutoForLoopback(target: BackendTarget) {
  return (
    Platform.OS !== 'web' &&
    !isIosSimulatorTarget(target) &&
    !isAndroidEmulatorTarget(target)
  );
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
      url: buildLocalUrl(getWebBackendHost()),
      source: 'web local default',
    };
  }

  if (explicitUrl && !isLoopbackBackendUrl(explicitUrl)) {
    return {
      url: explicitUrl,
      source: 'env override',
    };
  }

  if (explicitUrl && isLoopbackBackendUrl(explicitUrl)) {
    if (Platform.OS === 'web' || isIosSimulatorTarget(target)) {
      return {
        url: explicitUrl,
        source: 'env override',
      };
    }

    if (isAndroidEmulatorTarget(target)) {
      return {
        url: buildLocalUrl('10.0.2.2'),
        source: 'android emulator default',
      };
    }

    if (shouldUseLanAutoForLoopback(target)) {
      return resolveExpoGoLanBackendConfig();
    }
  }

  if (target === 'physical-device' && Platform.OS !== 'web') {
    return resolveExpoGoLanBackendConfig();
  }

  if (Platform.OS === 'android') {
    return {
      url: buildLocalUrl('10.0.2.2'),
      source: 'android emulator default',
    };
  }

  if (Platform.OS === 'ios') {
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
    explicitUrlIsLoopback: explicitUrl ? isLoopbackBackendUrl(explicitUrl) : false,
    expoDevServerLanHost: getExpoDevServerLanHostname(),
  };
}
