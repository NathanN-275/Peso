import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient, processLock } from '@supabase/supabase-js';
import { Platform } from 'react-native';

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabasePublishableKey = process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const legacySupabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
const supabaseClientKey = supabasePublishableKey || legacySupabaseAnonKey;
const supabaseConfig =
  supabaseUrl && supabaseClientKey
    ? { url: supabaseUrl, clientKey: supabaseClientKey }
    : null;

if (!supabasePublishableKey && legacySupabaseAnonKey) {
  console.warn(
    'EXPO_PUBLIC_SUPABASE_ANON_KEY is deprecated; migrate this build to EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.'
  );
}

export const supabaseConfigError =
  supabaseConfig === null
    ? 'Missing Supabase environment variables. Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY.'
    : null;

export const supabase =
  supabaseConfig
    ? createClient(supabaseConfig.url, supabaseConfig.clientKey, {
        auth: {
          storage: Platform.OS === 'web' ? undefined : AsyncStorage,
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: Platform.OS === 'web',
          flowType: 'pkce',
          lock: Platform.OS === 'web' ? undefined : processLock,
        },
      })
    : null;
