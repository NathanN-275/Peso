import { ReactNode, createContext, useContext, useEffect, useRef, useState } from 'react';
import { Session, User } from '@supabase/supabase-js';
import * as ExpoLinking from 'expo-linking';
import { Platform } from 'react-native';
import { supabase, supabaseConfigError } from '../lib/supabase';

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  initializing: boolean;
  configError: string | null;
  passwordRecoveryMode: boolean;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (
    email: string,
    password: string,
    profile?: {
      name?: string;
      username?: string;
      phone?: string;
    }
  ) => Promise<{
    session: Session | null;
    user: User | null;
    requiresEmailConfirmation: boolean;
  }>;
  resetPasswordForEmail: (email: string) => Promise<void>;
  updatePassword: (password: string) => Promise<void>;
  activatePasswordRecoveryMode: () => void;
  sendPhoneOtp: (phone: string) => Promise<void>;
  verifyPhoneOtp: (phone: string, token: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

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

function isMissingProfilesTableError(error: unknown) {
  // Missing profile tables are tolerated during early setup.
  if (!error || typeof error !== 'object') {
    return false;
  }

  const code = 'code' in error ? error.code : undefined;
  const message = 'message' in error ? error.message : undefined;

  return (
    code === 'PGRST205' ||
    (typeof message === 'string' &&
      message.includes("Could not find the table 'public.profiles' in the schema cache"))
  );
}

function deriveUsername(user: User) {
  // Fall back through metadata, email, then phone.
  const metadataUsername =
    typeof user.user_metadata?.username === 'string' ? user.user_metadata.username : null;

  if (metadataUsername) {
    return metadataUsername;
  }

  if (user.email) {
    return user.email.split('@')[0] ?? null;
  }

  return user.phone ?? null;
}

function getAuthRedirectUrl() {
  // Recovery links need a platform-specific redirect target.
  if (Platform.OS === 'web') {
    return typeof window !== 'undefined' && window.location.origin
      ? `${window.location.origin}/?auth=reset-password`
      : undefined;
  }

  return ExpoLinking.createURL('reset-password');
}

async function ensureProfile(user: User) {
  // Keep a matching profiles row in Supabase when possible.
  if (!supabase) {
    throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  }

  const profilePayload = {
    id: user.id,
    username: deriveUsername(user),
  };

  const { error } = await supabase.from('profiles').upsert(profilePayload, {
    onConflict: 'id',
  });

  if (error) {
    if (isMissingProfilesTableError(error)) {
      console.warn(
        "Supabase table 'public.profiles' is missing. Continuing without profile sync."
      );
      return;
    }

    logSupabaseError('ensureProfile failed', error, {
      table: 'profiles',
      operation: 'upsert',
      userId: user.id,
    });
    throw error;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Auth state lives here so every screen can read the same session.
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [passwordRecoveryMode, setPasswordRecoveryMode] = useState(false);
  const pendingRecoveryLinkRef = useRef(false);

  useEffect(() => {
    // Bootstrap the current session once at startup.
    let active = true;

    const bootstrap = async () => {
      if (!supabase) {
        if (active) {
          setInitializing(false);
        }
        return;
      }

      const {
        data: { session: currentSession },
        error,
      } = await supabase.auth.getSession();

      if (error) {
        throw error;
      }

      if (!active) {
        return;
      }

      setSession(currentSession);
      if (!pendingRecoveryLinkRef.current) {
        setPasswordRecoveryMode(false);
      }

      if (currentSession?.user) {
        await ensureProfile(currentSession.user);
      }

      if (active) {
        setInitializing(false);
      }
    };

    bootstrap().catch((error) => {
      logSupabaseError('Failed to initialize auth session', error);
      if (active) {
        setInitializing(false);
      }
    });

    if (!supabase) {
      return () => {
        active = false;
      };
    }

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      // Track sign-in, sign-out, and password recovery in one place.
      setSession(nextSession);

      if (event === 'PASSWORD_RECOVERY') {
        pendingRecoveryLinkRef.current = true;
        setPasswordRecoveryMode(true);
        return;
      }

      if (event === 'SIGNED_OUT') {
        pendingRecoveryLinkRef.current = false;
        setPasswordRecoveryMode(false);
      }

      if ((event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') && nextSession?.user) {
        ensureProfile(nextSession.user).catch((error) => {
          logSupabaseError('Failed to ensure profile row after auth state change', error, {
            event,
            userId: nextSession.user.id,
          });
        });
      }
    });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  const value: AuthContextValue = {
    session,
    user: session?.user ?? null,
    initializing,
    configError: supabaseConfigError,
    passwordRecoveryMode,
    async signInWithEmail(email, password) {
      // Password login is a thin wrapper over Supabase auth.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.signInWithPassword({ email, password });

      if (error) {
        logSupabaseError('signInWithPassword failed', error, {
          email,
        });
        throw error;
      }
    },
    async signUpWithEmail(email, password, profile) {
      // Signup stores profile hints in auth metadata.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const trimmedUsername = profile?.username?.trim();
      const trimmedName = profile?.name?.trim();
      const trimmedPhone = profile?.phone?.trim();
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            ...(trimmedName ? { name: trimmedName } : {}),
            ...(trimmedUsername ? { username: trimmedUsername } : {}),
            ...(trimmedPhone ? { phone: trimmedPhone } : {}),
          },
        },
      });

      if (error) {
        throw error;
      }

      return {
        session: data.session,
        user: data.user,
        requiresEmailConfirmation: !data.session,
      };
    },
    async resetPasswordForEmail(email) {
      // Request the reset email with a platform-appropriate callback URL.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const redirectTo = getAuthRedirectUrl();
      console.log('[Supabase] reset redirectTo', redirectTo);
      console.log('[Supabase] resetPasswordForEmail requested', {
        email,
        redirectTo,
      });
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        ...(redirectTo ? { redirectTo } : {}),
      });

      if (error) {
        logSupabaseError('resetPasswordForEmail failed', error, {
          email,
          redirectTo,
        });
        throw error;
      }

      console.log('[Supabase] resetPasswordForEmail succeeded', {
        email,
        redirectTo,
      });
    },
    async updatePassword(password) {
      // Password updates clear recovery mode after success.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.updateUser({ password });

      if (error) {
        throw error;
      }

      setPasswordRecoveryMode(false);
      pendingRecoveryLinkRef.current = false;
    },
    activatePasswordRecoveryMode() {
      // The app switches into recovery UI as soon as a reset link is detected.
      pendingRecoveryLinkRef.current = true;
      setPasswordRecoveryMode(true);
    },
    async sendPhoneOtp(phone) {
      // Phone verification follows the same auth context boundary.
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.signInWithOtp({ phone });

      if (error) {
        throw error;
      }
    },
    async verifyPhoneOtp(phone, token) {
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.verifyOtp({
        phone,
        token,
        type: 'sms',
      });

      if (error) {
        throw error;
      }
    },
    async signOut() {
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.signOut();

      if (error) {
        throw error;
      }

      pendingRecoveryLinkRef.current = false;
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
