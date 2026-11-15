import type { ImagePickerAsset } from 'expo-image-picker';
import Constants, { AppOwnership } from 'expo-constants';
import { Platform } from 'react-native';
import type { User } from '@supabase/supabase-js';
import { supabaseAuthUrl } from './supabase';
import { beginProfileAvatarOperation, readProfileAvatar } from './avatarReader';
import { BackendHttpError, fetchOwnProfileMetadata, updateOwnProfileMetadata,
  uploadOwnProfileAvatar, publishOwnProfileAvatar } from './backendApi';
import { getPrivateMediaEpoch, getActivePrivateMediaSessionKey } from './privateMediaLifecycle';
import { getPrivateMediaSessionKey } from './privateMediaLogout';
import { isCanonicalUuid, normalizeProfileDetails, validateProfileEnvelope,
  validateAvatarAttempt, validatePublishedProfile } from './profilePolicy';
import type { ProfileDetails, ProfileRecord } from './profilePolicy';

const MAX_AVATAR_UPLOAD_BYTES = 512 * 1024;
const AVATAR_COMPRESS_MAX_DIMENSION = 512;
const AVATAR_COMPRESS_QUALITY = 0.72;
const ALLOWED_AVATAR_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp'] as const;

type NativeImageCompressor = {
  compress: (
    value: string,
    options?: {
      compressionMethod?: 'auto' | 'manual';
      maxWidth?: number;
      maxHeight?: number;
      quality?: number;
      input?: 'base64' | 'uri';
      output?: 'jpg' | 'png';
      returnableOutputType?: 'uri' | 'base64';
    }
  ) => Promise<string>;
};

type WebImageAsset = ImagePickerAsset & {
  file?: File | null;
};

let cachedNativeImageCompressor: NativeImageCompressor | null | undefined;

export type UserProfile = Omit<ProfileRecord, 'created_at' | 'updated_at' | 'profile_revision'> & {
  created_at?: string;
  updated_at?: string;
  profile_revision: string | null;
  avatar_data_uri?: string | null;
  avatar_reupload_required?: boolean;
  avatar_error?: string | null;
};

export type ProfileUpdate = ProfileDetails;

function captureProfileSession(user: User, accessToken: string) {
  const owner = user.id;
  const epoch = getPrivateMediaEpoch();
  const key = getPrivateMediaSessionKey(accessToken, supabaseAuthUrl);
  const assertCurrent = () => {
    if (!isCanonicalUuid(owner) || !key || !key.startsWith(owner + ':')
        || epoch !== getPrivateMediaEpoch() || key !== getActivePrivateMediaSessionKey()) {
      throw new Error('Your sign-in session changed. Please try again.');
    }
  };
  assertCurrent();
  return { owner, assertCurrent };
}

function assertRevision(revision: string | null) {
  if (revision !== null && !isCanonicalUuid(revision)) throw new Error('Reload your profile before saving.');
}

function normalizeMimeType(value?: string | null) {
  return value?.split(';')[0]?.trim().toLowerCase() ?? '';
}

function assertSupportedAvatarSource(contentType: string, sizeBytes: number) {
  const normalizedContentType = normalizeMimeType(contentType);

  if (
    !ALLOWED_AVATAR_MIME_TYPES.includes(
      normalizedContentType as (typeof ALLOWED_AVATAR_MIME_TYPES)[number]
    )
  ) {
    throw new Error('Unsupported profile image format. Choose a JPG, PNG, or WebP image.');
  }

  if (!Number.isSafeInteger(sizeBytes) || sizeBytes <= 0 || sizeBytes > MAX_AVATAR_UPLOAD_BYTES) {
    throw new Error('Profile image is too large. Choose an image under 512 KB.');
  }
}

function getNativeImageCompressor() {
  if (Platform.OS === 'web' || Constants.appOwnership === AppOwnership.Expo) {
    return null;
  }

  if (cachedNativeImageCompressor !== undefined) {
    return cachedNativeImageCompressor;
  }

  try {
    const compressorModule = require('react-native-compressor') as typeof import('react-native-compressor');
    cachedNativeImageCompressor = compressorModule.Image ?? null;
  } catch {
    cachedNativeImageCompressor = null;
  }

  return cachedNativeImageCompressor;
}

async function maybeCompressAvatarAsset(asset: ImagePickerAsset) {
  const compressor = getNativeImageCompressor();

  if (!compressor) {
    return asset;
  }

  const compressedUri = await compressor.compress(asset.uri, {
    compressionMethod: 'manual',
    maxWidth: AVATAR_COMPRESS_MAX_DIMENSION,
    maxHeight: AVATAR_COMPRESS_MAX_DIMENSION,
    quality: AVATAR_COMPRESS_QUALITY,
    input: 'uri',
    output: 'jpg',
    returnableOutputType: 'uri',
  });

  return {
    ...asset,
    uri: compressedUri,
    fileName: 'avatar.jpg',
    mimeType: 'image/jpeg',
  };
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

function fallbackProfile(user: User, owner: string): UserProfile {
  return {
    id: owner,
    username: deriveUsernameFromUser(user),
    display_name: typeof user.user_metadata?.name === 'string' ? user.user_metadata.name : null,
    avatar_path: null,
    avatar_data_uri: null,
    profile_revision: null,
  };
}

async function readProfile(owner: string, accessToken: string, assertCurrent: () => void) {
  assertCurrent();
  const value = await fetchOwnProfileMetadata(accessToken);
  assertCurrent();
  return validateProfileEnvelope(value, owner);
}

async function withAvatar(profile: UserProfile, accessToken: string, assertSession: () => void,
  operation: ReturnType<typeof beginProfileAvatarOperation>, signal?: AbortSignal): Promise<UserProfile> {
  const key = getPrivateMediaSessionKey(accessToken, supabaseAuthUrl);
  assertSession();
  if (!key) throw new Error('Your sign-in session changed. Please try again.');
  operation.observe(key, profile.profile_revision);
  const assertCurrent = () => { assertSession(); operation.assertCurrent(); };
  const image = profile.avatar_path ? await readProfileAvatar(accessToken, profile.profile_revision, assertCurrent, signal)
    : { avatar_data_uri: null, avatar_reupload_required: false, avatar_error: null };
  assertCurrent();
  return { ...profile, ...image };
}

export async function loadOwnProfile(user: User, accessToken: string, signal?: AbortSignal): Promise<UserProfile> {
  const { owner, assertCurrent: assertSession } = captureProfileSession(user, accessToken);
  const operation = beginProfileAvatarOperation();
  const assertCurrent = () => { assertSession(); operation.assertCurrent(); if (signal?.aborted) throw new Error('Profile loading was cancelled.'); };
  const profile = await readProfile(owner, accessToken, assertCurrent);
  return withAvatar(profile ?? fallbackProfile(user, owner), accessToken, assertCurrent, operation, signal);
}

export async function saveOwnProfile(
  user: User, accessToken: string, revision: string | null, update: ProfileUpdate, signal?: AbortSignal
): Promise<UserProfile> {
  const { owner, assertCurrent: assertSession } = captureProfileSession(user, accessToken);
  assertRevision(revision);
  const details = normalizeProfileDetails(update);
  const operation = beginProfileAvatarOperation(true);
  const assertCurrent = () => { assertSession(); operation.assertCurrent(); };
  try {
    const value = await updateOwnProfileMetadata(accessToken, { profile_revision: revision, ...details });
    assertCurrent();
    const profile = validatePublishedProfile(value, owner, revision, details);
    return await withAvatar(profile, accessToken, assertSession, operation, signal);
  } finally { operation.finish(); }
}

// Create signup profile hints once; refreshes must never overwrite existing edits.
export async function ensureOwnProfile(user: User, accessToken: string): Promise<void> {
  const { owner, assertCurrent } = captureProfileSession(user, accessToken);
  if (await readProfile(owner, accessToken, assertCurrent)) return;
  const fallback = fallbackProfile(user, owner);
  const username = fallback.username?.trim().toLowerCase() ?? null;
  const details = normalizeProfileDetails({
    username: username && /^[a-z0-9_]{3,30}$/.test(username) ? username : null,
    display_name: fallback.display_name,
  });
  const create = async (nextDetails: typeof details) => {
    assertCurrent();
    const value = await updateOwnProfileMetadata(accessToken, { profile_revision: null, ...nextDetails });
    assertCurrent();
    validatePublishedProfile(value, owner, null, nextDetails, null);
  };
  try {
    await create(details);
  } catch (error) {
    assertCurrent();
    if (!(error instanceof BackendHttpError) || error.status !== 409) throw error;
    // A concurrent initializer may already have reserved the username for this owner.
    if (await readProfile(owner, accessToken, assertCurrent)) return;
    try {
      await create({ ...details, username: null });
    } catch (retryError) {
      assertCurrent();
      if (!(retryError instanceof BackendHttpError) || retryError.status !== 409
          || !(await readProfile(owner, accessToken, assertCurrent))) throw retryError;
    }
  }
}

async function resolveAvatarUploadSource(asset: ImagePickerAsset, assertCurrent: () => void) {
  assertCurrent();
  const uploadAsset = await maybeCompressAvatarAsset(asset);
  assertCurrent();
  const webAsset = asset as WebImageAsset;

  if (Platform.OS === 'web' && webAsset.file) {
    const contentType = normalizeMimeType(webAsset.file.type || uploadAsset.mimeType || 'image/jpeg');
    assertSupportedAvatarSource(contentType, webAsset.file.size);
    return {
      body: webAsset.file,
      contentType,
      sizeBytes: webAsset.file.size,
    };
  }

  const response = await fetch(uploadAsset.uri);
  assertCurrent();

  if (!response.ok) {
    throw new Error('Unable to read selected profile image.');
  }

  const blob = await response.blob();
  assertCurrent();
  const contentType = normalizeMimeType(uploadAsset.mimeType || blob.type || 'image/jpeg');
  assertSupportedAvatarSource(contentType, blob.size);

  return {
    body: blob,
    contentType,
    sizeBytes: blob.size,
  };
}

export async function uploadProfileAvatar(
  user: User,
  accessToken: string,
  asset: ImagePickerAsset,
  revision: string | null,
  update: ProfileUpdate,
  signal?: AbortSignal
): Promise<UserProfile> {
  const { owner, assertCurrent: assertSession } = captureProfileSession(user, accessToken);
  assertRevision(revision);
  const details = normalizeProfileDetails(update);
  const operation = beginProfileAvatarOperation(true);
  const assertCurrent = () => { assertSession(); operation.assertCurrent(); };
  try {
    const uploadSource = await resolveAvatarUploadSource(asset, assertCurrent);
    assertCurrent();
    const uploaded = await uploadOwnProfileAvatar(accessToken, revision, uploadSource.body, uploadSource.contentType);
    assertCurrent();
    const attempt = validateAvatarAttempt(uploaded, owner);
    const published = await publishOwnProfileAvatar(accessToken, attempt.attempt_id, details);
    assertCurrent();
    const profile = validatePublishedProfile(published, owner, revision, details, attempt.avatar_path);
    return await withAvatar(profile, accessToken, assertSession, operation, signal);
  } finally { operation.finish(); }
}
