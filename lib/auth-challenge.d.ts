export type AuthChallengeAction = 'login' | 'signup' | 'reset_password';

export type AuthChallengeEvent =
  | { action: AuthChallengeAction; status: 'ready' }
  | { action: AuthChallengeAction; status: 'verified'; token: string }
  | { action: AuthChallengeAction; status: 'expired' }
  | { action: AuthChallengeAction; status: 'error'; code: string };

export type AuthChallengeParseResult =
  | { ok: true; event: AuthChallengeEvent }
  | { ok: false; error: string };

export const AUTH_CHALLENGE_ACTIONS: readonly AuthChallengeAction[];

export function buildAuthChallengeUrl(
  baseUrl: string,
  action: AuthChallengeAction,
  resetSignal: number
): string;

export function isTrustedAuthChallengeNavigation(
  requestUrl: string,
  configuredUrl: string
): boolean;
export function isTrustedAuthChallengeMessageSource(
  requestUrl: string,
  configuredUrl: string
): boolean;

export function parseAuthChallengeMessage(
  rawMessage: string,
  expectedAction: AuthChallengeAction
): AuthChallengeParseResult;
