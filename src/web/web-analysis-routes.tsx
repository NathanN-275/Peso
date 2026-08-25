import type * as ImagePicker from 'expo-image-picker';
import { lazy, Suspense, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Navigate, useNavigate, useParams } from 'react-router';
import { useAuth } from '../../context/AuthContext';
import { fetchAnalysisResult, getVideoPlaybackUrl } from '../../lib/backendApi';
import type { AnalysisActivityItem, VideoAnalysisResult } from '../types/videoAnalysis';
import { useWebAnalysisActivity } from './web-analysis-activity';

const UploadVideoScreen = lazy(() => import('../screens/UploadVideoScreen'));
const WebVideoRecorderScreen = lazy(() => import('../screens/WebVideoRecorderScreen'));
const AnalysisReviewScreen = lazy(() => import('../screens/AnalysisReviewScreen'));

const SIDE_SQUAT_SETUP = { exercise: 'Squat', angle: 'Side' } as const;

function RouteLoading({ label = 'Loading analysis…' }: { label?: string }) {
  return (
    <View style={styles.centered} accessibilityLabel={label}>
      <ActivityIndicator color="#1F6BFF" size="large" />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

function stageCopy(activity: AnalysisActivityItem | null) {
  switch (activity?.stage) {
    case 'queued':
      return { title: 'Squat set is queued', detail: 'Waiting for an analysis worker.' };
    case 'downloading':
      return { title: 'Preparing your video', detail: 'Downloading the uploaded source.' };
    case 'pose':
      return { title: 'Estimating pose', detail: 'Tracking the lifter through the set.' };
    case 'barbell_tracking':
      return { title: 'Tracking the barbell', detail: 'Building the visible bar path.' };
    case 'saving':
      return { title: 'Saving your analysis', detail: 'Preparing the result for review.' };
    case 'ready':
      return { title: 'Analysis ready', detail: 'Your real result is ready to review.' };
    case 'failed':
      return { title: 'Analysis could not finish', detail: 'Try another side-view squat video.' };
    default:
      return { title: 'Loading analysis activity', detail: 'Checking the durable queue.' };
  }
}

export function WebUploadRoute() {
  const navigate = useNavigate();
  const {
    pendingRecordedAsset,
    setPendingRecordedAsset,
    recordQueued,
  } = useWebAnalysisActivity();

  return (
    <Suspense fallback={<RouteLoading label="Loading video upload…" />}>
      <UploadVideoScreen
        sourceMode={pendingRecordedAsset ? 'camera' : 'library'}
        initialSelectedVideo={pendingRecordedAsset}
        initialVideoSetup={SIDE_SQUAT_SETUP}
        onBack={() => {
          setPendingRecordedAsset(null);
          navigate('/');
        }}
        onRecordVideoPress={() => navigate('/record')}
        onAnalysisQueued={(activity) => {
          recordQueued(activity);
          setPendingRecordedAsset(null);
          navigate(`/processing/${activity.videoId}`);
        }}
      />
    </Suspense>
  );
}

export function WebRecordRoute() {
  const navigate = useNavigate();
  const { setPendingRecordedAsset } = useWebAnalysisActivity();

  return (
    <Suspense fallback={<RouteLoading label="Starting the camera…" />}>
      <WebVideoRecorderScreen
        setup={SIDE_SQUAT_SETUP}
        onBack={() => navigate('/')}
        onUseRecording={(asset: ImagePicker.ImagePickerAsset) => {
          setPendingRecordedAsset(asset);
          navigate('/upload');
        }}
      />
    </Suspense>
  );
}

export function WebProcessingRoute() {
  const navigate = useNavigate();
  const { videoId } = useParams();
  const { items, loading, error, refresh } = useWebAnalysisActivity();
  const activity = items.find((item) => item.video_id === videoId) ?? null;
  const copy = stageCopy(activity);

  if (!videoId) return <Navigate to="/" replace />;

  return (
    <View style={styles.processingPage}>
      <View style={styles.stageMark}>
        <Text style={styles.stageMarkText}>{activity?.stage === 'ready' ? '✓' : 'P'}</Text>
      </View>
      <Text accessibilityRole="header" style={styles.heading}>{copy.title}</Text>
      <Text style={styles.body}>{copy.detail}</Text>
      <View style={styles.stageList} accessibilityLabel="Analysis stages">
        {['Queued', 'Downloading', 'Pose', 'Barbell tracking', 'Saving', 'Ready'].map((stage) => (
          <Text key={stage} style={styles.stageText}>{stage}</Text>
        ))}
      </View>
      {loading ? <ActivityIndicator color="#1F6BFF" /> : null}
      {error ? (
        <View style={styles.errorCard} role="alert">
          <Text style={styles.error}>{error}</Text>
          <Pressable accessibilityRole="button" onPress={() => void refresh()} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Retry activity</Text>
          </Pressable>
        </View>
      ) : null}
      {activity?.stage === 'ready' ? (
        <Pressable accessibilityRole="button" onPress={() => navigate(`/review/${videoId}`)} style={styles.primaryButton}>
          <Text style={styles.primaryButtonText}>Review result</Text>
        </Pressable>
      ) : null}
      <Pressable accessibilityRole="button" onPress={() => navigate('/')} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>Back to Home</Text>
      </Pressable>
    </View>
  );
}

export function WebReviewRoute({ onLibraryChanged }: { onLibraryChanged: () => void }) {
  const navigate = useNavigate();
  const { videoId } = useParams();
  const { session } = useAuth();
  const { removeActivity } = useWebAnalysisActivity();
  const [videoUri, setVideoUri] = useState<string | null>(null);
  const [result, setResult] = useState<VideoAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!videoId || !session?.access_token) return;

    let active = true;
    const controller = new AbortController();
    setError(null);
    setResult(null);
    setVideoUri(null);

    Promise.all([
      getVideoPlaybackUrl(videoId, session.access_token),
      fetchAnalysisResult(videoId, session.access_token, controller.signal),
    ])
      .then(([playback, analysis]) => {
        if (!active) return;
        setVideoUri(playback.video_url);
        setResult(analysis.result_json);
      })
      .catch((loadError) => {
        if (!active || controller.signal.aborted) return;
        setError(loadError instanceof Error ? loadError.message : 'Unable to load this analysis.');
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [reloadKey, session?.access_token, videoId]);

  if (!videoId) return <Navigate to="/" replace />;

  if (error) {
    return (
      <View style={styles.centered} role="alert">
        <Text style={styles.error}>{error}</Text>
        <Pressable accessibilityRole="button" onPress={() => setReloadKey((value) => value + 1)} style={styles.primaryButton}>
          <Text style={styles.primaryButtonText}>Retry review</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => navigate(`/processing/${videoId}`)} style={styles.secondaryButton}>
          <Text style={styles.secondaryButtonText}>Back to activity</Text>
        </Pressable>
      </View>
    );
  }

  if (!result) return <RouteLoading label="Loading your analysis…" />;

  return (
    <Suspense fallback={<RouteLoading label="Loading the review tools…" />}>
      <AnalysisReviewScreen
        mode="pending"
        videoUri={videoUri}
        result={result}
        onBack={() => navigate('/')}
        onDiscarded={() => {
          removeActivity(videoId);
          navigate('/');
        }}
        onSaved={() => {
          removeActivity(videoId);
          onLibraryChanged();
          navigate('/');
        }}
      />
    </Suspense>
  );
}

const styles = StyleSheet.create({
  centered: {
    minHeight: 420,
    padding: 32,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    backgroundColor: '#07090D',
  },
  processingPage: {
    flex: 1,
    minHeight: 560,
    padding: 40,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 18,
    backgroundColor: '#07090D',
  },
  stageMark: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1F6BFF',
  },
  stageMarkText: { color: '#FFFFFF', fontSize: 28, fontWeight: '800' },
  heading: { color: '#F5F8FF', fontSize: 30, fontWeight: '800', textAlign: 'center' },
  body: { maxWidth: 560, color: '#A7B3C7', fontSize: 16, lineHeight: 24, textAlign: 'center' },
  muted: { color: '#A7B3C7', fontSize: 14 },
  stageList: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 8 },
  stageText: { color: '#8AB2FF', fontSize: 12, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: '#102653' },
  errorCard: { maxWidth: 620, padding: 16, gap: 12, borderRadius: 10, backgroundColor: '#32131A' },
  error: { color: '#FF9CAA', fontSize: 14, lineHeight: 21, textAlign: 'center' },
  primaryButton: { minWidth: 180, paddingHorizontal: 20, paddingVertical: 13, borderRadius: 9, backgroundColor: '#1F6BFF', alignItems: 'center' },
  primaryButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  secondaryButton: { minWidth: 180, paddingHorizontal: 20, paddingVertical: 12, borderWidth: 1, borderColor: '#34425A', borderRadius: 9, alignItems: 'center' },
  secondaryButtonText: { color: '#DCE5F5', fontSize: 14, fontWeight: '600' },
});
