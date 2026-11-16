import type * as ImagePicker from 'expo-image-picker';
import { lazy, Suspense, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Navigate, useNavigate, useParams } from 'react-router';
import { useAuth } from '../../context/AuthContext';
import { fetchAnalysisResult } from '../../lib/backendApi';
import { getFreshBackendAccessToken } from '../../lib/backendAuth';
import type { VideoAnalysisResult } from '../types/videoAnalysis';
import { useWebAnalysisActivity } from './web-analysis-activity';
import { AnalysisIdentity, AnalysisProgress } from './web-analysis-progress';
import { analysisStageCopy } from '../../lib/analysisActivityPresentation';
import VideoSetupModal from '../components/VideoSetupModal';
import type { VideoSetupSelection } from '../constants/videoSetup';

const UploadVideoScreen = lazy(() => import('../screens/UploadVideoScreen'));
const WebVideoRecorderScreen = lazy(() => import('../screens/WebVideoRecorderScreen'));
const AnalysisReviewScreen = lazy(() => import('../screens/AnalysisReviewScreen'));

const SIDE_SQUAT_SETUP = { exercise: 'Squat', angle: 'Side' } as const;
const WEB_SETUP_MESSAGE = 'The web beta currently supports Side-view Squat only.';

function isSupportedWebVideoSetup(selection: VideoSetupSelection) {
  return selection.exercise === SIDE_SQUAT_SETUP.exercise && selection.angle === SIDE_SQUAT_SETUP.angle;
}

function RouteLoading({ label = 'Loading analysis…' }: { label?: string }) {
  return (
    <View style={styles.centered} accessibilityLabel={label}>
      <ActivityIndicator color="#1F6BFF" size="large" />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

export function WebUploadRoute() {
  const navigate = useNavigate();
  const {
    pendingRecordedAsset,
    setPendingRecordedAsset,
    pendingVideoSetup,
    setPendingVideoSetup,
    recordQueued,
  } = useWebAnalysisActivity();

  if (!pendingVideoSetup) {
    return <Navigate to="/setup" replace />;
  }

  return (
    <Suspense fallback={<RouteLoading label="Loading video upload…" />}>
      <UploadVideoScreen
        sourceMode={pendingRecordedAsset ? 'camera' : 'library'}
        initialSelectedVideo={pendingRecordedAsset}
        initialVideoSetup={pendingVideoSetup}
        isSelectionSupported={isSupportedWebVideoSetup}
        unsupportedSelectionMessage={WEB_SETUP_MESSAGE}
        onBack={() => {
          setPendingRecordedAsset(null);
          navigate('/submit');
        }}
        onRecordVideoPress={() => navigate('/record')}
        onAnalysisQueued={(activity) => {
          recordQueued(activity);
          setPendingRecordedAsset(null);
          setPendingVideoSetup(null);
          navigate(`/queued/${activity.videoId}`, { replace: true });
        }}
      />
    </Suspense>
  );
}

export function WebRecordRoute() {
  const navigate = useNavigate();
  const { pendingVideoSetup, setPendingRecordedAsset } = useWebAnalysisActivity();

  if (!pendingVideoSetup) {
    return <Navigate to="/setup" replace />;
  }

  return (
    <Suspense fallback={<RouteLoading label="Starting the camera…" />}>
      <WebVideoRecorderScreen
        setup={pendingVideoSetup}
        onBack={() => navigate('/submit')}
        onEditSetup={() => navigate('/setup')}
        onUseRecording={(asset: ImagePicker.ImagePickerAsset) => {
          setPendingRecordedAsset(asset);
          navigate('/upload');
        }}
      />
    </Suspense>
  );
}

export function WebVideoSetupRoute() {
  const navigate = useNavigate();
  const { pendingVideoSetup, setPendingVideoSetup } = useWebAnalysisActivity();

  return (
    <VideoSetupModal
      visible
      initialSelection={pendingVideoSetup ?? SIDE_SQUAT_SETUP}
      onCancel={() => navigate('/')}
      onContinue={(selection: VideoSetupSelection) => {
        setPendingVideoSetup(selection);
        navigate('/submit');
      }}
      isSelectionSupported={isSupportedWebVideoSetup}
      unsupportedSelectionMessage={WEB_SETUP_MESSAGE}
    />
  );
}

export function WebSubmissionChoiceRoute() {
  const navigate = useNavigate();
  const { pendingVideoSetup } = useWebAnalysisActivity();

  if (!pendingVideoSetup) {
    return <Navigate to="/setup" replace />;
  }

  return (
    <View style={styles.submissionChoice}>
      <Text accessibilityRole="header" style={styles.heading}>Choose your video</Text>
      <Text style={styles.body}>Side-view Squat selected. Upload a recording or use this device’s camera.</Text>
      <Pressable accessibilityRole="button" onPress={() => navigate('/upload')} style={styles.primaryButton}>
        <Text style={styles.primaryButtonText}>Upload Video</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => navigate('/record')} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>Record Video</Text>
      </Pressable>
      <Pressable accessibilityRole="button" onPress={() => navigate('/setup')} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>Edit setup</Text>
      </Pressable>
    </View>
  );
}

export function WebQueuedRoute() {
  const navigate = useNavigate();
  const { videoId } = useParams();
  const { items, activeCount, activeLimit, loading } = useWebAnalysisActivity();
  const activity = items.find((item) => item.video_id === videoId);
  if (!videoId) return <Navigate to="/" replace />;
  if (!activity && loading) return <RouteLoading />;
  if (!activity) return <Navigate to="/" replace />;
  return <ScrollView contentContainerStyle={styles.processingPage}>
    <Text accessibilityRole="header" style={styles.heading}>Video queued for analysis</Text>
    {activity && <AnalysisIdentity activity={activity} />}
    <Text style={styles.body}>Your video was submitted. Analysis continues when you leave this page.</Text>
    <Text style={styles.body}>{activeCount < activeLimit
      ? 'You can upload or record another video while this one runs.'
      : `All ${activeLimit} analysis slots are busy. Follow each video’s progress on Home.`}</Text>
    <Pressable accessibilityRole="button" onPress={() => navigate('/', { replace: true })} style={styles.primaryButton}>
      <Text style={styles.primaryButtonText}>Back to Home</Text>
    </Pressable>
  </ScrollView>;
}

export function WebProcessingRoute() {
  const navigate = useNavigate();
  const { videoId } = useParams();
  const { items, loading, error, refresh } = useWebAnalysisActivity();
  const activity = items.find((item) => item.video_id === videoId) ?? null;
  const copy = analysisStageCopy(activity);

  if (!videoId) return <Navigate to="/" replace />;

  return (
    <ScrollView contentContainerStyle={styles.processingPage}>
      {activity && <AnalysisIdentity activity={activity} />}
      <Text accessibilityRole="header" style={styles.heading}>{copy.title}</Text>
      <Text style={styles.body}>{copy.detail}</Text>
      {activity && <AnalysisProgress activity={activity} />}
      {!activity && !loading && !error && <Text style={styles.muted}>This activity is no longer available. Check Home for your current lifts.</Text>}
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
    </ScrollView>
  );
}

export function WebReviewRoute({ onLibraryChanged }: { onLibraryChanged: () => void }) {
  const navigate = useNavigate();
  const { videoId } = useParams();
  const { session } = useAuth();
  const { removeActivity } = useWebAnalysisActivity();
  const [result, setResult] = useState<VideoAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!videoId || !session?.access_token) return;

    let active = true;
    const controller = new AbortController();
    setError(null);
    setResult(null);

    getFreshBackendAccessToken()
      .then((accessToken) => fetchAnalysisResult(videoId, accessToken, controller.signal))
      .then((analysis) => {
        if (!active) return;
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
        videoUri={null}
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
  submissionChoice: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
    paddingHorizontal: 24,
  },
  processingPage: {
    flex: 1,
    flexGrow: 1,
    padding: 24,
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
