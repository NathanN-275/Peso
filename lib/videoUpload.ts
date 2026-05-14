import Constants, { AppOwnership } from 'expo-constants';
import type { ImagePickerAsset } from 'expo-image-picker';
import { Platform } from 'react-native';
import type { VideoCompressorType } from 'react-native-compressor';
import { CameraAngle, ExerciseOption } from '../src/constants/videoSetup';
import { supabase, supabaseConfigError } from './supabase';

const DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const MAX_UPLOAD_BYTES = resolveFrontendMaxUploadBytes();
const VERY_LARGE_VIDEO_BYTES = 200 * 1024 * 1024;
const TARGET_COMPRESSED_BYTES = Math.min(45 * 1024 * 1024, Math.floor(MAX_UPLOAD_BYTES * 0.9));
const TARGET_MAX_DIMENSION = 1280;
const MIN_POSE_BITRATE = 1_800_000;
const MAX_POSE_BITRATE = 2_500_000;
const AUDIO_BITRATE_RESERVE = 128_000;
const UPLOAD_LIMIT_LABEL = `${Math.round(MAX_UPLOAD_BYTES / (1024 * 1024))} MB`;
const ALLOWED_VIDEO_EXTENSIONS = ['.mp4', '.mov', '.m4v'] as const;
const ALLOWED_VIDEO_MIME_TYPES = [
  'video/mp4',
  'video/quicktime',
  'video/x-m4v',
  'video/m4v',
] as const;

type UploadVideoForAnalysisArgs = {
  asset: ImagePickerAsset;
  exercise: ExerciseOption;
  angle: CameraAngle;
  onStatusChange?: (message: string | null) => void;
};

export type UploadVideoForAnalysisResult = {
  videoId: string;
  status: 'uploaded';
  storagePath: string;
  originalFileSizeBytes: number;
  uploadedFileSizeBytes: number;
  wasCompressed: boolean;
};

type UploadSource = {
  body: Blob | File;
  contentType: string;
  fileName: string;
  sizeBytes: number;
};

type WebImagePickerAsset = ImagePickerAsset & {
  file?: File | null;
};

type UploadableVideoAsset = Pick<ImagePickerAsset, 'uri' | 'fileName' | 'mimeType'> & {
  file?: File | null;
  fileSize?: number;
  type?: string | null;
};

type PreparedVideoForUpload = {
  asset: UploadableVideoAsset;
  originalSizeBytes: number;
  finalSizeBytes: number;
  wasCompressed: boolean;
  wasVeryLarge: boolean;
};

type SupabaseLikeError = {
  code?: string;
  details?: string;
  hint?: string;
  message?: string;
};

type CleanupUploadedVideoForAnalysisArgs = {
  videoId: string;
  storagePath: string;
};

let cachedNativeVideoCompressor: VideoCompressorType | null | undefined;

function resolveFrontendMaxUploadBytes() {
  const rawValue = process.env.EXPO_PUBLIC_MAX_VIDEO_UPLOAD_BYTES?.trim();

  if (!rawValue) {
    return DEFAULT_MAX_UPLOAD_BYTES;
  }

  const parsedValue = Number(rawValue);

  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    if (__DEV__) {
      console.warn(
        '[VideoUpload] Invalid EXPO_PUBLIC_MAX_VIDEO_UPLOAD_BYTES. Falling back to 50 MB.',
        { value: rawValue }
      );
    }

    return DEFAULT_MAX_UPLOAD_BYTES;
  }

  return Math.floor(parsedValue);
}

function logVideoUploadDebug(message: string, details?: Record<string, unknown>) {
  console.log('[VideoUpload]', message, details ?? {});
}

function logVideoUploadWarning(message: string, details?: Record<string, unknown>) {
  console.warn('[VideoUpload]', message, details ?? {});
}

function normalizeExerciseType(exercise: ExerciseOption) {
  return exercise.trim().toLowerCase();
}

function normalizeViewType(angle: CameraAngle) {
  return angle.trim().toLowerCase();
}

function sanitizeFilename(filename: string) {
  return filename.replace(/[^a-zA-Z0-9._-]/g, '-').replace(/-+/g, '-');
}

function buildStoragePath(userId: string, filename: string) {
  const uploadToken = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `${userId}/${uploadToken}-${sanitizeFilename(filename)}`;
}

function inferFileName(asset: UploadableVideoAsset) {
  return asset.fileName ?? asset.uri.split('/').pop() ?? 'video-upload.mp4';
}

function getExplicitAssetMimeType(asset: UploadableVideoAsset) {
  if (asset.mimeType) {
    return asset.mimeType;
  }

  return asset.type?.includes('/') ? asset.type : null;
}

function getFileExtension(filename: string) {
  const normalizedFilename = filename.split(/[?#]/)[0];
  const dotIndex = normalizedFilename.lastIndexOf('.');
  return dotIndex >= 0 ? normalizedFilename.slice(dotIndex).toLowerCase() : '';
}

function isAllowedVideoExtension(filename: string) {
  return ALLOWED_VIDEO_EXTENSIONS.includes(
    getFileExtension(filename) as (typeof ALLOWED_VIDEO_EXTENSIONS)[number]
  );
}

function hasFileExtension(filename: string) {
  return Boolean(getFileExtension(filename));
}

function isAllowedVideoMimeType(mimeType?: string | null) {
  return Boolean(
    mimeType &&
      ALLOWED_VIDEO_MIME_TYPES.includes(
        mimeType.toLowerCase() as (typeof ALLOWED_VIDEO_MIME_TYPES)[number]
      )
  );
}

function inferMimeTypeFromFilename(filename: string) {
  const extension = getFileExtension(filename);

  if (extension === '.mov') {
    return 'video/quicktime';
  }

  if (extension === '.m4v') {
    return 'video/x-m4v';
  }

  if (extension === '.mp4') {
    return 'video/mp4';
  }

  return null;
}

function inferExtensionFromMimeType(mimeType: string) {
  const normalizedMimeType = mimeType.toLowerCase();

  if (normalizedMimeType === 'video/quicktime') {
    return '.mov';
  }

  if (normalizedMimeType === 'video/x-m4v' || normalizedMimeType === 'video/m4v') {
    return '.m4v';
  }

  return '.mp4';
}

function buildUploadFileName(filename: string, contentType: string) {
  if (hasFileExtension(filename)) {
    return filename;
  }

  return `video-upload${inferExtensionFromMimeType(contentType)}`;
}

function assertSupportedVideoFile(fileName: string, mimeType?: string | null) {
  const hasExtension = hasFileExtension(fileName);

  if (hasExtension && !isAllowedVideoExtension(fileName)) {
    throw new Error('Unsupported video file type. Choose an MP4, MOV, or M4V video.');
  }

  if (mimeType && !isAllowedVideoMimeType(mimeType)) {
    throw new Error('Unsupported video format. Choose an MP4, MOV, or M4V video.');
  }

  if (!hasExtension && !isAllowedVideoMimeType(mimeType)) {
    throw new Error('Unable to verify the selected video format. Choose an MP4, MOV, or M4V video.');
  }
}

function validateInitialVideoMetadata(asset: UploadableVideoAsset) {
  const fileName = inferFileName(asset);
  const mimeType = getExplicitAssetMimeType(asset);

  if (hasFileExtension(fileName) || mimeType) {
    assertSupportedVideoFile(fileName, mimeType);
  }
}

function replaceFileExtension(filename: string, nextExtension: string) {
  if (!filename.includes('.')) {
    return `${filename}${nextExtension}`;
  }

  return filename.replace(/\.[^/.]+$/, nextExtension);
}

function inferBitrateFromAsset(asset: ImagePickerAsset, fileSizeBytes: number) {
  if (typeof asset.duration !== 'number' || Number.isNaN(asset.duration) || asset.duration <= 0) {
    return null;
  }

  return Math.floor((fileSizeBytes * 8) / (asset.duration / 1000));
}

function calculateTargetBitrate(asset: ImagePickerAsset, fileSizeBytes: number) {
  const durationSeconds =
    typeof asset.duration === 'number' && !Number.isNaN(asset.duration) && asset.duration > 0
      ? asset.duration / 1000
      : null;
  const originalBitrate = inferBitrateFromAsset(asset, fileSizeBytes);
  const bitrateFromDuration =
    durationSeconds && durationSeconds > 0
      ? Math.floor((TARGET_COMPRESSED_BYTES * 8) / durationSeconds) - AUDIO_BITRATE_RESERVE
      : MAX_POSE_BITRATE;

  const safeBudgetBitrate = Math.max(MIN_POSE_BITRATE, bitrateFromDuration);
  const loweredOriginalBitrate = originalBitrate ? Math.floor(originalBitrate * 0.7) : safeBudgetBitrate;

  return Math.max(MIN_POSE_BITRATE, Math.min(MAX_POSE_BITRATE, safeBudgetBitrate, loweredOriginalBitrate));
}

async function resolveFileSizeFromUri(uri: string) {
  const response = await fetch(uri);

  if (!response.ok) {
    throw new Error('Unable to read the selected video file.');
  }

  const fileBlob = await response.blob();
  return fileBlob.size;
}

async function resolveAssetFileSize(asset: UploadableVideoAsset) {
  if (Platform.OS === 'web' && typeof asset.fileSize === 'number' && !Number.isNaN(asset.fileSize)) {
    return asset.fileSize;
  }

  return resolveFileSizeFromUri(asset.uri);
}

function getNativeVideoCompressor() {
  if (Platform.OS === 'web' || Constants.appOwnership === AppOwnership.Expo) {
    return null;
  }

  if (cachedNativeVideoCompressor !== undefined) {
    return cachedNativeVideoCompressor;
  }

  try {
    const compressorModule = require('react-native-compressor') as typeof import('react-native-compressor');
    cachedNativeVideoCompressor = compressorModule.Video ?? null;
  } catch (error) {
    cachedNativeVideoCompressor = null;

    logVideoUploadWarning('Native compressor module is not available in this build.', {
      reason: error instanceof Error ? error.message : 'unknown_native_module_load_error',
      platform: Platform.OS,
      appOwnership: Constants.appOwnership,
    });
  }

  return cachedNativeVideoCompressor;
}

function canUseNativeCompression() {
  // `react-native-compressor` needs a native build. Expo Go will not include this module.
  return typeof getNativeVideoCompressor()?.compress === 'function';
}

function buildCompressedAsset(asset: ImagePickerAsset, compressedUri: string): UploadableVideoAsset {
  return {
    uri: compressedUri,
    fileName: replaceFileExtension(inferFileName(asset), '.mp4'),
    mimeType: 'video/mp4',
  };
}

async function prepareVideoForUpload(
  asset: ImagePickerAsset,
  onStatusChange?: (message: string | null) => void
): Promise<PreparedVideoForUpload> {
  const metadataSizeBytes =
    typeof asset.fileSize === 'number' && !Number.isNaN(asset.fileSize) ? asset.fileSize : null;
  const originalSizeBytes = await resolveAssetFileSize(asset);
  const wasVeryLarge = originalSizeBytes > VERY_LARGE_VIDEO_BYTES;

  logVideoUploadDebug('Resolved original video size.', {
    platform: Platform.OS,
    appOwnership: Constants.appOwnership,
    assetUri: asset.uri,
    metadataSizeBytes,
    originalSizeBytes,
  });

  if (originalSizeBytes <= MAX_UPLOAD_BYTES) {
    logVideoUploadDebug('Original video is already under the upload limit. Using it as-is.', {
      originalSizeBytes,
      maxUploadBytes: MAX_UPLOAD_BYTES,
    });

    return {
      asset,
      originalSizeBytes,
      finalSizeBytes: originalSizeBytes,
      wasCompressed: false,
      wasVeryLarge,
    };
  }

  if (!canUseNativeCompression()) {
    const reason =
      Platform.OS === 'web'
        ? 'web_runtime_no_client_side_compression'
        : Constants.appOwnership === AppOwnership.Expo
          ? 'expo_go_native_module_unavailable'
          : 'native_compressor_api_unavailable';

    logVideoUploadWarning('Compression cannot run in the current runtime.', {
      reason,
      platform: Platform.OS,
      appOwnership: Constants.appOwnership,
      originalSizeBytes,
    });

    if (Constants.appOwnership === AppOwnership.Expo) {
      throw new Error(
        'Video compression requires a native iOS build. Rebuild the app with `npx expo run:ios` and try again.'
      );
    }

    if (Platform.OS === 'web') {
      throw new Error(
        `This video is over the ${UPLOAD_LIMIT_LABEL} upload limit, and compression is not available in this web environment. Use a smaller clip and try again.`
      );
    }

    throw new Error(
      `This video is over the ${UPLOAD_LIMIT_LABEL} upload limit. Trim the clip or record a shorter video and try again.`
    );
  }

  onStatusChange?.('Compressing for upload...');

  const targetBitrate = calculateTargetBitrate(asset, originalSizeBytes);
  const nativeVideoCompressor = getNativeVideoCompressor();
  let compressedUri: string;

  if (!nativeVideoCompressor) {
    throw new Error('Video compression is not available in this build. Rebuild the native iOS app and try again.');
  }

  logVideoUploadDebug('Starting video compression.', {
    originalSizeBytes,
    targetBitrate,
    targetMaxDimension: TARGET_MAX_DIMENSION,
    wasVeryLarge,
  });

  try {
    compressedUri = await nativeVideoCompressor.compress(asset.uri, {
      compressionMethod: 'manual',
      maxSize: TARGET_MAX_DIMENSION,
      bitrate: targetBitrate,
      minimumFileSizeForCompress: 0,
    });
  } catch (error) {
    logVideoUploadWarning('Compression failed before a compressed file was produced.', {
      originalSizeBytes,
      reason: error instanceof Error ? error.message : 'unknown_compression_error',
    });

    if (__DEV__) {
      console.warn('Video compression failed.', error);
    }

    throw new Error(
      wasVeryLarge
        ? 'Compression failed for this very large video. Trim the clip or record a shorter video and try again.'
        : 'Compression failed. Try another clip or record a shorter video.'
    );
  }

  const compressedAsset = buildCompressedAsset(asset, compressedUri);
  const compressedSizeBytes = await resolveAssetFileSize(compressedAsset);

  logVideoUploadDebug('Compression finished.', {
    compressedUri,
    compressedSizeBytes,
    originalSizeBytes,
  });

  if (compressedSizeBytes > MAX_UPLOAD_BYTES) {
    logVideoUploadWarning('Compressed file is still over the upload limit.', {
      compressedUri,
      compressedSizeBytes,
      maxUploadBytes: MAX_UPLOAD_BYTES,
      originalSizeBytes,
      wasVeryLarge,
      reason: 'compressed_file_still_too_large',
    });

    throw new Error(
      wasVeryLarge
        ? `Compressed video still exceeds the ${UPLOAD_LIMIT_LABEL} upload limit. This clip is very large, so trim it or record a shorter video and try again.`
        : `Compressed video still exceeds the ${UPLOAD_LIMIT_LABEL} upload limit. Trim the clip or record a shorter video and try again.`
    );
  }

  return {
    asset: compressedAsset,
    originalSizeBytes,
    finalSizeBytes: compressedSizeBytes,
    wasCompressed: true,
    wasVeryLarge,
  };
}

function createUuid() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }

  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const randomNibble = Math.floor(Math.random() * 16);
    const value = character === 'x' ? randomNibble : (randomNibble & 0x3) | 0x8;
    return value.toString(16);
  });
}

function formatSupabaseError(error: unknown) {
  const typedError = (error ?? {}) as SupabaseLikeError;
  const segments = [
    typedError.message,
    typedError.code ? `code=${typedError.code}` : null,
    typedError.details ? `details=${typedError.details}` : null,
    typedError.hint ? `hint=${typedError.hint}` : null,
  ].filter(Boolean);

  return segments.join(' | ') || 'Unknown Supabase error';
}

async function resolveUploadSource(asset: UploadableVideoAsset): Promise<UploadSource> {
  const webAsset = asset as UploadableVideoAsset & WebImagePickerAsset;
  const inferredFileName = inferFileName(asset);
  validateInitialVideoMetadata(asset);

  if (Platform.OS === 'web' && webAsset.file) {
    const fileName = webAsset.file.name || inferredFileName;
    const contentType =
      getExplicitAssetMimeType(asset) ?? webAsset.file.type ?? inferMimeTypeFromFilename(fileName);
    assertSupportedVideoFile(fileName, contentType);

    if (!contentType) {
      throw new Error('Unable to verify the selected video format.');
    }

    return {
      body: webAsset.file,
      contentType,
      fileName: buildUploadFileName(fileName, contentType),
      sizeBytes: webAsset.file.size,
    };
  }

  const sourceResponse = await fetch(asset.uri);

  if (!sourceResponse.ok) {
    throw new Error('Unable to read the selected video file.');
  }

  const videoBlob = await sourceResponse.blob();
  const contentType =
    getExplicitAssetMimeType(asset) ?? videoBlob.type ?? inferMimeTypeFromFilename(inferredFileName);
  assertSupportedVideoFile(inferredFileName, contentType);

  if (!contentType) {
    throw new Error('Unable to verify the selected video format.');
  }

  return {
    body: videoBlob,
    contentType,
    fileName: buildUploadFileName(inferredFileName, contentType),
    sizeBytes: videoBlob.size,
  };
}

export async function cleanupUploadedVideoForAnalysis({
  videoId,
  storagePath,
}: CleanupUploadedVideoForAnalysisArgs): Promise<void> {
  if (!supabase) {
    return;
  }

  let storageRemoved = false;

  const {
    data: { user },
    error: getUserError,
  } = await supabase.auth.getUser();
  const ownsStoragePath = Boolean(user?.id && storagePath.startsWith(`${user.id}/`));

  if (getUserError) {
    logVideoUploadWarning('Failed to verify current user before upload cleanup.', {
      videoId,
      storagePath,
      error: formatSupabaseError(getUserError),
    });
  } else if (!ownsStoragePath) {
    logVideoUploadWarning('Skipped storage cleanup because the path is outside the current user folder.', {
      videoId,
      storagePath,
      userId: user?.id ?? null,
    });
  } else {
    const { error: removeError } = await supabase.storage.from('videos').remove([storagePath]);

    if (removeError) {
      logVideoUploadWarning('Failed to remove uploaded video from storage during cleanup.', {
        videoId,
        storagePath,
        error: formatSupabaseError(removeError),
      });
    } else {
      storageRemoved = true;
    }
  }

  if (storageRemoved) {
    let deleteQuery = supabase.from('videos').delete().eq('id', videoId);

    if (user?.id) {
      deleteQuery = deleteQuery.eq('user_id', user.id);
    }

    const { error: deleteError } = await deleteQuery;

    if (!deleteError) {
      return;
    }

    logVideoUploadWarning('Failed to delete uploaded video row during cleanup.', {
      videoId,
      error: formatSupabaseError(deleteError),
    });
  }

  let updateQuery = supabase.from('videos').update({ status: 'failed' }).eq('id', videoId);

  if (user?.id) {
    updateQuery = updateQuery.eq('user_id', user.id);
  }

  const { error: updateError } = await updateQuery;

  if (updateError) {
    logVideoUploadWarning('Failed to mark uploaded video row as failed during cleanup.', {
      videoId,
      error: formatSupabaseError(updateError),
    });
  }
}

export async function uploadVideoForAnalysis({
  asset,
  exercise,
  angle,
  onStatusChange,
}: UploadVideoForAnalysisArgs): Promise<UploadVideoForAnalysisResult> {
  if (!supabase) {
    throw new Error(supabaseConfigError ?? 'Supabase is not configured.');
  }

  const {
    data: { user },
    error: getUserError,
  } = await supabase.auth.getUser();

  if (getUserError) {
    throw getUserError;
  }

  if (!user) {
    throw new Error('You must be logged in to upload and analyze a video.');
  }

  validateInitialVideoMetadata(asset);
  const preparedVideo = await prepareVideoForUpload(asset, onStatusChange);

  if (preparedVideo.finalSizeBytes > MAX_UPLOAD_BYTES) {
    logVideoUploadWarning('Upload flow stopped because the prepared file is still too large.', {
      originalSizeBytes: preparedVideo.originalSizeBytes,
      finalSizeBytes: preparedVideo.finalSizeBytes,
      reason: 'prepared_file_still_too_large',
    });

    throw new Error(
      `This video is still too large to upload. The limit is ${UPLOAD_LIMIT_LABEL}. Trim the clip or record a shorter video and try again.`
    );
  }

  onStatusChange?.('Uploading video...');

  const uploadSource = await resolveUploadSource(preparedVideo.asset);
  logVideoUploadDebug('Uploading prepared video file.', {
    originalSizeBytes: preparedVideo.originalSizeBytes,
    uploadedFileSizeBytes: uploadSource.sizeBytes,
    wasCompressed: preparedVideo.wasCompressed,
  });
  const storagePath = buildStoragePath(user.id, uploadSource.fileName);

  const { error: uploadError } = await supabase.storage.from('videos').upload(storagePath, uploadSource.body, {
    contentType: uploadSource.contentType,
    upsert: false,
  });

  if (uploadError) {
    throw uploadError;
  }

  const durationMs =
    typeof asset.duration === 'number' && !Number.isNaN(asset.duration)
      ? Math.round(asset.duration)
      : null;
  const videoId = createUuid();
  const normalizedExerciseType = normalizeExerciseType(exercise);
  const normalizedViewType = normalizeViewType(angle);

  const { error: insertError } = await supabase
    .from('videos')
    .insert({
      id: videoId,
      user_id: user.id,
      storage_path: storagePath,
      source_type: 'camera_roll',
      exercise_type: normalizedExerciseType,
      view_type: normalizedViewType,
      status: 'uploaded',
      duration_ms: durationMs,
    })
    ;

  if (insertError) {
    console.error('[Supabase] uploadVideoForAnalysis insert failed', {
      authUserId: user.id,
      insertedUserId: user.id,
      videoId,
      storagePath,
      exerciseType: normalizedExerciseType,
      viewType: normalizedViewType,
      error: {
        message: insertError.message,
        code: insertError.code,
        details: insertError.details,
        hint: insertError.hint,
      },
    });
    await supabase.storage.from('videos').remove([storagePath]);
    throw new Error(formatSupabaseError(insertError));
  }

  return {
    videoId,
    status: 'uploaded',
    storagePath,
    originalFileSizeBytes: preparedVideo.originalSizeBytes,
    uploadedFileSizeBytes: uploadSource.sizeBytes,
    wasCompressed: preparedVideo.wasCompressed,
  };
}
