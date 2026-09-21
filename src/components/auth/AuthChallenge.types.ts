import type { AuthChallengeAction } from '../../../lib/auth-challenge';

export type AuthChallengeProps = {
  action: AuthChallengeAction;
  resetSignal: number;
  onTokenChange: (token: string | null) => void;
  onError: (message: string | null) => void;
};
