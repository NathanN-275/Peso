import { ReactNode, createContext, useContext, useEffect, useRef, useState } from 'react';
import { Session, User } from '@supabase/supabase-js';
import { AppState, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { supabase, supabaseConfigError, supabaseAuthUrl, signOutWithPrivateMedia,
  getAcceptedAuthSnapshot, subscribeAcceptedAuthSession, initializeAcceptedAuthSession,
  waitForAcceptedAuthSession, retryAuthSessionTransition, updateUserWithPrivateMedia } from '../lib/supabase';
import { getPrivateMediaSessionKey } from '../lib/privateMediaLogout';
import { ensureOwnProfile } from '../lib/profile';

type AuthContextValue = {
  session: Session | null;
  mediaSessionKey: string | null;
  user: User | null;
  initializing: boolean;
  configError: string | null;
  passwordRecoveryMode: boolean;
  signInWithEmail: (email: string, password: string, captchaToken: string) => Promise<void>;
  signUpWithEmail: (
    email: string,
    password: string,
    profile: {
      name?: string;
      username?: string;
      phone?: string;
    } | undefined,
    captchaToken: string
  ) => Promise<{
    session: Session | null;
    user: User | null;
    requiresEmailConfirmation: boolean;
  }>;
  resetPasswordForEmail: (email: string, captchaToken: string) => Promise<void>;
  updatePassword: (password: string) => Promise<void>;
  activatePasswordRecoveryMode: (expectedSessionKey: string | null) => boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const INVALID_LOGIN_MESSAGE = 'Incorrect email or password. Please try again.';
const EMAIL_NOT_CONFIRMED_MESSAGE =
  'Please confirm your email address before logging in.';
const AUTH_SERVICE_UNAVAILABLE_MESSAGE =
  'Unable to reach the auth service. Check your connection and try again.';
const SIGN_UP_FAILED_MESSAGE = 'Unable to create an account. Check your details and try again.';

function toSupabaseErrorDetails(error: unknown) {
  // Normalize Supabase errors so logs stay structured.
  if (!error || typeof error !== 'object') {
    return { raw: error };
  }

  return {
    name: 'name' in error ? error.name : undefined,
    message: 'message' in error ? error.message : undefined,
    code: 'code' in error ? error.code : undefined,
    status: 'status' in error ? error.status : undefined,
    details: 'details' in error ? error.details : undefined,
    hint: 'hint' in error ? error.hint : undefined,
    __isAuthError: '__isAuthError' in error ? error.__isAuthError : undefined,
    raw: error,
  };
}

function logSupabaseError(context: string, error: unknown, extra?: Record<string, unknown>) {
  // Keep auth failures visible without losing the original shape.
  console.error(`[Supabase] ${context}`, {
    ...toSupabaseErrorDetails(error),
    ...(extra ?? {}),
  });
}

function getErrorMessage(error: unknown) {
  if (!error || typeof error !== 'object' || !('message' in error)) {
    return null;
  }

  return typeof error.message === 'string' ? error.message : null;
}

function getErrorCode(error: unknown) {
  if (!error || typeof error !== 'object' || !('code' in error)) {
    return null;
  }

  return typeof error.code === 'string' ? error.code : null;
}

function getErrorName(error: unknown) {
  if (!error || typeof error !== 'object' || !('name' in error)) {
    return null;
  }

  return typeof error.name === 'string' ? error.name : null;
}

function requireCaptchaToken(captchaToken: string) {
  if (!captchaToken?.trim()) {
    throw new Error('Complete the security check and try again.');
  }

  return captchaToken;
}

function getSignInErrorMessage(error: unknown) {
  const message = getErrorMessage(error);
  const normalizedMessage = message?.toLowerCase() ?? '';
  const code = getErrorCode(error);
  const name = getErrorName(error);

  if (code === 'invalid_credentials' || normalizedMessage === 'invalid login credentials') {
    return INVALID_LOGIN_MESSAGE;
  }

  if (code === 'email_not_confirmed' || normalizedMessage.includes('email not confirmed')) {
    return EMAIL_NOT_CONFIRMED_MESSAGE;
  }

  if (name === 'AuthRetryableFetchError' || normalizedMessage.includes('failed to fetch')) {
    return AUTH_SERVICE_UNAVAILABLE_MESSAGE;
  }

  if (normalizedMessage.includes('captcha') || normalizedMessage.includes('turnstile')) {
    return 'Security verification failed. Complete the security check and try again.';
  }

  return message ?? 'Unable to log in.';
}

function getSignUpErrorMessage(error: unknown) {
  const message = getErrorMessage(error)?.toLowerCase() ?? '';
  const name = getErrorName(error);

  if (name === 'AuthRetryableFetchError' || message.includes('failed to fetch')) {
    return AUTH_SERVICE_UNAVAILABLE_MESSAGE;
  }

  if (message.includes('captcha') || message.includes('turnstile')) {
    return 'Security verification failed. Complete the security check and try again.';
  }

  return SIGN_UP_FAILED_MESSAGE;
}

function getAuthRedirectUrl(route: 'login' | 'reset' = 'reset') {
  // Recovery links need a platform-specific redirect target.
  if (Platform.OS === 'web') {
    return typeof window !== 'undefined' && window.location.origin
      ? `${window.location.origin}${process.env.EXPO_PUBLIC_WEB_ROUTER_BASE === '/' ? '' : '/app'}/${route}`
      : undefined;
  }

  return route === 'reset' ? 'pesoapp://reset-password' : 'pesoapp://login';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState(getAcceptedAuthSnapshot);
  const [initializationError, setInitializationError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [passwordRecoveryMode, setPasswordRecoveryMode] = useState(false);
  const pendingRecoveryLinkRef = useRef(false);
  const recoverySessionKeyRef = useRef<string | null>(null);
  const session = snapshot.status === 'ready' ? snapshot.session : null;
  const initializing = snapshot.status === 'initializing' || snapshot.status === 'pending';

  useEffect(() => {
    let active = true;
    let profileRevision = -1;
    const publish = (next: ReturnType<typeof getAcceptedAuthSnapshot>) => {
      if (!active) return;
      setSnapshot(next);
      if (next.status !== 'ready') return;
      setInitializationError(null);
      const nextKey = getPrivateMediaSessionKey(next.session?.access_token, supabaseAuthUrl);
      if (next.event === 'PASSWORD_RECOVERY' && nextKey) {
        pendingRecoveryLinkRef.current = true;
        recoverySessionKeyRef.current = nextKey;
        setPasswordRecoveryMode(true);
      } else if (!next.session || (pendingRecoveryLinkRef.current && recoverySessionKeyRef.current !== nextKey)) {
        pendingRecoveryLinkRef.current = false;
        recoverySessionKeyRef.current = null;
        setPasswordRecoveryMode(false);
      }
      if (next.session?.user && next.revision !== profileRevision) {
        profileRevision = next.revision;
        const accepted = next.session;
        // Profile work uses the accepted generation, never the raw Auth callback.
        void Promise.resolve().then(async () => {
          const current = getAcceptedAuthSnapshot();
          if (active && current.status === 'ready' && current.revision === next.revision) {
            await ensureOwnProfile(accepted.user, accepted.access_token);
          }
        }).catch(() => {
          console.warn('Unable to initialize profile. Profile editing can retry after loading.');
        });
      }
    };
    const unsubscribe = subscribeAcceptedAuthSession(publish);
    publish(getAcceptedAuthSnapshot());
    void initializeAcceptedAuthSession().catch(() => {
      if (active) setInitializationError('Unable to finish your sign-in change. Please retry.');
    });
    return () => { active = false; unsubscribe(); };
  }, []);

  useEffect(() => {
    const supabaseClient = supabase;
    if (!supabaseClient || Platform.OS === 'web') {
      return;
    }

    const updateRefreshState = (state: string) => {
      if (state === 'active') {
        supabaseClient.auth.startAutoRefresh();
      } else {
        supabaseClient.auth.stopAutoRefresh();
      }
    };

    updateRefreshState(AppState.currentState);
    const appStateSubscription = AppState.addEventListener('change', updateRefreshState);

    return () => {
      appStateSubscription.remove();
      supabaseClient.auth.stopAutoRefresh();
    };
  }, []);

  const value: AuthContextValue = {
    session,
    mediaSessionKey: getPrivateMediaSessionKey(session?.access_token, supabaseAuthUrl),
    user: session?.user ?? null,
    initializing,
    configError: supabaseConfigError,
    passwordRecoveryMode,
    async signInWithEmail(email, password, captchaToken) {
      // Password login is a thin wrapper over Supabase auth.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const verifiedCaptchaToken = requireCaptchaToken(captchaToken);
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
        options: { captchaToken: verifiedCaptchaToken },
      });

      if (error) {
        logSupabaseError('signInWithPassword failed', error);
        throw new Error(getSignInErrorMessage(error));
      }
      await waitForAcceptedAuthSession(data.session);
    },
    async signUpWithEmail(email, password, profile, captchaToken) {
      // Signup stores profile hints in auth metadata.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const verifiedCaptchaToken = requireCaptchaToken(captchaToken);
      const trimmedUsername = profile?.username?.trim();
      const trimmedName = profile?.name?.trim();
      const trimmedPhone = profile?.phone?.trim();
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          ...(getAuthRedirectUrl('login') ? { emailRedirectTo: getAuthRedirectUrl('login') } : {}),
          captchaToken: verifiedCaptchaToken,
          data: {
            ...(trimmedName ? { name: trimmedName } : {}),
            ...(trimmedUsername ? { username: trimmedUsername } : {}),
            ...(trimmedPhone ? { phone: trimmedPhone } : {}),
          },
        },
      });

      if (error) {
        logSupabaseError('signUp failed', error);
        throw new Error(getSignUpErrorMessage(error));
      }

      const acceptedSession = data.session ? await waitForAcceptedAuthSession(data.session) : null;
      return {
        session: acceptedSession,
        user: data.user,
        requiresEmailConfirmation: !acceptedSession,
      };
    },
    async resetPasswordForEmail(email, captchaToken) {
      // Request the reset email with a platform-appropriate callback URL.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const verifiedCaptchaToken = requireCaptchaToken(captchaToken);
      const redirectTo = getAuthRedirectUrl();
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        ...(redirectTo ? { redirectTo } : {}),
        captchaToken: verifiedCaptchaToken,
      });

      if (error) {
        logSupabaseError('resetPasswordForEmail failed', error);
        const message = getErrorMessage(error)?.toLowerCase() ?? '';
        if (message.includes('captcha') || message.includes('turnstile')) {
          throw new Error('Security verification failed. Complete the security check and try again.');
        }
        if (getErrorName(error) === 'AuthRetryableFetchError' || message.includes('failed to fetch')) {
          throw new Error(AUTH_SERVICE_UNAVAILABLE_MESSAGE);
        }
        throw new Error('Unable to request a password reset. Please try again.');
      }
    },
    async updatePassword(password) {
      // Password updates clear recovery mode after success.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const expectedKey = getPrivateMediaSessionKey(session?.access_token, supabaseAuthUrl);
      const { error } = await updateUserWithPrivateMedia(expectedKey, { password });

      if (error) {
        throw error;
      }

      const current = getAcceptedAuthSnapshot();
      if (expectedKey && (current.status !== 'ready'
          || getPrivateMediaSessionKey(current.session?.access_token, supabaseAuthUrl) !== expectedKey)) {
        throw new Error('Your sign-in session changed. Please retry the account update.');
      }
      setPasswordRecoveryMode(false);
      pendingRecoveryLinkRef.current = false;
      recoverySessionKeyRef.current = null;
    },
    activatePasswordRecoveryMode(expectedSessionKey) {
      // Native listeners outlive a render; validate the accepted callback identity now.
      const current = getAcceptedAuthSnapshot();
      const key = getPrivateMediaSessionKey(current.session?.access_token, supabaseAuthUrl);
      if (current.status !== 'ready' || !expectedSessionKey || key !== expectedSessionKey) return false;
      pendingRecoveryLinkRef.current = true;
      recoverySessionKeyRef.current = expectedSessionKey;
      setPasswordRecoveryMode(true);
      return true;
    },
    async signOut() {
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await signOutWithPrivateMedia(getPrivateMediaSessionKey(session?.access_token, supabaseAuthUrl));

      if (error) {
        throw error;
      }

      pendingRecoveryLinkRef.current = false;
      recoverySessionKeyRef.current = null;
    },
  };

  const transitionVisible = snapshot.status !== 'ready' || initializationError !== null;
  const transitionError = initializationError ?? snapshot.error;
  const retry = async () => {
    setRetrying(true);
    setInitializationError(null);
    try {
      await retryAuthSessionTransition();
      await initializeAcceptedAuthSession();
    } catch {
      setInitializationError('Unable to finish your sign-in change. Please retry.');
    } finally { setRetrying(false); }
  };

  return (
    <AuthContext.Provider value={value}>
      <View style={transitionStyles.root}>
        <View style={[transitionStyles.root, transitionVisible && transitionStyles.hidden]}>{children}</View>
        {transitionVisible && <View style={transitionStyles.panel} accessibilityViewIsModal>
          <Text accessibilityRole="header" style={transitionStyles.title}>Finishing your sign-in change</Text>
          <Text accessibilityRole={transitionError ? 'alert' : undefined} style={transitionStyles.message}>
            {transitionError ?? 'Securing your previous session before continuing…'}
          </Text>
          {(snapshot.status === 'blocked' || initializationError) && <Pressable accessibilityRole="button"
            accessibilityState={{ disabled: retrying, busy: retrying }} disabled={retrying}
            onPress={() => { void retry(); }} style={transitionStyles.button}>
            <Text style={transitionStyles.buttonText}>{retrying ? 'Retrying…' : 'Retry session change'}</Text>
          </Pressable>}
        </View>}
      </View>
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}

const transitionStyles = StyleSheet.create({
  root: { flex: 1 },
  hidden: { display: 'none' },
  panel: { flex: 1, minHeight: 320, justifyContent: 'center', alignItems: 'center', padding: 28,
    gap: 18, backgroundColor: '#07090D' },
  title: { color: '#FFFFFF', fontSize: 22, fontWeight: '600', textAlign: 'center' },
  message: { color: '#A7B3C7', fontSize: 16, textAlign: 'center', maxWidth: 460 },
  button: { paddingHorizontal: 22, paddingVertical: 14, borderRadius: 10, backgroundColor: '#1F6BFF' },
  buttonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '600' },
});
