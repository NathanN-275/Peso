import type { Session } from '@supabase/supabase-js';
import { supabase, supabaseConfigError } from './supabase';

const TOKEN_REFRESH_BUFFER_SECONDS = 60;

function sessionNeedsRefresh(session: Session | null) {
  if (!session?.access_token) {
    return true;
  }

  if (!session.expires_at) {
    return false;
  }

  const refreshBefore = Math.floor(Date.now() / 1000) + TOKEN_REFRESH_BUFFER_SECONDS;
  return session.expires_at <= refreshBefore;
}

function formatAuthError(error: { message?: string } | null | undefined) {
  return error?.message ? ` ${error.message}` : '';
}

export async function getFreshBackendAccessToken() {
  if (!supabase) {
    throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  }

  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();

  if (error) {
    throw new Error(`Unable to read the current sign-in session.${formatAuthError(error)}`);
  }

  if (session && !sessionNeedsRefresh(session)) {
    return session.access_token;
  }

  const {
    data: { session: refreshedSession },
    error: refreshError,
  } = await supabase.auth.refreshSession();

  if (refreshError) {
    throw new Error(`Unable to refresh the current sign-in session.${formatAuthError(refreshError)}`);
  }

  const nextSession = refreshedSession ?? session;

  if (!nextSession?.access_token) {
    throw new Error('You must be logged in to start analysis.');
  }

  return nextSession.access_token;
}

export function isBackendAuthError(error: unknown) {
  const message = error instanceof Error ? error.message.toLowerCase() : String(error ?? '').toLowerCase();

  return (
    message.includes('401') ||
    message.includes('unauthorized') ||
    message.includes('missing bearer token') ||
    message.includes('invalid bearer token') ||
    message.includes('authenticated user') ||
    message.includes('sign-in session') ||
    message.includes('logged in')
  );
}

export function backendAuthRecoveryMessage() {
  return 'Your sign-in session expired while starting analysis. The upload was cleaned up; sign in again and try again.';
}
