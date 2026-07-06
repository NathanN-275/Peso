import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type * as ImagePicker from 'expo-image-picker';
import {
  ActivityIndicator,
  Image,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { VideoSetupSelection } from '../constants/videoSetup';
import tokens from '../theme/tokens';

type WebVideoRecorderScreenProps = {
  setup?: VideoSetupSelection | null;
  setupResumeKey?: number;
  onBack?: () => void;
  onEditSetup?: () => void;
  onUseRecording?: (asset: ImagePicker.ImagePickerAsset) => void;
};

type RecorderPhase = 'initializing' | 'ready' | 'recording' | 'review' | 'exporting';
type TrimHandle = 'start' | 'end';

type TrimmedVideoResult = {
  file: File;
  uri: string;
  durationMs: number;
};

type TrimThumbnail = {
  id: string;
  uri: string;
  time: number;
};

const MIN_TRIM_SECONDS = 0.5;
const RECORDING_FRAME_RATE = 30;
const THUMBNAIL_COUNT = 10;
const RECORDING_MIME_TYPES = [
  'video/mp4;codecs=avc1.42E01E',
  'video/mp4',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
  'video/webm',
];

function formatDuration(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function formatSeconds(value: number) {
  return `${value.toFixed(1)}s`;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum);
}

function getTimeFromTrackX(x: number, width: number, durationSeconds: number) {
  if (width <= 0 || durationSeconds <= 0) {
    return 0;
  }

  return clamp((x / width) * durationSeconds, 0, durationSeconds);
}

function getBaseMimeType(value?: string | null) {
  return value?.split(';')[0]?.trim().toLowerCase() || 'video/webm';
}

function getRecordingExtension(mimeType: string) {
  return getBaseMimeType(mimeType) === 'video/mp4' ? 'mp4' : 'webm';
}

function getSupportedRecordingMimeType() {
  if (typeof MediaRecorder === 'undefined') {
    return null;
  }

  return RECORDING_MIME_TYPES.find((mimeType) => MediaRecorder.isTypeSupported(mimeType)) ?? '';
}

function buildRecordingFile(blob: Blob, startedAt: number) {
  const mimeType = getBaseMimeType(blob.type);
  const extension = getRecordingExtension(mimeType);
  return new File([blob], `peso-recording-${startedAt}.${extension}`, { type: mimeType });
}

function waitForMediaEvent(target: HTMLMediaElement, eventName: string) {
  return new Promise<void>((resolve, reject) => {
    const cleanup = () => {
      target.removeEventListener(eventName, handleEvent);
      target.removeEventListener('error', handleError);
    };
    const handleEvent = () => {
      cleanup();
      resolve();
    };
    const handleError = () => {
      cleanup();
      reject(new Error('Unable to load recorded video.'));
    };

    target.addEventListener(eventName, handleEvent, { once: true });
    target.addEventListener('error', handleError, { once: true });
  });
}

async function waitForMetadata(video: HTMLVideoElement) {
  if (Number.isFinite(video.duration) && video.duration > 0) {
    return;
  }

  await waitForMediaEvent(video, 'loadedmetadata');
}

async function seekVideo(video: HTMLVideoElement, timeSeconds: number) {
  if (Math.abs(video.currentTime - timeSeconds) < 0.04) {
    return;
  }

  const seeked = waitForMediaEvent(video, 'seeked');
  video.currentTime = timeSeconds;
  await seeked;
}

async function generateTrimThumbnails(sourceUri: string, durationSeconds: number) {
  const video = document.createElement('video');
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');

  if (!context) {
    throw new Error('Unable to build video thumbnails.');
  }

  canvas.width = 90;
  canvas.height = 120;
  video.src = sourceUri;
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';

  await waitForMetadata(video);

  const resolvedDuration = Number.isFinite(video.duration) && video.duration > 0
    ? video.duration
    : durationSeconds;
  const count = Math.max(1, THUMBNAIL_COUNT);
  const thumbnails: TrimThumbnail[] = [];

  for (let index = 0; index < count; index += 1) {
    const progress = count === 1 ? 0 : index / (count - 1);
    const time = clamp(progress * resolvedDuration, 0, Math.max(resolvedDuration - 0.05, 0));

    await seekVideo(video, time);
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    thumbnails.push({
      id: `${index}-${time.toFixed(2)}`,
      time,
      uri: canvas.toDataURL('image/jpeg', 0.76),
    });
  }

  return thumbnails;
}

async function exportTrimmedVideo({
  durationSeconds,
  file,
  height,
  sourceUri,
  trimEnd,
  trimStart,
  width,
}: {
  durationSeconds: number;
  file: File;
  height: number;
  sourceUri: string;
  trimEnd: number;
  trimStart: number;
  width: number;
}): Promise<TrimmedVideoResult> {
  const selectedStart = clamp(trimStart, 0, Math.max(durationSeconds - MIN_TRIM_SECONDS, 0));
  const selectedEnd = clamp(trimEnd, selectedStart + MIN_TRIM_SECONDS, durationSeconds);
  const usesFullRecording = selectedStart <= 0.05 && selectedEnd >= durationSeconds - 0.05;

  if (usesFullRecording) {
    return {
      file,
      uri: sourceUri,
      durationMs: Math.round(durationSeconds * 1000),
    };
  }

  const canvas = document.createElement('canvas');
  const captureStream = (
    canvas as HTMLCanvasElement & { captureStream?: (frameRate?: number) => MediaStream }
  ).captureStream;

  if (!captureStream || typeof MediaRecorder === 'undefined') {
    throw new Error('This browser cannot export trimmed camera recordings. Use the full range or test on another browser.');
  }

  const video = document.createElement('video');
  const canvasWidth = Math.max(width, 1);
  const canvasHeight = Math.max(height, 1);
  const context = canvas.getContext('2d');

  if (!context) {
    throw new Error('Unable to prepare trimmed video export.');
  }

  canvas.width = canvasWidth;
  canvas.height = canvasHeight;
  video.src = sourceUri;
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';

  await waitForMetadata(video);
  await seekVideo(video, selectedStart);

  const stream = captureStream.call(canvas, RECORDING_FRAME_RATE);
  const mimeType = getSupportedRecordingMimeType();
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: Blob[] = [];
  let animationFrameId: number | null = null;

  const stopped = new Promise<Blob>((resolve, reject) => {
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunks.push(event.data);
      }
    };
    recorder.onerror = () => {
      reject(new Error('Unable to export the selected trim.'));
    };
    recorder.onstop = () => {
      const outputType = getBaseMimeType(recorder.mimeType || mimeType || file.type);
      resolve(new Blob(chunks, { type: outputType }));
    };
  });

  const stopExport = () => {
    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }

    video.pause();
    stream.getTracks().forEach((track) => track.stop());

    if (recorder.state !== 'inactive') {
      recorder.stop();
    }
  };

  const drawFrame = () => {
    context.drawImage(video, 0, 0, canvasWidth, canvasHeight);

    if (video.currentTime >= selectedEnd || video.ended) {
      stopExport();
      return;
    }

    animationFrameId = requestAnimationFrame(drawFrame);
  };

  recorder.start(250);
  await video.play();
  drawFrame();

  const trimmedBlob = await stopped;

  if (trimmedBlob.size <= 0) {
    throw new Error('The selected trim did not produce a video file.');
  }

  const trimmedFile = buildRecordingFile(trimmedBlob, Date.now());

  return {
    file: trimmedFile,
    uri: URL.createObjectURL(trimmedFile),
    durationMs: Math.round((selectedEnd - selectedStart) * 1000),
  };
}

function PhotosTrimSelector({
  currentTime,
  durationSeconds,
  onPreviewTime,
  onTrimChange,
  setupLabel,
  thumbnails,
  trimEnd,
  trimStart,
}: {
  currentTime: number;
  durationSeconds: number;
  onPreviewTime: (time: number) => void;
  onTrimChange: (start: number, end: number) => void;
  setupLabel: string;
  thumbnails: TrimThumbnail[];
  trimEnd: number;
  trimStart: number;
}) {
  const [trackWidth, setTrackWidth] = useState(0);
  const [activeHandle, setActiveHandle] = useState<TrimHandle | null>(null);
  const safeDuration = Math.max(durationSeconds, MIN_TRIM_SECONDS);
  const startProgress = clamp(trimStart / safeDuration, 0, 1);
  const endProgress = clamp(trimEnd / safeDuration, 0, 1);
  const playheadProgress = clamp(currentTime / safeDuration, 0, 1);

  const updateHandleFromX = useCallback((handle: TrimHandle, x: number) => {
    const time = getTimeFromTrackX(x, trackWidth, safeDuration);

    if (handle === 'start') {
      const nextStart = clamp(time, 0, Math.max(trimEnd - MIN_TRIM_SECONDS, 0));
      onTrimChange(nextStart, trimEnd);
      onPreviewTime(nextStart);
      return;
    }

    const nextEnd = clamp(time, trimStart + MIN_TRIM_SECONDS, safeDuration);
    onTrimChange(trimStart, nextEnd);
    onPreviewTime(nextEnd);
  }, [onPreviewTime, onTrimChange, safeDuration, trackWidth, trimEnd, trimStart]);

  const handleResponderStart = useCallback((locationX: number) => {
    const startX = startProgress * trackWidth;
    const endX = endProgress * trackWidth;
    const nextHandle = Math.abs(locationX - startX) <= Math.abs(locationX - endX) ? 'start' : 'end';

    setActiveHandle(nextHandle);
    updateHandleFromX(nextHandle, locationX);
  }, [endProgress, startProgress, trackWidth, updateHandleFromX]);

  const handleResponderMove = useCallback((locationX: number) => {
    if (!activeHandle) {
      return;
    }

    updateHandleFromX(activeHandle, locationX);
  }, [activeHandle, updateHandleFromX]);

  return (
    <View style={styles.trimPanel}>
      <Text numberOfLines={1} style={styles.reviewSetupLabel}>{setupLabel}</Text>
      <View style={styles.trimHeader}>
        <Text style={styles.trimTitle}>Trim</Text>
        <Text style={styles.trimRange}>
          {formatSeconds(trimStart)} - {formatSeconds(trimEnd)}
        </Text>
      </View>

      <View style={styles.filmstripShell}>
        <View
          accessibilityRole="adjustable"
          style={styles.filmstripTrack}
          onLayout={({ nativeEvent }: LayoutChangeEvent) => setTrackWidth(nativeEvent.layout.width)}
          onStartShouldSetResponder={() => true}
          onMoveShouldSetResponder={() => true}
          onResponderGrant={(event) => handleResponderStart(event.nativeEvent.locationX)}
          onResponderMove={(event) => handleResponderMove(event.nativeEvent.locationX)}
          onResponderRelease={() => setActiveHandle(null)}
          onResponderTerminate={() => setActiveHandle(null)}
          onResponderTerminationRequest={() => false}
        >
          <View pointerEvents="none" style={styles.thumbnailRow}>
            {thumbnails.length > 0 ? (
              thumbnails.map((thumbnail) => (
                <Image
                  key={thumbnail.id}
                  source={{ uri: thumbnail.uri }}
                  style={styles.thumbnailFrame}
                />
              ))
            ) : (
              Array.from({ length: THUMBNAIL_COUNT }).map((_, index) => (
                <View key={index} style={styles.thumbnailPlaceholder} />
              ))
            )}
          </View>
          <View
            pointerEvents="none"
            style={[
              styles.unselectedMask,
              { left: 0, width: `${startProgress * 100}%` },
            ]}
          />
          <View
            pointerEvents="none"
            style={[
              styles.unselectedMask,
              { left: `${endProgress * 100}%`, right: 0 },
            ]}
          />
          <View
            pointerEvents="none"
            style={[
              styles.selectedTrimRange,
              {
                left: `${startProgress * 100}%`,
                width: `${Math.max((endProgress - startProgress) * 100, 0)}%`,
              },
            ]}
          />
          <View
            pointerEvents="none"
            style={[
              styles.trimHandle,
              styles.trimHandleLeft,
              { left: `${startProgress * 100}%` },
            ]}
          >
            <Text style={styles.trimHandleText}>‹</Text>
          </View>
          <View
            pointerEvents="none"
            style={[
              styles.trimHandle,
              styles.trimHandleRight,
              { left: `${endProgress * 100}%` },
            ]}
          >
            <Text style={styles.trimHandleText}>›</Text>
          </View>
          <View
            pointerEvents="none"
            style={[
              styles.playhead,
              { left: `${playheadProgress * 100}%` },
            ]}
          />
        </View>
      </View>
    </View>
  );
}

export default function WebVideoRecorderScreen({
  setup,
  setupResumeKey = 0,
  onBack,
  onEditSetup,
  onUseRecording,
}: WebVideoRecorderScreenProps) {
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);
  const playbackVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const handedOffUrlRef = useRef<string | null>(null);
  const [phase, setPhase] = useState<RecorderPhase>('initializing');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [recordedFile, setRecordedFile] = useState<File | null>(null);
  const [recordedUri, setRecordedUri] = useState<string | null>(null);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [videoSize, setVideoSize] = useState({ width: 0, height: 0 });
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState(0);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [trimThumbnails, setTrimThumbnails] = useState<TrimThumbnail[]>([]);

  const stopElapsedTimer = useCallback(() => {
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }, []);

  const stopCameraTracks = useCallback(() => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;

    if (previewVideoRef.current) {
      previewVideoRef.current.srcObject = null;
    }
  }, []);

  const revokeRecordingUrl = useCallback(() => {
    if (objectUrlRef.current && objectUrlRef.current !== handedOffUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
    }

    objectUrlRef.current = null;
  }, []);

  const startCamera = useCallback(async () => {
    setErrorMessage(null);
    setPhase('initializing');

    if (!window.isSecureContext) {
      setErrorMessage('Camera access requires localhost or HTTPS.');
      setPhase('ready');
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setErrorMessage('This browser does not support camera recording.');
      setPhase('ready');
      return;
    }

    const mimeType = getSupportedRecordingMimeType();

    if (mimeType === null) {
      setErrorMessage('This browser does not support camera recording.');
      setPhase('ready');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: 'environment' },
          height: { ideal: 720 },
          width: { ideal: 1280 },
        },
      });

      cameraStreamRef.current = stream;

      if (previewVideoRef.current) {
        previewVideoRef.current.srcObject = stream;
        await previewVideoRef.current.play();
      }

      setPhase('ready');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to access the camera.');
      setPhase('ready');
      stopCameraTracks();
    }
  }, [stopCameraTracks]);

  useEffect(() => {
    void startCamera();

    return () => {
      stopElapsedTimer();

      if (recorderRef.current?.state === 'recording') {
        recorderRef.current.stop();
      }

      stopCameraTracks();
      revokeRecordingUrl();
    };
  }, [revokeRecordingUrl, startCamera, stopCameraTracks, stopElapsedTimer]);

  useEffect(() => {
    if (setupResumeKey <= 0 || recordedFile || phase === 'recording' || cameraStreamRef.current) {
      return;
    }

    void startCamera();
  }, [phase, recordedFile, setupResumeKey, startCamera]);

  useEffect(() => {
    let active = true;

    if (!recordedUri || phase !== 'review') {
      setTrimThumbnails([]);
      return () => {
        active = false;
      };
    }

    void generateTrimThumbnails(recordedUri, durationSeconds)
      .then((thumbnails) => {
        if (active) {
          setTrimThumbnails(thumbnails);
        }
      })
      .catch(() => {
        if (active) {
          setTrimThumbnails([]);
        }
      });

    return () => {
      active = false;
    };
  }, [durationSeconds, phase, recordedUri]);

  const stopRecording = useCallback(() => {
    stopElapsedTimer();

    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.stop();
    }
  }, [stopElapsedTimer]);

  const startRecording = useCallback(() => {
    const stream = cameraStreamRef.current;
    const mimeType = getSupportedRecordingMimeType();

    if (!stream || mimeType === null) {
      setErrorMessage('Camera is not ready.');
      return;
    }

    try {
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const startedAt = Date.now();

      recordingChunksRef.current = [];
      recorderRef.current = recorder;
      revokeRecordingUrl();
      setRecordedFile(null);
      setRecordedUri(null);
      setTrimThumbnails([]);
      setElapsedMs(0);
      setPlaybackTime(0);
      setErrorMessage(null);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordingChunksRef.current.push(event.data);
        }
      };
      recorder.onerror = () => {
        stopElapsedTimer();
        setErrorMessage('Recording failed. Try again.');
        setPhase('ready');
      };
      recorder.onstop = () => {
        stopElapsedTimer();

        const recordedMimeType = getBaseMimeType(recorder.mimeType || mimeType || 'video/webm');
        const blob = new Blob(recordingChunksRef.current, { type: recordedMimeType });

        if (blob.size <= 0) {
          setErrorMessage('No video data was recorded. Try again.');
          setPhase('ready');
          return;
        }

        const file = buildRecordingFile(blob, startedAt);
        const uri = URL.createObjectURL(file);
        const recordedDurationSeconds = Math.max((Date.now() - startedAt) / 1000, MIN_TRIM_SECONDS);
        const previewWidth = previewVideoRef.current?.videoWidth ?? 0;
        const previewHeight = previewVideoRef.current?.videoHeight ?? 0;

        objectUrlRef.current = uri;
        setRecordedFile(file);
        setRecordedUri(uri);
        setDurationSeconds(recordedDurationSeconds);
        setTrimStart(0);
        setTrimEnd(recordedDurationSeconds);
        setPlaybackTime(0);
        setVideoSize({ width: previewWidth, height: previewHeight });
        setElapsedMs(Math.round(recordedDurationSeconds * 1000));
        stopCameraTracks();
        setPhase('review');
      };

      recorder.start(250);
      setPhase('recording');
      elapsedTimerRef.current = setInterval(() => {
        setElapsedMs(Date.now() - startedAt);
      }, 250);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to start recording.');
      setPhase('ready');
    }
  }, [revokeRecordingUrl, stopCameraTracks, stopElapsedTimer]);

  const recordAgain = () => {
    stopElapsedTimer();
    revokeRecordingUrl();
    setRecordedFile(null);
    setRecordedUri(null);
    setTrimThumbnails([]);
    setDurationSeconds(0);
    setTrimStart(0);
    setTrimEnd(0);
    setPlaybackTime(0);
    setElapsedMs(0);
    void startCamera();
  };

  const cancelRecording = () => {
    stopElapsedTimer();
    stopCameraTracks();
    playbackVideoRef.current?.pause();
    onBack?.();
  };

  const editSetup = () => {
    if (phase === 'recording') {
      return;
    }

    stopElapsedTimer();
    stopCameraTracks();
    playbackVideoRef.current?.pause();
    onEditSetup?.();
  };

  const previewTrimTime = (time: number) => {
    setPlaybackTime(time);

    if (playbackVideoRef.current) {
      playbackVideoRef.current.currentTime = time;
    }
  };

  const updateTrimRange = (start: number, end: number) => {
    setTrimStart(start);
    setTrimEnd(end);
  };

  const handlePlaybackMetadata = () => {
    const video = playbackVideoRef.current;

    if (!video || !Number.isFinite(video.duration) || video.duration <= 0) {
      return;
    }

    const nextDuration = video.duration;

    setDurationSeconds(nextDuration);
    setTrimEnd((currentEnd) => (
      currentEnd <= 0 || Math.abs(currentEnd - durationSeconds) < 0.75
        ? nextDuration
        : clamp(currentEnd, MIN_TRIM_SECONDS, nextDuration)
    ));
  };

  const useRecording = async () => {
    if (!recordedFile || !recordedUri || phase === 'exporting') {
      return;
    }

    setPhase('exporting');
    setErrorMessage(null);

    try {
      const result = await exportTrimmedVideo({
        durationSeconds,
        file: recordedFile,
        height: videoSize.height,
        sourceUri: recordedUri,
        trimEnd,
        trimStart,
        width: videoSize.width,
      });
      handedOffUrlRef.current = result.uri;

      onUseRecording?.({
        uri: result.uri,
        width: videoSize.width,
        height: videoSize.height,
        type: 'video',
        fileName: result.file.name,
        fileSize: result.file.size,
        duration: result.durationMs,
        mimeType: result.file.type,
        file: result.file,
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to prepare the recording.');
      setPhase('review');
    }
  };

  const setupLabel = useMemo(() => {
    if (!setup) {
      return 'Setup selected';
    }

    return `${setup.exercise} • ${setup.angle}`;
  }, [setup]);
  const canRecord = phase === 'ready' && !errorMessage;
  const canRetryCamera = phase === 'ready' && Boolean(errorMessage);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.screen}>
        <View style={styles.headerRow}>
          <Pressable onPress={cancelRecording} style={styles.backButton}>
            <Text style={styles.backButtonText}>Back</Text>
          </Pressable>
          <Text numberOfLines={1} adjustsFontSizeToFit style={styles.title}>
            Record Video
          </Text>
          <View style={styles.headerSpacer} />
        </View>

        <View style={styles.previewArea}>
          {phase === 'review' || phase === 'exporting' ? (
            recordedUri ? (
              React.createElement('video', {
                ref: playbackVideoRef,
                src: recordedUri,
                controls: false,
                playsInline: true,
                onLoadedMetadata: handlePlaybackMetadata,
                onTimeUpdate: (event: React.SyntheticEvent<HTMLVideoElement>) => {
                  setPlaybackTime(event.currentTarget.currentTime);
                },
                style: styles.browserVideo,
              })
            ) : null
          ) : (
            React.createElement('video', {
              ref: previewVideoRef,
              autoPlay: true,
              muted: true,
              playsInline: true,
              style: styles.browserVideo,
            })
          )}

          {phase === 'initializing' ? (
            <View style={styles.videoOverlay}>
              <ActivityIndicator color={tokens.colors.textPrimary} />
              <Text style={styles.overlayText}>Opening camera...</Text>
            </View>
          ) : null}

          {phase === 'recording' ? (
            <View style={styles.recordingPill}>
              <View style={styles.recordingDot} />
              <Text style={styles.recordingText}>{formatDuration(elapsedMs)}</Text>
            </View>
          ) : null}

          {phase === 'review' || phase === 'exporting' ? null : (
            <View style={styles.setupPill}>
              <Text numberOfLines={1} style={styles.setupPillText}>{setupLabel}</Text>
            </View>
          )}
        </View>

        {errorMessage ? (
          <View style={styles.messageBlock}>
            <Text style={styles.errorText} selectable>{errorMessage}</Text>
          </View>
        ) : null}

        {phase === 'review' || phase === 'exporting' ? (
          <PhotosTrimSelector
            currentTime={playbackTime}
            durationSeconds={durationSeconds}
            onPreviewTime={previewTrimTime}
            onTrimChange={updateTrimRange}
            setupLabel={setupLabel}
            thumbnails={trimThumbnails}
            trimEnd={trimEnd}
            trimStart={trimStart}
          />
        ) : null}

        <View style={styles.bottomBar}>
          {phase === 'review' || phase === 'exporting' ? (
            <>
              <Pressable
                onPress={recordAgain}
                disabled={phase === 'exporting'}
                style={[styles.secondaryBarButton, phase === 'exporting' && styles.disabledButton]}
              >
                <Text style={styles.secondaryBarButtonText}>Record Again</Text>
              </Pressable>
              <Pressable
                onPress={useRecording}
                disabled={phase === 'exporting'}
                style={[styles.useButton, phase === 'exporting' && styles.disabledButton]}
              >
                <Text style={styles.useButtonText}>
                  {phase === 'exporting' ? 'Preparing...' : 'Use Recording'}
                </Text>
              </Pressable>
            </>
          ) : (
            <>
              <Pressable
                onPress={editSetup}
                disabled={phase === 'recording'}
                style={[styles.editSetupButton, phase === 'recording' && styles.disabledButton]}
              >
                <Text style={styles.editSetupText}>Edit Setup</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={phase === 'recording' ? 'Stop Recording' : 'Start Recording'}
                onPress={phase === 'recording' ? stopRecording : canRetryCamera ? () => void startCamera() : startRecording}
                disabled={phase === 'initializing' || (!canRecord && !canRetryCamera && phase !== 'recording')}
                style={[
                  styles.shutterButton,
                  phase === 'recording' && styles.shutterButtonRecording,
                  phase === 'initializing' && styles.disabledButton,
                ]}
              >
                <View style={[
                  styles.shutterInner,
                  phase === 'recording' && styles.shutterInnerRecording,
                ]} />
              </Pressable>
              <View style={styles.bottomSpacer}>
                {canRetryCamera ? (
                  <Text style={styles.bottomHint}>Try Again</Text>
                ) : null}
              </View>
            </>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  screen: {
    flex: 1,
    backgroundColor: '#000',
  },
  headerRow: {
    minHeight: 58,
    paddingHorizontal: 12,
    paddingTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  backButton: {
    width: 58,
    minHeight: 34,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#111827',
    borderWidth: 1,
    borderColor: '#22304A',
  },
  backButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
  },
  title: {
    flex: 1,
    color: tokens.colors.brand,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: '900',
    textAlign: 'center',
  },
  headerSpacer: {
    width: 58,
  },
  previewArea: {
    flex: 1,
    marginHorizontal: 0,
    backgroundColor: '#050505',
    overflow: 'hidden',
    position: 'relative',
  },
  browserVideo: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
    backgroundColor: '#000',
  },
  videoOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: 'rgba(0, 0, 0, 0.56)',
  },
  overlayText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  setupPill: {
    position: 'absolute',
    left: 16,
    right: 16,
    bottom: 14,
    minHeight: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
    backgroundColor: 'rgba(0, 0, 0, 0.58)',
  },
  setupPillText: {
    color: tokens.colors.textPrimary,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
  },
  messageBlock: {
    marginHorizontal: 16,
    marginTop: 12,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#5C2730',
    backgroundColor: '#1B0E12',
    padding: 10,
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  recordingPill: {
    position: 'absolute',
    top: 14,
    alignSelf: 'center',
    minHeight: 34,
    borderRadius: 17,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: 'rgba(0, 0, 0, 0.66)',
  },
  recordingDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: '#FF2D38',
  },
  recordingText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 19,
    fontWeight: '900',
    fontVariant: ['tabular-nums'],
  },
  trimPanel: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 2,
    gap: 8,
    backgroundColor: '#000',
  },
  reviewSetupLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '900',
    textAlign: 'center',
  },
  trimHeader: {
    minHeight: 24,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  trimTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '900',
  },
  trimRange: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    fontVariant: ['tabular-nums'],
  },
  filmstripShell: {
    minHeight: 72,
    borderRadius: 8,
    backgroundColor: '#6E6E73',
    padding: 6,
    overflow: 'hidden',
  },
  filmstripTrack: {
    flex: 1,
    minHeight: 60,
    borderRadius: 6,
    overflow: 'hidden',
    position: 'relative',
    backgroundColor: '#3A3A3C',
  },
  thumbnailRow: {
    ...StyleSheet.absoluteFillObject,
    flexDirection: 'row',
  },
  thumbnailFrame: {
    flex: 1,
    height: '100%',
    resizeMode: 'cover',
  },
  thumbnailPlaceholder: {
    flex: 1,
    height: '100%',
    backgroundColor: '#28282A',
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: '#555',
  },
  unselectedMask: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.48)',
  },
  selectedTrimRange: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    borderTopWidth: 6,
    borderBottomWidth: 6,
    borderColor: '#FFD60A',
    backgroundColor: 'rgba(255, 214, 10, 0.06)',
  },
  trimHandle: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    width: 34,
    marginLeft: -17,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFD60A',
  },
  trimHandleLeft: {
    borderTopLeftRadius: 8,
    borderBottomLeftRadius: 8,
  },
  trimHandleRight: {
    borderTopRightRadius: 8,
    borderBottomRightRadius: 8,
  },
  trimHandleText: {
    color: '#050505',
    fontSize: 46,
    lineHeight: 48,
    fontWeight: '900',
  },
  playhead: {
    position: 'absolute',
    top: -2,
    bottom: -2,
    width: 4,
    marginLeft: -2,
    borderRadius: 2,
    backgroundColor: '#FFFFFF',
    shadowColor: '#000',
    shadowOpacity: 0.4,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 1 },
  },
  bottomBar: {
    minHeight: 126,
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 24,
    backgroundColor: '#000',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 14,
  },
  editSetupButton: {
    width: 92,
    minHeight: 44,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  editSetupText: {
    color: tokens.colors.textPrimary,
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
    textAlign: 'center',
  },
  shutterButton: {
    width: 78,
    height: 78,
    borderRadius: 39,
    borderWidth: 5,
    borderColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterButtonRecording: {
    borderColor: '#FFFFFF',
  },
  shutterInner: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: '#FF2D38',
  },
  shutterInnerRecording: {
    width: 30,
    height: 30,
    borderRadius: 7,
  },
  bottomSpacer: {
    width: 92,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bottomHint: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    textAlign: 'center',
  },
  secondaryBarButton: {
    flex: 1,
    minHeight: 52,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#151922',
    borderWidth: 1,
    borderColor: '#273247',
    paddingHorizontal: 12,
  },
  secondaryBarButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '800',
    textAlign: 'center',
  },
  useButton: {
    flex: 1,
    minHeight: 52,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: tokens.colors.brand,
    paddingHorizontal: 12,
  },
  useButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '900',
    textAlign: 'center',
  },
  disabledButton: {
    opacity: 0.45,
  },
});
