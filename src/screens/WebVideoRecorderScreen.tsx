import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type * as ImagePicker from 'expo-image-picker';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Button from '../components/Button';
import tokens from '../theme/tokens';

type WebVideoRecorderScreenProps = {
  onBack?: () => void;
  onUseRecording?: (asset: ImagePicker.ImagePickerAsset) => void;
};

type RecorderPhase = 'initializing' | 'ready' | 'recording' | 'review' | 'exporting';

type TrimmedVideoResult = {
  file: File;
  uri: string;
  durationMs: number;
};

const MIN_TRIM_SECONDS = 0.5;
const TRIM_STEP_SECONDS = 0.5;
const RECORDING_FRAME_RATE = 30;
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

async function seekVideo(video: HTMLVideoElement, timeSeconds: number) {
  if (Math.abs(video.currentTime - timeSeconds) < 0.04) {
    return;
  }

  const seeked = waitForMediaEvent(video, 'seeked');
  video.currentTime = timeSeconds;
  await seeked;
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

  await waitForMediaEvent(video, 'loadedmetadata');
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

export default function WebVideoRecorderScreen({
  onBack,
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
      setElapsedMs(0);
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
    setDurationSeconds(0);
    setTrimStart(0);
    setTrimEnd(0);
    setElapsedMs(0);
    void startCamera();
  };

  const cancelRecording = () => {
    stopElapsedTimer();
    stopCameraTracks();
    onBack?.();
  };

  const setTrimFromPlayback = (edge: 'start' | 'end') => {
    const currentTime = playbackVideoRef.current?.currentTime ?? 0;

    if (edge === 'start') {
      setTrimStart(clamp(currentTime, 0, Math.max(trimEnd - MIN_TRIM_SECONDS, 0)));
      return;
    }

    setTrimEnd(clamp(currentTime, trimStart + MIN_TRIM_SECONDS, durationSeconds));
  };

  const adjustTrimStart = (amount: number) => {
    setTrimStart((currentValue) =>
      clamp(currentValue + amount, 0, Math.max(trimEnd - MIN_TRIM_SECONDS, 0))
    );
  };

  const adjustTrimEnd = (amount: number) => {
    setTrimEnd((currentValue) =>
      clamp(currentValue + amount, trimStart + MIN_TRIM_SECONDS, durationSeconds)
    );
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

  const recordingRangeLabel = useMemo(
    () => `${formatSeconds(trimStart)} - ${formatSeconds(trimEnd)}`,
    [trimEnd, trimStart]
  );
  const readyActionLabel = errorMessage ? 'Try Camera Again' : 'Start Recording';
  const handleReadyAction = errorMessage ? () => void startCamera() : startRecording;

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <View style={styles.headerRow}>
          <Button label="Back" onPress={cancelRecording} variant="secondary" style={styles.headerButton} />
          <Text style={styles.title}>Record Video</Text>
          <View style={styles.headerButton} />
        </View>

        <View style={styles.videoFrame}>
          {phase === 'review' || phase === 'exporting' ? (
            recordedUri ? (
              React.createElement('video', {
                ref: playbackVideoRef,
                src: recordedUri,
                controls: true,
                playsInline: true,
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
              <ActivityIndicator color={tokens.colors.brand} />
              <Text style={styles.overlayText}>Opening camera...</Text>
            </View>
          ) : null}
        </View>

        {errorMessage ? (
          <View style={styles.messageBlock}>
            <Text style={styles.errorText} selectable>{errorMessage}</Text>
          </View>
        ) : null}

        {phase === 'recording' ? (
          <View style={styles.recordingStatus}>
            <View style={styles.recordingDot} />
            <Text style={styles.recordingText}>{formatDuration(elapsedMs)}</Text>
          </View>
        ) : null}

        {phase === 'review' || phase === 'exporting' ? (
          <View style={styles.trimSection}>
            <Text style={styles.sectionTitle}>Trim</Text>
            <Text style={styles.rangeText}>{recordingRangeLabel}</Text>

            <View style={styles.trimGrid}>
              <View style={styles.trimGroup}>
                <Text style={styles.trimLabel}>Start</Text>
                <View style={styles.stepperRow}>
                  <Pressable style={styles.stepperButton} onPress={() => adjustTrimStart(-TRIM_STEP_SECONDS)}>
                    <Text style={styles.stepperText}>-</Text>
                  </Pressable>
                  <Text style={styles.trimValue}>{formatSeconds(trimStart)}</Text>
                  <Pressable style={styles.stepperButton} onPress={() => adjustTrimStart(TRIM_STEP_SECONDS)}>
                    <Text style={styles.stepperText}>+</Text>
                  </Pressable>
                </View>
                <Pressable style={styles.secondaryControl} onPress={() => setTrimFromPlayback('start')}>
                  <Text style={styles.secondaryControlText}>Set From Playback</Text>
                </Pressable>
              </View>

              <View style={styles.trimGroup}>
                <Text style={styles.trimLabel}>End</Text>
                <View style={styles.stepperRow}>
                  <Pressable style={styles.stepperButton} onPress={() => adjustTrimEnd(-TRIM_STEP_SECONDS)}>
                    <Text style={styles.stepperText}>-</Text>
                  </Pressable>
                  <Text style={styles.trimValue}>{formatSeconds(trimEnd)}</Text>
                  <Pressable style={styles.stepperButton} onPress={() => adjustTrimEnd(TRIM_STEP_SECONDS)}>
                    <Text style={styles.stepperText}>+</Text>
                  </Pressable>
                </View>
                <Pressable style={styles.secondaryControl} onPress={() => setTrimFromPlayback('end')}>
                  <Text style={styles.secondaryControlText}>Set From Playback</Text>
                </Pressable>
              </View>
            </View>
          </View>
        ) : null}

        <View style={styles.actions}>
          {phase === 'ready' ? (
            <Button label={readyActionLabel} onPress={handleReadyAction} style={styles.actionButton} />
          ) : null}

          {phase === 'recording' ? (
            <Button label="Stop Recording" onPress={stopRecording} style={styles.actionButton} />
          ) : null}

          {phase === 'review' || phase === 'exporting' ? (
            <>
              <Button
                label={phase === 'exporting' ? 'Preparing...' : 'Use Recording'}
                onPress={useRecording}
                disabled={phase === 'exporting'}
                style={styles.actionButton}
              />
              <Button
                label="Record Again"
                onPress={recordAgain}
                disabled={phase === 'exporting'}
                variant="secondary"
                style={styles.actionButton}
              />
            </>
          ) : null}

          {phase !== 'recording' ? (
            <Button label="Cancel" onPress={cancelRecording} variant="secondary" style={styles.actionButton} />
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  scroll: {
    flex: 1,
    backgroundColor: '#000',
  },
  scrollContent: {
    minHeight: '100%',
    paddingHorizontal: 20,
    paddingTop: 22,
    paddingBottom: 34,
    gap: 20,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  headerButton: {
    width: 92,
    minHeight: 52,
    borderRadius: 8,
  },
  title: {
    flex: 1,
    color: tokens.colors.brand,
    fontSize: 31,
    lineHeight: 37,
    fontWeight: '800',
    textAlign: 'center',
  },
  videoFrame: {
    width: '100%',
    aspectRatio: 9 / 16,
    maxHeight: 560,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#111',
    borderWidth: 1,
    borderColor: '#25324A',
    alignSelf: 'center',
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
  messageBlock: {
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#5C2730',
    backgroundColor: '#1B0E12',
    padding: 12,
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 13,
    lineHeight: 19,
    textAlign: 'center',
  },
  recordingStatus: {
    minHeight: 42,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#5C2730',
    backgroundColor: '#1B0E12',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  recordingDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#FF4D5E',
  },
  recordingText: {
    color: tokens.colors.textPrimary,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '800',
    fontVariant: ['tabular-nums'],
  },
  trimSection: {
    gap: 12,
  },
  sectionTitle: {
    color: tokens.colors.brand,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '800',
  },
  rangeText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  trimGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  trimGroup: {
    flexGrow: 1,
    flexBasis: 220,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#25324A',
    backgroundColor: '#12151D',
    padding: 12,
    gap: 10,
  },
  trimLabel: {
    color: tokens.colors.textMuted,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  stepperRow: {
    minHeight: 46,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  stepperButton: {
    width: 44,
    height: 44,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: tokens.colors.brand,
  },
  stepperText: {
    color: tokens.colors.textPrimary,
    fontSize: 26,
    lineHeight: 30,
    fontWeight: '900',
  },
  trimValue: {
    flex: 1,
    color: tokens.colors.textPrimary,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '800',
    textAlign: 'center',
    fontVariant: ['tabular-nums'],
  },
  secondaryControl: {
    minHeight: 38,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#252B37',
    paddingHorizontal: 10,
  },
  secondaryControlText: {
    color: tokens.colors.textPrimary,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '800',
  },
  actions: {
    gap: 12,
  },
  actionButton: {
    width: '100%',
    borderRadius: 8,
    minHeight: 58,
  },
});
