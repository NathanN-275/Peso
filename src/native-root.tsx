import '../global.css';

import * as ImagePicker from 'expo-image-picker';
import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Linking,
  LogBox,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider, useAuth } from '../context/AuthContext';
import CreateAccountScreen from './screens/CreateAccountScreen';
import AddVideoScreen from './screens/AddVideoScreen';
import HomeScreen from './screens/HomeScreen';
import LoginScreen from './screens/LoginScreen';
import ResetPasswordScreen from './screens/EmailResetPasswordScreen';
import ResetPasswordFormScreen from './screens/ChangePasswordScreen';
import AnalysisReviewScreen from './screens/AnalysisReviewScreen';
import SavedLiftVideosScreen from './screens/SavedLiftVideosScreen';
import UploadVideoScreen from './screens/UploadVideoScreen';
import WebVideoRecorderScreen from './screens/WebVideoRecorderScreen';
import VideoSetupModal from './components/VideoSetupModal';
import WelcomeScreen from './screens/WelcomeScreen';
import ProfileScreen from './screens/ProfileScreen';
import SettingsScreen from './screens/SettingsScreen';
import { supabase } from '../lib/supabase';
import {
  parseNativeAuthRedirect,
  parseWebAuthRedirect,
  redactAuthParams,
} from '../lib/auth-redirect';
import { deleteSavedVideo, fetchAnalysisResult, getVideoPlaybackUrl } from '../lib/backendApi';
import type { SavedVideo } from '../lib/backendApi';
import type { VideoSetupSelection } from './constants/videoSetup';
import type { SavedVideoOverview, VideoAnalysisResult } from './types/videoAnalysis';

LogBox.ignoreLogs([
  "SafeAreaView has been deprecated and will be removed in a future release. Please use 'react-native-safe-area-context' instead.",
]);

// Manual route map for the small auth flow.
const AUTH_ROUTES = {
  home: 'home',
  addVideo: 'add-video',
  uploadVideo: 'upload-video',
  webRecordVideo: 'web-record-video',
  savedLiftVideos: 'saved-lift-videos',
  savedVideoReview: 'saved-video-review',
  pendingAnalysisReview: 'pending-analysis-review',
  profile: 'profile',
  settings: 'settings',
  welcome: 'welcome',
  login: 'login',
  createAccount: 'create-account',
  resetPassword: 'reset-password',
  resetPasswordForm: 'reset-password-form',
} as const;

type AuthRoute = (typeof AUTH_ROUTES)[keyof typeof AUTH_ROUTES];

type ParsedNativeAuthRoute = {
  route: AuthRoute | null;
  trusted: boolean;
  destination: 'login' | 'reset-password' | null;
  queryParams: Record<string, string>;
  hashParams: Record<string, string>;
  code: string | null;
  accessToken: string | null;
  refreshToken: string | null;
  isRecoveryResetLink: boolean;
  hasRecoverySessionParams: boolean;
  errorMessage: string | null;
};

type ParsedWebAuthLink = {
  route: AuthRoute | null;
  searchParams: Record<string, string>;
  hashParams: Record<string, string>;
  resetRouteDetected: boolean;
  supabaseAuthErrorDetected: boolean;
  errorMessage: string | null;
};

const WEB_ROUTE_HASHES: Record<AuthRoute, string> = {
  [AUTH_ROUTES.home]: '#/home',
  [AUTH_ROUTES.addVideo]: '#/add-video',
  [AUTH_ROUTES.uploadVideo]: '#/upload-video',
  [AUTH_ROUTES.webRecordVideo]: '#/web-record-video',
  [AUTH_ROUTES.savedLiftVideos]: '#/saved-lift-videos',
  [AUTH_ROUTES.savedVideoReview]: '#/saved-video-review',
  [AUTH_ROUTES.pendingAnalysisReview]: '#/pending-analysis-review',
  [AUTH_ROUTES.profile]: '#/profile',
  [AUTH_ROUTES.settings]: '#/settings',
  [AUTH_ROUTES.welcome]: '#/welcome',
  [AUTH_ROUTES.login]: '#/login',
  [AUTH_ROUTES.createAccount]: '#/create-account',
  [AUTH_ROUTES.resetPassword]: '#/reset-password',
  [AUTH_ROUTES.resetPasswordForm]: '#/reset-password-form',
};

const styles = StyleSheet.create({
  // Web mode renders the app inside a phone-sized frame.
  webWrapper: {
    flex: 1,
    width: '100%',
    backgroundColor: '#3a3a3a',
  },
  phoneFrame: {
    width: 390,
    height: 844,
    flexGrow: 1,
    backgroundColor: '#000',
    overflow: 'hidden',
  },
});

function parseWebAuthRoute(hash: string): AuthRoute {
  // Match the URL hash to one of the known screens.
  const normalizedHash = hash.toLowerCase();

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.home]) {
    return AUTH_ROUTES.home;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.addVideo]) {
    return AUTH_ROUTES.addVideo;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.uploadVideo]) {
    return AUTH_ROUTES.uploadVideo;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.webRecordVideo]) {
    return AUTH_ROUTES.webRecordVideo;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.savedLiftVideos]) {
    return AUTH_ROUTES.savedLiftVideos;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.savedVideoReview]) {
    return AUTH_ROUTES.savedVideoReview;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.pendingAnalysisReview]) {
    return AUTH_ROUTES.pendingAnalysisReview;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.profile]) {
    return AUTH_ROUTES.profile;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.settings]) {
    return AUTH_ROUTES.settings;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.login]) {
    return AUTH_ROUTES.login;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.createAccount]) {
    return AUTH_ROUTES.createAccount;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.resetPassword]) {
    return AUTH_ROUTES.resetPassword;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.resetPasswordForm]) {
    return AUTH_ROUTES.resetPasswordForm;
  }

  return AUTH_ROUTES.welcome;
}

function parseWebAuthLink(pathname: string, search: string, hash: string): ParsedWebAuthLink {
  // Detect web recovery links before the screen is chosen.
  const parsed = parseWebAuthRedirect(pathname, search, hash);
  const supabaseAuthErrorDetected = Boolean(parsed.errorMessage);
  const resetRouteDetected = parsed.isRecovery;

  return {
    route: resetRouteDetected ? AUTH_ROUTES.resetPasswordForm : null,
    searchParams: parsed.queryParams,
    hashParams: parsed.hashParams,
    resetRouteDetected,
    supabaseAuthErrorDetected,
    errorMessage: parsed.errorMessage,
  };
}

function parseNativeAuthRoute(url: string): ParsedNativeAuthRoute {
  const parsed = parseNativeAuthRedirect(url);
  const isRecoveryResetLink = parsed.trusted && parsed.destination === 'reset-password';

  return {
    ...parsed,
    route: !parsed.trusted
      ? null
      : isRecoveryResetLink
        ? AUTH_ROUTES.resetPasswordForm
        : AUTH_ROUTES.login,
    isRecoveryResetLink,
    hasRecoverySessionParams: parsed.hasSessionParams,
  };
}

async function hydrateAuthRedirectSession(parsedRoute: ParsedNativeAuthRoute) {
  // Load a session only from an exact, allowlisted Peso auth callback.
  if (!parsedRoute.trusted || !parsedRoute.hasRecoverySessionParams || !supabase) {
    return null;
  }

  if (parsedRoute.code) {
    const { error } = await supabase.auth.exchangeCodeForSession(parsedRoute.code);

    if (error) {
      throw error;
    }

    return 'code';
  }

  if (parsedRoute.accessToken && parsedRoute.refreshToken) {
    const { error } = await supabase.auth.setSession({
      access_token: parsedRoute.accessToken,
      refresh_token: parsedRoute.refreshToken,
    });

    if (error) {
      throw error;
    }

    return 'tokens';
  }

  return null;
}

function AppContent() {
  // This app switches screens manually instead of using a router.
  const {
    session,
    user,
    initializing,
    configError,
    passwordRecoveryMode,
    activatePasswordRecoveryMode,
    signOut,
  } = useAuth();
  const [route, setRoute] = useState<AuthRoute>(() => {
    // Web starts from the current hash so refreshes keep the same screen.
    if (Platform.OS === 'web') {
      const webAuthLink = parseWebAuthLink(
        window.location.pathname,
        window.location.search,
        window.location.hash
      );

      if (webAuthLink.route) {
        return webAuthLink.route;
      }

      return parseWebAuthRoute(window.location.hash);
    }

    return AUTH_ROUTES.welcome;
  });
  const [initialDeepLinkChecked, setInitialDeepLinkChecked] = useState(Platform.OS === 'web');
  const [isHandlingRecoveryLink, setIsHandlingRecoveryLink] = useState(false);
  const [isRecoveryMode, setIsRecoveryMode] = useState(false);
  const [recoverySessionReady, setRecoverySessionReady] = useState(false);
  const [authLinkErrorMessage, setAuthLinkErrorMessage] = useState<string | null>(() => {
    if (Platform.OS !== 'web') {
      return null;
    }

    return parseWebAuthLink(
      window.location.pathname,
      window.location.search,
      window.location.hash
    ).errorMessage;
  });
  const [homeRefreshKey, setHomeRefreshKey] = useState(0);
  const [queuedAnalysisConfirmation, setQueuedAnalysisConfirmation] = useState<string | null>(null);
  const [uploadSourceMode, setUploadSourceMode] = useState<'camera' | 'library'>('library');
  const [recordedUploadVideo, setRecordedUploadVideo] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [recordedUploadSetup, setRecordedUploadSetup] = useState<VideoSetupSelection | null>(null);
  const [pendingRecordingSetup, setPendingRecordingSetup] = useState<VideoSetupSelection | null>(null);
  const [recordingSetupModalVisible, setRecordingSetupModalVisible] = useState(false);
  const [recordingSetupResumeKey, setRecordingSetupResumeKey] = useState(0);
  const [recordingLauncherOpen, setRecordingLauncherOpen] = useState(false);
  const [savedOverview, setSavedOverview] = useState<SavedVideoOverview | null>(null);
  const [savedOverviewLoaded, setSavedOverviewLoaded] = useState(false);
  const [selectedSavedExerciseType, setSelectedSavedExerciseType] = useState<string | null>(null);
  const [selectedSavedVideo, setSelectedSavedVideo] = useState<SavedVideo | null>(null);
  const [selectedSavedVideoPlaybackUri, setSelectedSavedVideoPlaybackUri] = useState<string | null>(null);
  const [selectedSavedVideoAnalysisResult, setSelectedSavedVideoAnalysisResult] =
    useState<VideoAnalysisResult | null>(null);
  const [pendingAnalysisPlaybackUri, setPendingAnalysisPlaybackUri] = useState<string | null>(null);
  const [pendingAnalysisResult, setPendingAnalysisResult] = useState<VideoAnalysisResult | null>(null);
  const routeRef = useRef(route);
  const hadSessionRef = useRef(false);

  useEffect(() => {
    // Keep the current route in a ref for async deep-link handlers.
    routeRef.current = route;
  }, [route]);

  useEffect(() => {
    if (session?.access_token) {
      return;
    }

    setSavedOverview(null);
    setSavedOverviewLoaded(false);
  }, [session?.access_token]);

  useEffect(() => {
    // Native links are parsed here so recovery sessions can be hydrated early.
    if (Platform.OS === 'web') {
      return;
    }

    const handleUrl = async (url: string | null, source: 'initial' | 'runtime') => {
      // Route both initial and runtime URLs through the same parser.
      if (!url) {
        console.log('[DeepLink] final route chosen', routeRef.current);
        return;
      }

      const parsedRoute = parseNativeAuthRoute(url);
      const nextRoute = parsedRoute.route;

      console.log('[DeepLink] parsed auth redirect', {
        source,
        trusted: parsedRoute.trusted,
        destination: parsedRoute.destination,
        queryParams: redactAuthParams(parsedRoute.queryParams),
        hashParams: redactAuthParams(parsedRoute.hashParams),
      });
      console.log('[DeepLink] recovery detected', parsedRoute.isRecoveryResetLink);
      console.log('[DeepLink] recovery session detected', parsedRoute.hasRecoverySessionParams);
      if (nextRoute) {
        setAuthLinkErrorMessage(parsedRoute.errorMessage);
        setRecoverySessionReady(false);

        if (parsedRoute.isRecoveryResetLink) {
          setIsHandlingRecoveryLink(!parsedRoute.errorMessage);
          setIsRecoveryMode(false);
          setRoute(AUTH_ROUTES.resetPasswordForm);
        }

        try {
          const exchangeMethod = parsedRoute.errorMessage
            ? null
            : await hydrateAuthRedirectSession(parsedRoute);
          console.log('[Recovery] session exchange success', { method: exchangeMethod });

          let hasSession = false;
          if (supabase) {
            const {
              data: { session: currentSession },
            } = await supabase.auth.getSession();
            hasSession = !!currentSession;

            setRecoverySessionReady(hasSession);
            console.log('[Recovery] getSession after exchange', { hasSession });
          }

          if (parsedRoute.isRecoveryResetLink && !parsedRoute.errorMessage) {
            if (hasSession) {
              console.log('[Recovery] mode on', { reason: 'verified-deep-link' });
              setIsRecoveryMode(true);
              activatePasswordRecoveryMode();
            } else {
              setAuthLinkErrorMessage(
                'Reset link session expired or was not loaded. Please request a new reset link.'
              );
            }
          }
        } catch (error) {
          setRecoverySessionReady(false);
          setIsRecoveryMode(false);
          setAuthLinkErrorMessage(
            parsedRoute.isRecoveryResetLink
              ? 'Reset link expired or was already used. Please request a new reset email.'
              : 'Confirmation link expired or was already used. Please request a new confirmation email.'
          );
          console.error('[Recovery] session exchange error', error);
        } finally {
          if (parsedRoute.isRecoveryResetLink) {
            setIsHandlingRecoveryLink(false);
          }
        }

        if (!parsedRoute.isRecoveryResetLink) {
          setRoute(nextRoute);
        }
      }
      console.log('[DeepLink] final route chosen', nextRoute ?? routeRef.current);
    };

    Linking.getInitialURL()
      .then((url) => handleUrl(url, 'initial'))
      .catch((error) => {
        console.error('[DeepLink] failed to read initial URL', error);
      })
      .finally(() => {
        setInitialDeepLinkChecked(true);
      });

    const subscription = Linking.addEventListener('url', ({ url }) => {
      handleUrl(url, 'runtime').catch((error) => {
        console.error('[DeepLink] failed to handle incoming URL', error);
      });
    });

    return () => {
      subscription.remove();
    };
  }, []);

  const navigateToAuthRoute = (nextRoute: AuthRoute) => {
    // Clear recovery state when leaving the reset-password flow.
    if (nextRoute !== AUTH_ROUTES.resetPasswordForm) {
      if (isHandlingRecoveryLink || isRecoveryMode || recoverySessionReady) {
        console.log('[Recovery] mode off', { reason: 'route-change', route: nextRoute });
      }
      setIsHandlingRecoveryLink(false);
      setIsRecoveryMode(false);
      setRecoverySessionReady(false);
    }

    if (Platform.OS === 'web') {
      if (nextRoute !== AUTH_ROUTES.resetPasswordForm && window.location.search.includes('auth=')) {
        const nextUrl = new URL(window.location.href);

        nextUrl.searchParams.delete('auth');
        window.history.replaceState(null, '', `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
      }

      const nextHash = WEB_ROUTE_HASHES[nextRoute];

      if (window.location.hash !== nextHash) {
        window.location.hash = nextHash;
      }

      setRoute(nextRoute);
      return;
    }

    setRoute(nextRoute);
  };

  const authNavigation = {
    toHome: () => navigateToAuthRoute(AUTH_ROUTES.home),
    toAddVideo: () => navigateToAuthRoute(AUTH_ROUTES.addVideo),
    toUploadVideo: () => navigateToAuthRoute(AUTH_ROUTES.uploadVideo),
    toProfile: () => navigateToAuthRoute(AUTH_ROUTES.profile),
    toSettings: () => navigateToAuthRoute(AUTH_ROUTES.settings),
    toWelcome: () => navigateToAuthRoute(AUTH_ROUTES.welcome),
    toLogin: () => navigateToAuthRoute(AUTH_ROUTES.login),
    toCreateAccount: () => navigateToAuthRoute(AUTH_ROUTES.createAccount),
    toResetPassword: () => navigateToAuthRoute(AUTH_ROUTES.resetPassword),
    toResetPasswordForm: () => navigateToAuthRoute(AUTH_ROUTES.resetPasswordForm),
  };

  const handleRecordedVideoAsset = (
    asset?: ImagePicker.ImagePickerAsset | null,
    setup: VideoSetupSelection | null = pendingRecordingSetup
  ) => {
    if (!asset) {
      return;
    }

    setRecordedUploadVideo(asset);
    setRecordedUploadSetup(setup);
    setUploadSourceMode('camera');
    authNavigation.toUploadVideo();
  };

  const launchRecordingCamera = async (setup: VideoSetupSelection | null = pendingRecordingSetup) => {
    if (recordingLauncherOpen) {
      return;
    }

    setRecordingLauncherOpen(true);

    try {
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ['videos'],
        allowsEditing: true,
        quality: 1,
        videoMaxDuration: 0,
        cameraType: ImagePicker.CameraType.back,
        ...(Platform.OS === 'ios'
          ? {
              videoExportPreset: ImagePicker.VideoExportPreset.H264_1280x720,
              videoQuality: ImagePicker.UIImagePickerControllerQualityType.High,
            }
          : {}),
      });

      if (result.canceled) {
        return;
      }

      handleRecordedVideoAsset(result.assets[0], setup);
    } finally {
      setRecordingLauncherOpen(false);
    }
  };

  const promptForCameraSettings = () => {
    Alert.alert(
      'Camera access needed',
      'Peso needs camera access to record lift videos.',
      [
        {
          text: 'Accept',
          onPress: () => {
            void requestCameraPermissionAndRecord(true);
          },
        },
        {
          text: 'Settings',
          onPress: () => {
            void Linking.openSettings();
          },
        },
      ],
      { cancelable: true }
    );
  };

  const handleWebRecordVideoRoute = () => {
    setRecordedUploadVideo(null);
    setUploadSourceMode('camera');
    navigateToAuthRoute(AUTH_ROUTES.webRecordVideo);
  };

  const requestCameraPermissionAndRecord = async (
    forcePrompt = false,
    setup: VideoSetupSelection | null = pendingRecordingSetup
  ) => {
    if (Platform.OS === 'web') {
      handleWebRecordVideoRoute();
      return;
    }

    const currentPermission = await ImagePicker.getCameraPermissionsAsync();

    if (currentPermission.granted) {
      await launchRecordingCamera(setup);
      return;
    }

    if (currentPermission.canAskAgain || forcePrompt) {
      const requestedPermission = await ImagePicker.requestCameraPermissionsAsync();

      if (requestedPermission.granted) {
        await launchRecordingCamera(setup);
        return;
      }
    }

    promptForCameraSettings();
  };

  const handleRecordVideoRoute = () => {
    setRecordedUploadVideo(null);
    setRecordedUploadSetup(null);
    setPendingRecordingSetup(null);
    setRecordingSetupModalVisible(true);
  };

  const handleRecordingSetupContinue = (selection: VideoSetupSelection) => {
    setPendingRecordingSetup(selection);
    setRecordedUploadSetup(selection);
    setRecordingSetupModalVisible(false);

    if (route === AUTH_ROUTES.webRecordVideo) {
      setRecordingSetupResumeKey((key) => key + 1);
      return;
    }

    if (Platform.OS === 'web') {
      handleWebRecordVideoRoute();
      return;
    }

    void requestCameraPermissionAndRecord(true, selection);
  };

  const handleRecordingSetupCancel = () => {
    setRecordingSetupModalVisible(false);

    if (route === AUTH_ROUTES.webRecordVideo) {
      setRecordingSetupResumeKey((key) => key + 1);
    }
  };

  const handleEditRecordingSetup = () => {
    setRecordingSetupModalVisible(true);
  };

  const handleUploadVideoRoute = () => {
    setRecordedUploadVideo(null);
    setRecordedUploadSetup(null);
    setPendingRecordingSetup(null);
    setUploadSourceMode('library');
    authNavigation.toUploadVideo();
  };

  const invalidateSavedVideoCaches = () => {
    setSavedOverviewLoaded(false);
    setHomeRefreshKey((key) => key + 1);
  };

  const handleUploadBack = () => {
    setRecordedUploadVideo(null);
    setRecordedUploadSetup(null);
    setPendingRecordingSetup(null);
    authNavigation.toAddVideo();
  };
  const handleSavedOverviewLoaded = (overview: SavedVideoOverview) => {
    setSavedOverview(overview);
    setSavedOverviewLoaded(true);
  };
  const handleAnalysisSaved = (_videoId?: string) => {
    setRecordedUploadVideo(null);
    setRecordedUploadSetup(null);
    setPendingAnalysisPlaybackUri(null);
    setPendingAnalysisResult(null);
    invalidateSavedVideoCaches();
    authNavigation.toHome();
  };
  const handleAnalysisQueued = () => {
    setRecordedUploadVideo(null);
    setRecordedUploadSetup(null);
    setPendingRecordingSetup(null);
    setQueuedAnalysisConfirmation('Video queued for analysis. You can upload or record another video.');
    setHomeRefreshKey((key) => key + 1);
    authNavigation.toHome();
  };
  const handleOpenAnalysisActivity = async (videoId: string) => {
    if (!session?.access_token) {
      return;
    }

    try {
      const [playbackResponse, analysisResponse] = await Promise.all([
        getVideoPlaybackUrl(videoId, session.access_token),
        fetchAnalysisResult(videoId, session.access_token),
      ]);
      setPendingAnalysisPlaybackUri(playbackResponse.video_url);
      setPendingAnalysisResult(analysisResponse.result_json);
      navigateToAuthRoute(AUTH_ROUTES.pendingAnalysisReview);
    } catch (error) {
      Alert.alert(
        'Unable to open analysis',
        error instanceof Error ? error.message : 'Refresh Analysis Activity and try again.'
      );
      throw error;
    }
  };
  const handlePendingAnalysisDiscarded = () => {
    setPendingAnalysisPlaybackUri(null);
    setPendingAnalysisResult(null);
    setHomeRefreshKey((key) => key + 1);
    authNavigation.toHome();
  };
  const handleOpenSavedLiftFolder = (exerciseType: string) => {
    setSelectedSavedExerciseType(exerciseType);
    setSelectedSavedVideo(null);
    setSelectedSavedVideoPlaybackUri(null);
    setSelectedSavedVideoAnalysisResult(null);
    navigateToAuthRoute(AUTH_ROUTES.savedLiftVideos);
  };
  const handleOpenSavedVideo = async (video: SavedVideo) => {
    if (!session?.access_token) {
      throw new Error('You need to be signed in to open saved videos.');
    }

    const [playbackResponse, analysisResponse] = await Promise.all([
      getVideoPlaybackUrl(video.id, session.access_token),
      fetchAnalysisResult(video.id, session.access_token),
    ]);

    setSelectedSavedVideo(video);
    setSelectedSavedExerciseType(video.exercise_type);
    setSelectedSavedVideoPlaybackUri(playbackResponse.video_url);
    setSelectedSavedVideoAnalysisResult(analysisResponse.result_json);
    navigateToAuthRoute(AUTH_ROUTES.savedVideoReview);
  };
  const handleSavedVideoReviewBack = () => {
    navigateToAuthRoute(selectedSavedExerciseType ? AUTH_ROUTES.savedLiftVideos : AUTH_ROUTES.home);
  };
  const handleDeleteSavedVideos = async (videoIds: string[]) => {
    if (!session?.access_token) {
      throw new Error('You need to be signed in to delete saved videos.');
    }

    const deletedIds = new Set<string>();
    const failedIds = new Set<string>();

    for (const videoId of videoIds) {
      try {
        await deleteSavedVideo(videoId, session.access_token);
        deletedIds.add(videoId);
      } catch {
        failedIds.add(videoId);
      }
    }

    if (deletedIds.size > 0) {
      invalidateSavedVideoCaches();
      setSelectedSavedVideo((currentVideo) => currentVideo && deletedIds.has(currentVideo.id) ? null : currentVideo);
      setSelectedSavedVideoPlaybackUri((currentUri) => deletedIds.has(selectedSavedVideo?.id ?? '') ? null : currentUri);
      setSelectedSavedVideoAnalysisResult((currentResult) =>
        deletedIds.has(selectedSavedVideo?.id ?? '') ? null : currentResult
      );
    }

    if (failedIds.size > 0) {
      throw new Error(`Unable to delete ${failedIds.size} ${failedIds.size === 1 ? 'video' : 'videos'}.`);
    }
  };
  const handleDeleteSavedVideoFromReview = async (videoId: string) => {
    await handleDeleteSavedVideos([videoId]);
    navigateToAuthRoute(selectedSavedExerciseType ? AUTH_ROUTES.savedLiftVideos : AUTH_ROUTES.home);
  };
  const handleHomeRoute = () => {
    setSelectedSavedExerciseType(null);
    setSelectedSavedVideo(null);
    setSelectedSavedVideoPlaybackUri(null);
    setSelectedSavedVideoAnalysisResult(null);
    authNavigation.toHome();
  };
  const handleProfileRoute = () => {
    setSelectedSavedExerciseType(null);
    setSelectedSavedVideo(null);
    setSelectedSavedVideoPlaybackUri(null);
    setSelectedSavedVideoAnalysisResult(null);
    authNavigation.toProfile();
  };
  const handleWelcomeLoginPress = authNavigation.toLogin;
  const handleWelcomeCreateAccountPress = authNavigation.toCreateAccount;
  const handleResetPasswordBack = () => {
    console.log('[Recovery] mode off', { reason: 'back-pressed' });
    setIsHandlingRecoveryLink(false);
    setIsRecoveryMode(false);
    setRecoverySessionReady(false);
    signOut()
      .catch((error) => {
        console.error('[DeepLink] failed to clear recovery session before leaving reset screen', error);
      })
      .finally(authNavigation.toWelcome);
  };
  const handleResetPasswordSuccess = () => {
    console.log('[Recovery] mode off', { reason: 'password-update-succeeded' });
    setIsHandlingRecoveryLink(false);
    setIsRecoveryMode(false);
    setRecoverySessionReady(false);
    signOut()
      .catch((error) => {
        console.error('[ResetPassword] failed to clear recovery session after password update', error);
      })
      .finally(() => {
        console.log('[ResetPassword] route chosen after reset submit', AUTH_ROUTES.login);
        authNavigation.toLogin();
      });
  };

  useEffect(() => {
    // Web needs explicit hash handling to keep reset links stable.
    if (Platform.OS !== 'web') {
      return;
    }

    const handleWebAuthLink = () => {
      // Check the current browser URL before using the route state.
      const parsedWebLink = parseWebAuthLink(
        window.location.pathname,
        window.location.search,
        window.location.hash
      );

      console.log('[WebDeepLink] search params', redactAuthParams(parsedWebLink.searchParams));
      console.log('[WebDeepLink] hash params', redactAuthParams(parsedWebLink.hashParams));
      console.log('[WebDeepLink] reset route detected', parsedWebLink.resetRouteDetected);
      console.log('[WebDeepLink] Supabase auth error detected', parsedWebLink.supabaseAuthErrorDetected);

      setAuthLinkErrorMessage(parsedWebLink.errorMessage);

      if (parsedWebLink.route) {
        if (!parsedWebLink.supabaseAuthErrorDetected) {
          console.log('[Recovery] mode on', { reason: 'web-reset-link-detected' });
          setIsRecoveryMode(true);
          activatePasswordRecoveryMode();
        }

        setRoute(parsedWebLink.route);
        console.log('[Route] final route chosen', parsedWebLink.route);
        return true;
      }

      return false;
    };

    if (!handleWebAuthLink()) {
      console.log('[Route] final route chosen', routeRef.current);
    }

    const handleHashChange = () => {
      if (handleWebAuthLink()) {
        return;
      }

      const nextRoute = parseWebAuthRoute(window.location.hash);

      setRoute(nextRoute);
      console.log('[Route] final route chosen', nextRoute);
    };

    window.addEventListener('hashchange', handleHashChange);

    return () => {
      window.removeEventListener('hashchange', handleHashChange);
    };
  }, []);

  useEffect(() => {
    // Force the recovery screen while Supabase says recovery mode is active.
    if (!initialDeepLinkChecked) {
      return;
    }

    if (passwordRecoveryMode && !isRecoveryMode) {
      authNavigation.toResetPasswordForm();
    }
  }, [initialDeepLinkChecked, passwordRecoveryMode, isRecoveryMode]);

  useEffect(() => {
    // Protect signed-in screens and send users back to the correct default.
    if (!initialDeepLinkChecked) {
      return;
    }

    const recoveryRouteActive =
      isHandlingRecoveryLink ||
      isRecoveryMode ||
      passwordRecoveryMode ||
      route === AUTH_ROUTES.resetPasswordForm;

    if (recoveryRouteActive) {
      console.log('[AuthGuard] route chosen', {
        route: AUTH_ROUTES.resetPasswordForm,
        reason: 'recovery-active',
        isHandlingRecoveryLink,
        isRecoveryMode,
        recoverySessionReady,
        passwordRecoveryMode,
      });
      if (route !== AUTH_ROUTES.resetPasswordForm) {
        setRoute(AUTH_ROUTES.resetPasswordForm);
      }
      return;
    }

    if (session) {
      hadSessionRef.current = true;
      if (
        route !== AUTH_ROUTES.home &&
        route !== AUTH_ROUTES.addVideo &&
        route !== AUTH_ROUTES.uploadVideo &&
        route !== AUTH_ROUTES.webRecordVideo &&
        route !== AUTH_ROUTES.savedLiftVideos &&
        route !== AUTH_ROUTES.savedVideoReview &&
        route !== AUTH_ROUTES.pendingAnalysisReview &&
        route !== AUTH_ROUTES.profile &&
        route !== AUTH_ROUTES.settings &&
        !recoveryRouteActive
      ) {
        console.log('[AuthGuard] route chosen', {
          route: AUTH_ROUTES.home,
          reason: 'session-default',
        });
        authNavigation.toHome();
      }
      return;
    }

    if (
      route === AUTH_ROUTES.home ||
      route === AUTH_ROUTES.addVideo ||
      route === AUTH_ROUTES.uploadVideo ||
      route === AUTH_ROUTES.webRecordVideo ||
      route === AUTH_ROUTES.savedLiftVideos ||
      route === AUTH_ROUTES.savedVideoReview ||
      route === AUTH_ROUTES.pendingAnalysisReview ||
      route === AUTH_ROUTES.profile ||
      route === AUTH_ROUTES.settings
    ) {
      console.log('[AuthGuard] route chosen', {
        route: AUTH_ROUTES.welcome,
        reason: 'protected-route-without-session',
      });
      authNavigation.toWelcome();
      hadSessionRef.current = false;
      return;
    }

    if (hadSessionRef.current && !recoveryRouteActive) {
      console.log('[AuthGuard] route chosen', {
        route: AUTH_ROUTES.welcome,
        reason: 'session-ended',
      });
      authNavigation.toWelcome();
      hadSessionRef.current = false;
    }
  }, [
    initialDeepLinkChecked,
    session,
    route,
    passwordRecoveryMode,
    isHandlingRecoveryLink,
    isRecoveryMode,
    recoverySessionReady,
  ]);

  const screenContent = (() => {
    if (initializing || !initialDeepLinkChecked) {
      return (
        <View className="flex-1 items-center justify-center bg-bg" style={{ paddingHorizontal: 24 }}>
          <Text className="text-text-primary" style={{ fontSize: 18, fontWeight: '600' }}>
            Loading session...
          </Text>
        </View>
      );
    }

    if (configError) {
      return (
        <View
          className="flex-1 items-center justify-center bg-bg"
          style={{ paddingHorizontal: 24, gap: 12 }}
        >
          <Text className="text-text-primary" style={{ fontSize: 22, fontWeight: '700', textAlign: 'center' }}>
            App setup incomplete
          </Text>
          <Text className="text-text-primary" style={{ fontSize: 16, textAlign: 'center', lineHeight: 24 }}>
            {configError}
          </Text>
        </View>
      );
    }

    if (
      isHandlingRecoveryLink ||
      isRecoveryMode ||
      passwordRecoveryMode ||
      route === AUTH_ROUTES.resetPasswordForm
    ) {
      return (
        <ResetPasswordFormScreen
          onBack={handleResetPasswordBack}
          onReset={handleResetPasswordSuccess}
          initialErrorMessage={authLinkErrorMessage}
        />
      );
    }

    if (session && user) {
      if (route === AUTH_ROUTES.uploadVideo) {
        return (
          <UploadVideoScreen
            sourceMode={uploadSourceMode}
            initialSelectedVideo={recordedUploadVideo}
            initialVideoSetup={recordedUploadSetup}
            onBack={handleUploadBack}
            onRecordVideoPress={Platform.OS === 'web' ? handleRecordVideoRoute : undefined}
            onAnalysisQueued={handleAnalysisQueued}
            onAnalysisSaved={handleAnalysisSaved}
          />
        );
      }

      if (route === AUTH_ROUTES.webRecordVideo) {
        return (
          <WebVideoRecorderScreen
            onBack={authNavigation.toAddVideo}
            setup={pendingRecordingSetup}
            setupResumeKey={recordingSetupResumeKey}
            onEditSetup={handleEditRecordingSetup}
            onUseRecording={(asset) => handleRecordedVideoAsset(asset, pendingRecordingSetup)}
          />
        );
      }

      if (
        route === AUTH_ROUTES.pendingAnalysisReview
        && pendingAnalysisPlaybackUri
        && pendingAnalysisResult
      ) {
        return (
          <AnalysisReviewScreen
            mode="pending"
            videoUri={pendingAnalysisPlaybackUri}
            result={pendingAnalysisResult}
            onDiscarded={handlePendingAnalysisDiscarded}
            onSaved={handleAnalysisSaved}
          />
        );
      }

      if (
        route === AUTH_ROUTES.savedVideoReview
        && selectedSavedVideo
        && selectedSavedVideoPlaybackUri
        && selectedSavedVideoAnalysisResult
      ) {
        return (
          <AnalysisReviewScreen
            mode="saved"
            videoUri={selectedSavedVideoPlaybackUri}
            result={selectedSavedVideoAnalysisResult}
            workoutDetails={
              selectedSavedVideo.performed_reps !== null
              || (
                selectedSavedVideo.load_value !== null
                && selectedSavedVideo.load_unit !== null
              )
              || Boolean(selectedSavedVideo.user_notes)
                ? {
                    performed_reps: selectedSavedVideo.performed_reps,
                    load_value: selectedSavedVideo.load_value,
                    load_unit: selectedSavedVideo.load_unit,
                    user_notes: selectedSavedVideo.user_notes,
                  }
                : null
            }
            onBack={handleSavedVideoReviewBack}
            onDeleteSavedVideo={handleDeleteSavedVideoFromReview}
          />
        );
      }

      if (route === AUTH_ROUTES.savedLiftVideos && selectedSavedExerciseType) {
        return (
          <SavedLiftVideosScreen
            exerciseType={selectedSavedExerciseType}
            onBack={handleHomeRoute}
            onOpenSavedVideo={handleOpenSavedVideo}
            onDeleteSavedVideos={handleDeleteSavedVideos}
          />
        );
      }

      if (route === AUTH_ROUTES.addVideo) {
        return (
          <AddVideoScreen
            onHomePress={handleHomeRoute}
            onAddPress={authNavigation.toAddVideo}
            onProfilePress={handleProfileRoute}
            onRecordVideoPress={handleRecordVideoRoute}
            onUploadVideoPress={handleUploadVideoRoute}
          />
        );
      }

      if (route === AUTH_ROUTES.profile) {
        return (
          <ProfileScreen
            onHomePress={handleHomeRoute}
            onAddPress={authNavigation.toAddVideo}
            onSettingsPress={authNavigation.toSettings}
            cachedSavedOverview={savedOverview}
            savedOverviewLoaded={savedOverviewLoaded}
            onSavedOverviewLoaded={handleSavedOverviewLoaded}
          />
        );
      }

      if (route === AUTH_ROUTES.settings) {
        return (
          <SettingsScreen
            onBack={handleProfileRoute}
            onHomePress={handleHomeRoute}
            onAddPress={authNavigation.toAddVideo}
            onProfilePress={handleProfileRoute}
            onManageSavedVideos={handleHomeRoute}
            onAccountDeleted={authNavigation.toWelcome}
          />
        );
      }

      return (
        <HomeScreen
          email={user.email}
          refreshKey={homeRefreshKey}
          queuedAnalysisConfirmation={queuedAnalysisConfirmation}
          onQueuedAnalysisConfirmationDismiss={() => setQueuedAnalysisConfirmation(null)}
          onNavigateToAddVideo={authNavigation.toAddVideo}
          onNavigateToProfile={handleProfileRoute}
          onOpenAnalysisActivity={handleOpenAnalysisActivity}
          onOpenSavedLiftFolder={handleOpenSavedLiftFolder}
          cachedSavedOverview={savedOverview}
          savedOverviewLoaded={savedOverviewLoaded}
          onSavedOverviewLoaded={handleSavedOverviewLoaded}
        />
      );
    }

    if (route === AUTH_ROUTES.welcome) {
      return (
        <WelcomeScreen
          onLogin={handleWelcomeLoginPress}
          onCreateAccount={handleWelcomeCreateAccountPress}
        />
      );
    }

    if (route === AUTH_ROUTES.login) {
      return (
        <LoginScreen
          onBack={authNavigation.toWelcome}
          onForgotPassword={authNavigation.toResetPassword}
          initialErrorMessage={authLinkErrorMessage}
        />
      );
    }

    if (route === AUTH_ROUTES.createAccount) {
      return (
        <CreateAccountScreen
          onBack={authNavigation.toWelcome}
        />
      );
    }

    if (route === AUTH_ROUTES.resetPassword) {
      return (
        <ResetPasswordScreen
          onBack={authNavigation.toLogin}
        />
      );
    }

    return (
      <WelcomeScreen
        onLogin={handleWelcomeLoginPress}
        onCreateAccount={handleWelcomeCreateAccountPress}
      />
    );
  })();

  const appContent = (
    <>
      {screenContent}
      {session && user ? (
        <VideoSetupModal
          visible={recordingSetupModalVisible}
          initialSelection={pendingRecordingSetup}
          onContinue={handleRecordingSetupContinue}
          onCancel={handleRecordingSetupCancel}
        />
      ) : null}
    </>
  );

  if (Platform.OS !== 'web') {
    return appContent;
  }

  return (
    <View style={styles.webWrapper}>
      <ScrollView
        style={{ flex: 1, width: '100%' }}
        contentContainerStyle={{
          flexGrow: 1,
          alignItems: 'center',
          paddingTop: 24,
          paddingBottom: 24,
        }}
      >
        <View style={styles.phoneFrame}>
          {appContent}
        </View>
      </ScrollView>
    </View>
  );
}

export default function NativeRoot() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
