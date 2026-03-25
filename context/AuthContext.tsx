import { ReactNode, createContext, useContext, useEffect, useState } from 'react';
import { Session, User } from '@supabase/supabase-js';
import { Linking, Platform } from 'react-native';
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
  sendPhoneOtp: (phone: string) => Promise<void>;
  verifyPhoneOtp: (phone: string, token: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function deriveUsername(user: User) {
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
  if (Platform.OS === 'web') {
    return typeof window !== 'undefined' && window.location.origin
      ? `${window.location.origin}${window.location.pathname}#/reset-password-form`
      : undefined;
  }

  return 'pesoapp://reset-password-form';
}

function parseAuthCallbackUrl(url: string) {
  const urlObject = new URL(url);
  const queryParams = new URLSearchParams(urlObject.search);
  const hash = urlObject.hash.startsWith('#') ? urlObject.hash.slice(1) : urlObject.hash;
  const hashParamsSource = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : hash;
  const hashParams = new URLSearchParams(hashParamsSource);
  const accessToken = queryParams.get('access_token') ?? hashParams.get('access_token');
  const refreshToken = queryParams.get('refresh_token') ?? hashParams.get('refresh_token');
  const type = queryParams.get('type') ?? hashParams.get('type');
  const code = queryParams.get('code') ?? hashParams.get('code');

  if (!code && (!accessToken || !refreshToken)) {
    return null;
  }

  return {
    accessToken,
    refreshToken,
    type,
    code,
  };
}

async function ensureProfile(user: User) {
  if (!supabase) {
    throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  }

  const { data, error } = await supabase.from('profiles').select('id').eq('id', user.id).maybeSingle();

  if (error) {
    throw error;
  }

  if (data) {
    return;
  }

  const { error: insertError } = await supabase.from('profiles').insert({
    id: user.id,
    username: deriveUsername(user),
  });

  if (insertError) {
    throw insertError;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [passwordRecoveryMode, setPasswordRecoveryMode] = useState(false);

  useEffect(() => {
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
      setPasswordRecoveryMode(false);

      if (currentSession?.user) {
        await ensureProfile(currentSession.user);
      }

      if (active) {
        setInitializing(false);
      }
    };

    bootstrap().catch((error) => {
      console.error('Failed to initialize auth session', error);
      if (active) {
        setInitializing(false);
      }
    });

    if (!supabase) {
      return () => {
        active = false;
      };
    }

    const hydrateSessionFromUrl = async (url: string | null) => {
      if (!url || !supabase) {
        return;
      }

      const callback = parseAuthCallbackUrl(url);

      if (!callback) {
        return;
      }

      if (callback.code) {
        const { error } = await supabase.auth.exchangeCodeForSession(callback.code);

        if (error) {
          throw error;
        }
      } else if (callback.accessToken && callback.refreshToken) {
        const { error } = await supabase.auth.setSession({
          access_token: callback.accessToken,
          refresh_token: callback.refreshToken,
        });

        if (error) {
          throw error;
        }
      }

      if (callback.type === 'recovery' && active) {
        setPasswordRecoveryMode(true);
      }
    };

    Linking.getInitialURL()
      .then((url) => hydrateSessionFromUrl(url))
      .catch((error) => {
        console.error('Failed to hydrate auth session from initial URL', error);
      });

    const linkingSubscription = Linking.addEventListener('url', ({ url }) => {
      hydrateSessionFromUrl(url).catch((error) => {
        console.error('Failed to hydrate auth session from incoming URL', error);
      });
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);

       if (event === 'PASSWORD_RECOVERY') {
        setPasswordRecoveryMode(true);
        return;
      }

      if (event === 'SIGNED_OUT') {
        setPasswordRecoveryMode(false);
      }

      if ((event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') && nextSession?.user) {
        ensureProfile(nextSession.user).catch((error) => {
          console.error('Failed to ensure profile row', error);
        });
      }
    });

    return () => {
      active = false;
      linkingSubscription.remove();
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
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.signInWithPassword({ email, password });

      if (error) {
        throw error;
      }
    },
    async signUpWithEmail(email, password, profile) {
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
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const redirectTo = getAuthRedirectUrl();
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        ...(redirectTo ? { redirectTo } : {}),
      });

      if (error) {
        throw error;
      }
    },
    async updatePassword(password) {
      if (!supabase) {
        throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
      }

      const { error } = await supabase.auth.updateUser({ password });

      if (error) {
        throw error;
      }

      setPasswordRecoveryMode(false);
    },
    async sendPhoneOtp(phone) {
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
