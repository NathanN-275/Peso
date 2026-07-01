import type { ImagePickerAsset } from 'expo-image-picker';
import { Platform } from 'react-native';
import type { User } from '@supabase/supabase-js';
import { supabase, supabaseConfigError } from './supabase';

const PROFILE_AVATAR_BUCKET = 'profile-avatars';
const AVATAR_SIGNED_URL_EXPIRES_IN_SECONDS = 60 * 60;

type WebImageAsset = ImagePickerAsset & {
  file?: File | null;
};

export type UserProfile = {
  id: string;
  username: string | null;
  display_name: string | null;
  avatar_path: string | null;
  avatar_url?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type ProfileUpdate = {
  username?: string | null;
  display_name?: string | null;
  avatar_path?: string | null;
};

function requireSupabase() {
  if (!supabase) {
    throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  }

  return supabase;
}

function normalizeOptionalText(value?: string | null) {
  const trimmedValue = value?.trim() ?? '';
  return trimmedValue ? trimmedValue : null;
}

function isMissingProfileInfrastructureError(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false;
  }

  const code = 'code' in error ? error.code : undefined;
  const message = 'message' in error ? error.message : undefined;
  const normalizedMessage = typeof message === 'string' ? message.toLowerCase() : '';

  return (
    code === 'PGRST205' ||
    normalizedMessage.includes("could not find the table 'public.profiles'") ||
    normalizedMessage.includes("relation \"public.profiles\" does not exist") ||
    normalizedMessage.includes('bucket not found') ||
    normalizedMessage.includes('profile-avatars')
  );
}

export function deriveUsernameFromUser(user: User | null) {
  const metadataUsername =
    typeof user?.user_metadata?.username === 'string' ? user.user_metadata.username : null;

  if (metadataUsername) {
    return metadataUsername;
  }

  if (user?.email) {
    return user.email.split('@')[0] ?? null;
  }

  return user?.phone ?? null;
}

export function getProfileDisplayName(profile: UserProfile | null, user: User | null) {
  return profile?.display_name || profile?.username || deriveUsernameFromUser(user) || 'Username';
}

export async function getProfileAvatarUrl(avatarPath?: string | null) {
  if (!avatarPath) {
    return null;
  }

  const client = requireSupabase();
  const { data, error } = await client.storage
    .from(PROFILE_AVATAR_BUCKET)
    .createSignedUrl(avatarPath, AVATAR_SIGNED_URL_EXPIRES_IN_SECONDS);

  if (error) {
    if (isMissingProfileInfrastructureError(error)) {
      return null;
    }

    throw error;
  }

  return data.signedUrl;
}

export async function loadOwnProfile(user: User): Promise<UserProfile> {
  const client = requireSupabase();
  const fallbackProfile: UserProfile = {
    id: user.id,
    username: deriveUsernameFromUser(user),
    display_name: typeof user.user_metadata?.name === 'string' ? user.user_metadata.name : null,
    avatar_path: null,
  };
  const { data, error } = await client
    .from('profiles')
    .select('id, username, display_name, avatar_path, created_at, updated_at')
    .eq('id', user.id)
    .maybeSingle();

  if (error) {
    if (isMissingProfileInfrastructureError(error)) {
      return {
        ...fallbackProfile,
        avatar_url: null,
      };
    }

    throw error;
  }

  const profile = (data ?? fallbackProfile) as UserProfile;
  const avatarUrl = await getProfileAvatarUrl(profile.avatar_path);

  return {
    ...fallbackProfile,
    ...profile,
    avatar_url: avatarUrl,
  };
}

export async function saveOwnProfile(user: User, update: ProfileUpdate): Promise<UserProfile> {
  const client = requireSupabase();
  const profilePayload = {
    id: user.id,
    username: normalizeOptionalText(update.username),
    display_name: normalizeOptionalText(update.display_name),
    avatar_path: normalizeOptionalText(update.avatar_path),
  };
  const { data, error } = await client
    .from('profiles')
    .upsert(profilePayload, { onConflict: 'id' })
    .select('id, username, display_name, avatar_path, created_at, updated_at')
    .single();

  if (error) {
    if (isMissingProfileInfrastructureError(error)) {
      throw new Error('Profile editing needs the user profile migration to be applied.');
    }

    throw error;
  }

  const profile = data as UserProfile;
  const avatarUrl = await getProfileAvatarUrl(profile.avatar_path);

  return {
    ...profile,
    avatar_url: avatarUrl,
  };
}

function inferImageExtension(asset: ImagePickerAsset, contentType: string) {
  const filename = asset.fileName ?? asset.uri.split('/').pop() ?? '';
  const extension = filename.split(/[?#]/)[0].split('.').pop()?.toLowerCase();

  if (extension && ['jpg', 'jpeg', 'png', 'webp'].includes(extension)) {
    return extension === 'jpeg' ? 'jpg' : extension;
  }

  if (contentType === 'image/png') {
    return 'png';
  }

  if (contentType === 'image/webp') {
    return 'webp';
  }

  return 'jpg';
}

async function resolveAvatarUploadSource(asset: ImagePickerAsset) {
  const webAsset = asset as WebImageAsset;

  if (Platform.OS === 'web' && webAsset.file) {
    const contentType = webAsset.file.type || asset.mimeType || 'image/jpeg';
    return {
      body: webAsset.file,
      contentType,
      extension: inferImageExtension(asset, contentType),
    };
  }

  const response = await fetch(asset.uri);

  if (!response.ok) {
    throw new Error('Unable to read selected profile image.');
  }

  const blob = await response.blob();
  const contentType = asset.mimeType || blob.type || 'image/jpeg';

  return {
    body: blob,
    contentType,
    extension: inferImageExtension(asset, contentType),
  };
}

export async function uploadProfileAvatar(
  user: User,
  asset: ImagePickerAsset,
  previousAvatarPath?: string | null
) {
  const client = requireSupabase();
  const uploadSource = await resolveAvatarUploadSource(asset);
  const avatarPath = `${user.id}/avatar-${Date.now()}.${uploadSource.extension}`;
  const { error: uploadError } = await client.storage
    .from(PROFILE_AVATAR_BUCKET)
    .upload(avatarPath, uploadSource.body, {
      cacheControl: '3600',
      contentType: uploadSource.contentType,
      upsert: false,
    });

  if (uploadError) {
    throw uploadError;
  }

  if (previousAvatarPath && previousAvatarPath.startsWith(`${user.id}/`)) {
    const { error: removeError } = await client.storage
      .from(PROFILE_AVATAR_BUCKET)
      .remove([previousAvatarPath]);

    if (removeError && __DEV__) {
      console.warn('Unable to remove previous profile avatar.', removeError);
    }
  }

  return {
    avatarPath,
    avatarUrl: await getProfileAvatarUrl(avatarPath),
  };
}
