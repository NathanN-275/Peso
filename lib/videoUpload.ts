import Constants, { AppOwnership } from 'expo-constants';
import type { ImagePickerAsset } from 'expo-image-picker';
import { Platform } from 'react-native';
import type { VideoCompressorType } from 'react-native-compressor';
import { CameraAngle, ExerciseOption } from '../src/constants/videoSetup';
import type { TrackingSetup } from '../src/types/trackingSetup';
import {
  cancelUploadReservation,
  completeUploadReservation,
  createUploadReservation,
  fetchVideoCapabilities,
  markVideoUploadFailed,
} from './backendApi';
import { getFreshBackendAccessToken } from './backendAuth';
import {
  shouldCheckPinTrackingCapability,
  verifyPinTrackingCapability,
} from './pinTrackingCapabilityPolicy';
import { supabase, supabaseConfigError } from './supabase';
import { normalizePositiveDurationMs } from './videoDurationPolicy';
import {
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  requiresQualityPreflight,
} from './qualityPreflightPolicy';
import { normalizeVideoUploadFileName } from './videoUploadPolicy';

const DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const MAX_UPLOAD_BYTES = resolveFrontendMaxUploadBytes();
const VERY_LARGE_VIDEO_BYTES = 200 * 1024 * 1024;
const TARGET_COMPRESSED_BYTES = Math.min(45 * 1024 * 1024, Math.floor(MAX_UPLOAD_BYTES * 0.9));
const TARGET_MAX_DIMENSION = 1280;
const MIN_POSE_BITRATE = 1_800_000;
const MAX_POSE_BITRATE = 2_500_000;
const AUDIO_BITRATE_RESERVE = 128_000;
const UPLOAD_LIMIT_LABEL = `${Math.round(MAX_UPLOAD_BYTES / (1024 * 1024))} MB`;
const ALLOWED_VIDEO_EXTENSIONS = ['.mp4', '.mov', '.m4v', '.webm'] as const;
const ALLOWED_VIDEO_MIME_TYPES = [
  'video/mp4',
  'video/quicktime',
  'video/x-m4v',
  'video/m4v',
  'video/webm',
] as const;

type UploadVideoForAnalysisArgs = {
  asset: ImagePickerAsset;
  exercise: ExerciseOption;
  angle: CameraAngle;
  sourceType?: 'camera' | 'camera_roll';
  trackingSetup?: TrackingSetup | null;
  durationMs?: number | null;
  onStatusChange?: (message: string | null) => void;
  onQuotaWarning?: (message: string) => void;
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

type CleanupUploadedVideoForAnalysisArgs = {
  videoId: string;
  storagePath: string;
};

let cachedNativeVideoCompressor: VideoCompressorType | null | undefined;

function resolveFrontendMaxUploadBytes() {
  // Let the frontend use a configurable upload cap when provided.
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
  // Upload logs stay structured for troubleshooting large clips.
  console.log('[VideoUpload]', message, details ?? {});
}

function logVideoUploadWarning(message: string, details?: Record<string, unknown>) {
  // Warnings explain why a clip was compressed or rejected.
  console.warn('[VideoUpload]', message, details ?? {});
}

function normalizeExerciseType(exercise: ExerciseOption) {
  // Store exercise names in a backend-friendly format.
  return exercise.trim().toLowerCase();
}

function normalizeViewType(angle: CameraAngle) {
  // Camera angles use the same normalization as exercises.
  return angle.trim().toLowerCase();
}

function inferFileName(asset: UploadableVideoAsset) {
  // Fall back to the URI tail when the picker omits a name.
  return asset.fileName ?? asset.uri.split('/').pop() ?? 'video-upload.mp4';
}

function getExplicitAssetMimeType(asset: UploadableVideoAsset) {
  // Some pickers provide the MIME type in different fields.
  if (asset.mimeType) {
    return asset.mimeType;
  }

  return asset.type?.includes('/') ? asset.type : null;
}

function getFileExtension(filename: string) {
  // Ignore query strings when checking the extension.
  const normalizedFilename = filename.split(/[?#]/)[0];
  const dotIndex = normalizedFilename.lastIndexOf('.');
  return dotIndex >= 0 ? normalizedFilename.slice(dotIndex).toLowerCase() : '';
}

function isAllowedVideoExtension(filename: string) {
  // Restrict uploads to the formats this pipeline supports.
  return ALLOWED_VIDEO_EXTENSIONS.includes(
    getFileExtension(filename) as (typeof ALLOWED_VIDEO_EXTENSIONS)[number]
  );
}

function hasFileExtension(filename: string) {
  // Some assets need MIME-type validation instead of extension validation.
  return Boolean(getFileExtension(filename));
}

function isAllowedVideoMimeType(mimeType?: string | null) {
  // Accept only the video types the backend can process.
  const normalizedMimeType = mimeType?.split(';')[0]?.trim().toLowerCase();

  return Boolean(
    normalizedMimeType &&
      ALLOWED_VIDEO_MIME_TYPES.includes(
        normalizedMimeType as (typeof ALLOWED_VIDEO_MIME_TYPES)[number]
      )
  );
}

function inferMimeTypeFromFilename(filename: string) {
  // Fill in a MIME type when the picker leaves it blank.
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

  if (extension === '.webm') {
    return 'video/webm';
  }

  return null;
}

function buildUploadFileName(filename: string, contentType: string) {
  // Storage policies validate the object name, so normalize picker metadata to
  // an extension that matches the MIME type actually sent to Storage.
  return normalizeVideoUploadFileName(filename, contentType);
}

function assertSupportedVideoFile(fileName: string, mimeType?: string | null) {
  // Reject formats the analysis backend cannot handle.
  const hasExtension = hasFileExtension(fileName);

  if (hasExtension && !isAllowedVideoExtension(fileName)) {
    throw new Error('Unsupported video file type. Choose an MP4, MOV, M4V, or WebM video.');
  }

  if (mimeType && !isAllowedVideoMimeType(mimeType)) {
    throw new Error('Unsupported video format. Choose an MP4, MOV, M4V, or WebM video.');
  }

  if (!hasExtension && !isAllowedVideoMimeType(mimeType)) {
    throw new Error('Unable to verify the selected video format. Choose an MP4, MOV, M4V, or WebM video.');
  }
}

function validateInitialVideoMetadata(asset: UploadableVideoAsset) {
  // Validate before compression so unsupported files fail early.
  const fileName = inferFileName(asset);
  const mimeType = getExplicitAssetMimeType(asset);

  if (hasFileExtension(fileName) || mimeType) {
    assertSupportedVideoFile(fileName, mimeType);
  }
}

function replaceFileExtension(filename: string, nextExtension: string) {
  // Compression can change the output container type.
  if (!filename.includes('.')) {
    return `${filename}${nextExtension}`;
  }

  return filename.replace(/\.[^/.]+$/, nextExtension);
}

function inferBitrateFromAsset(asset: ImagePickerAsset, fileSizeBytes: number) {
  // Estimate the original bitrate from size and duration.
  if (typeof asset.duration !== 'number' || Number.isNaN(asset.duration) || asset.duration <= 0) {
    return null;
  }

  return Math.floor((fileSizeBytes * 8) / (asset.duration / 1000));
}

function calculateTargetBitrate(asset: ImagePickerAsset, fileSizeBytes: number) {
  // Pick a bitrate that keeps pose detail while shrinking the file.
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
  // Read the file directly when picker metadata is missing.
  const response = await fetch(uri);

  if (!response.ok) {
    throw new Error('Unable to read the selected video file.');
  }

  const fileBlob = await response.blob();
  return fileBlob.size;
}

async function resolveAssetFileSize(asset: UploadableVideoAsset) {
  // Prefer picker metadata on web, then fall back to the file itself.
  if (Platform.OS === 'web' && typeof asset.fileSize === 'number' && !Number.isNaN(asset.fileSize)) {
    return asset.fileSize;
  }

  return resolveFileSizeFromUri(asset.uri);
}

function getNativeVideoCompressor() {
  // Native compression is only available outside web and Expo Go.
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
  // Compression output is normalized into an MP4 upload asset.
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
  // Compress only when the original file is over the upload cap.
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

async function resolveUploadSource(asset: UploadableVideoAsset): Promise<UploadSource> {
  // Convert the selected asset into the blob or file used by the reserved PUT.
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
}: CleanupUploadedVideoForAnalysisArgs): Promise<void> {
  // Remove partially processed uploads when analysis setup fails.
  if (!supabase) {
    return;
  }

  try {
    const accessToken = await getFreshBackendAccessToken();
    await markVideoUploadFailed(videoId, accessToken);
    return;
  } catch (error) {
    logVideoUploadWarning('Failed to mark uploaded video as failed through the backend.', {
      videoId,
      error: error instanceof Error ? error.message : String(error),
    });
  }

  // Cleanup is server-owned; expiry cleanup retries if this request cannot reach
  // the API. Clients never get storage deletion privileges.
}

export async function uploadVideoForAnalysis({
  asset,
  exercise,
  angle,
  sourceType = 'camera_roll',
  trackingSetup,
  durationMs,
  onStatusChange,
}: UploadVideoForAnalysisArgs): Promise<UploadVideoForAnalysisResult> {
  // Upload the video and create the DB row that analysis consumes.
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

  let accessToken: string | null = null;
  const sideSquatPreflightRequired = requiresQualityPreflight({ exercise, angle });

  if (shouldCheckPinTrackingCapability(trackingSetup)) {
    onStatusChange?.('Checking pin tracking support...');
    try {
      accessToken = await verifyPinTrackingCapability({
        trackingSetup,
        getAccessToken: getFreshBackendAccessToken,
        fetchCapabilities: fetchVideoCapabilities,
      });
    } catch (error) {
      logVideoUploadWarning('Unable to verify pin tracking support before upload.', {
        error: error instanceof Error ? error.message : String(error),
      });
      if (error instanceof Error && error.message.startsWith('Pin-assisted tracking')) {
        throw error;
      }
      throw new Error(
        'Unable to verify pin-assisted tracking support. Deploy the latest backend and tracking database migration, then try again.'
      );
    }
  }

  if (sideSquatPreflightRequired) {
    onStatusChange?.('Checking recording quality support...');
    try {
      accessToken ??= await getFreshBackendAccessToken();
      const capabilities = await fetchVideoCapabilities(accessToken);
      const supportedVersions = capabilities.quality_preflight_versions ?? [];
      if (
        capabilities.side_squat_quality_preflight !== true
        || !supportedVersions.includes(QUALITY_PREFLIGHT_THRESHOLD_VERSION)
      ) {
        throw new Error('Side-view squat quality preflight is unavailable.');
      }
    } catch (error) {
      logVideoUploadWarning('Unable to verify quality preflight support before upload.', {
        error: error instanceof Error ? error.message : String(error),
      });
      throw new Error(
        'Side-view squat quality checks are not ready on this backend. Deploy the latest backend and quality-preflight database migration, then try again.'
      );
    }
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

  const uploadSource = await resolveUploadSource(preparedVideo.asset);
  logVideoUploadDebug('Uploading prepared video file.', {
    fileName: uploadSource.fileName,
    contentType: uploadSource.contentType,
    originalSizeBytes: preparedVideo.originalSizeBytes,
    uploadedFileSizeBytes: uploadSource.sizeBytes,
    wasCompressed: preparedVideo.wasCompressed,
  });
  onStatusChange?.('Reserving upload capacity...');
  accessToken ??= await getFreshBackendAccessToken();

  const resolvedDurationMs =
    normalizePositiveDurationMs(durationMs)
    ?? normalizePositiveDurationMs(asset.duration);
  const normalizedExerciseType = normalizeExerciseType(exercise);
  const normalizedViewType = normalizeViewType(angle);

  const reservation = await createUploadReservation({
    file_name: uploadSource.fileName,
    content_type: uploadSource.contentType,
    size_bytes: uploadSource.sizeBytes,
    source_type: sourceType,
    exercise_type: normalizedExerciseType,
    view_type: normalizedViewType,
    duration_ms: resolvedDurationMs,
    ...(trackingSetup ? { tracking_setup: trackingSetup } : {}),
  }, accessToken);

  try {
    onStatusChange?.('Uploading video...');
    // One exact-blob, create-only SAS: no read/list/delete or overwrite access.
    // Do not log this URL or a fetch error object, which may contain its token.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180_000);
    let uploadResponse: Response;
    try {
      uploadResponse = await fetch(reservation.upload_url, {
        method: 'PUT',
        headers: reservation.upload_headers,
        body: uploadSource.body,
        signal: controller.signal,
        credentials: 'omit',
        redirect: 'error',
      });
    } catch {
      throw new Error('Private video upload could not complete. Check your connection and try again.');
    } finally {
      clearTimeout(timeout);
    }
    if (!uploadResponse.ok) {
      throw new Error('Private video upload failed or expired. Please try again.');
    }
    onStatusChange?.('Verifying video limits...');
    const registeredVideo = await completeUploadReservation(reservation.reservation_id, accessToken);
    logVideoUploadDebug('Video upload registration completed.', {
      videoId: registeredVideo.video_id,
      storagePath: registeredVideo.storage_path,
    });
    return {
      videoId: registeredVideo.video_id,
      status: 'uploaded',
      storagePath: registeredVideo.storage_path,
      originalFileSizeBytes: preparedVideo.originalSizeBytes,
      uploadedFileSizeBytes: registeredVideo.uploaded_size_bytes,
      wasCompressed: preparedVideo.wasCompressed,
    };
  } catch (error) {
    try {
      await cancelUploadReservation(reservation.reservation_id, accessToken);
    } catch {
      // A completed reservation is idempotent; expired unverified uploads are
      // removed by the scheduled cleanup job if cancellation cannot complete.
    }
    throw error;
  }
}
