export type NativeAuthRedirect = {
  trusted: boolean;
  destination: 'login' | 'reset-password' | null;
  queryParams: Record<string, string>;
  hashParams: Record<string, string>;
  code: string | null;
  accessToken: string | null;
  refreshToken: string | null;
  type: string | null;
  hasSessionParams: boolean;
  isRecovery: boolean;
  errorMessage: string | null;
};

export type WebAuthRedirect = {
  destination: 'login' | 'reset-password' | null;
  queryParams: Record<string, string>;
  hashParams: Record<string, string>;
  isRecovery: boolean;
  errorMessage: string | null;
};

export function parseNativeAuthRedirect(url: string): NativeAuthRedirect;
export function parseWebAuthRedirect(
  pathname: string,
  search: string,
  hash: string
): WebAuthRedirect;
export function redactAuthParams(params: Record<string, string>): Record<string, string>;
