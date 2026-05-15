import './global.css';

import { useEffect, useRef, useState } from 'react';
import { Linking, LogBox, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider, useAuth } from './context/AuthContext';
import CreateAccountScreen from './src/screens/CreateAccountScreen';
import AddVideoScreen from './src/screens/AddVideoScreen';
import HomeScreen from './src/screens/HomeScreen';
import LoginScreen from './src/screens/LoginScreen';
import ResetPasswordScreen from './src/screens/EmailResetPasswordScreen';
import ResetPasswordFormScreen from './src/screens/ChangePasswordScreen';
import AnalysisReviewScreen from './src/screens/AnalysisReviewScreen';
import SavedLiftVideosScreen from './src/screens/SavedLiftVideosScreen';
import UploadVideoScreen from './src/screens/UploadVideoScreen';
import WelcomeScreen from './src/screens/WelcomeScreen';
import { supabase } from './lib/supabase';
import type { SavedVideo } from './lib/backendApi';
import { buildSavedVideoAnalysisResult } from './src/utils/savedVideos';

LogBox.ignoreLogs([
  "SafeAreaView has been deprecated and will be removed in a future release. Please use 'react-native-safe-area-context' instead.",
]);

// Manual route map for the small auth flow.
const AUTH_ROUTES = {
  home: 'home',
  addVideo: 'add-video',
  uploadVideo: 'upload-video',
  savedLiftVideos: 'saved-lift-videos',
  savedVideoReview: 'saved-video-review',
  welcome: 'welcome',
  login: 'login',
  createAccount: 'create-account',
  resetPassword: 'reset-password',
  resetPasswordForm: 'reset-password-form',
} as const;

type AuthRoute = (typeof AUTH_ROUTES)[keyof typeof AUTH_ROUTES];

type ParsedNativeAuthRoute = {
  route: AuthRoute | null;
  protocol: string | null;
  host: string | null;
  hostname: string | null;
  pathname: string | null;
  search: string | null;
  hash: string | null;
  path: string | null;
  normalizedRoute: string | null;
  queryParams: Record<string, string>;
  hashParams: Record<string, string>;
  code: string | null;
  accessToken: string | null;
  refreshToken: string | null;
  isRecoveryResetLink: boolean;
  hasRecoverySessionParams: boolean;
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
  [AUTH_ROUTES.savedLiftVideos]: '#/saved-lift-videos',
  [AUTH_ROUTES.savedVideoReview]: '#/saved-video-review',
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

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.savedLiftVideos]) {
    return AUTH_ROUTES.savedLiftVideos;
  }

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.savedVideoReview]) {
    return AUTH_ROUTES.savedVideoReview;
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

function parseHashParams(hash: string) {
  // Treat fragment values like query params for reset links.
  const hashValue = hash.startsWith('#') ? hash.slice(1) : hash;
  const hashParamsSource = hashValue.includes('?')
    ? hashValue.slice(hashValue.indexOf('?') + 1)
    : hashValue.includes('=')
      ? hashValue
      : '';

  return new URLSearchParams(hashParamsSource);
}

function parseWebAuthLink(search: string, hash: string): ParsedWebAuthLink {
  // Detect web recovery links before the screen is chosen.
  const searchParams = new URLSearchParams(search);
  const hashParams = parseHashParams(hash);
  const auth = searchParams.get('auth');
  const type = hashParams.get('type');
  const accessToken = hashParams.get('access_token');
  const refreshToken = hashParams.get('refresh_token');
  const code = hashParams.get('code');
  const errorCode = hashParams.get('error_code');
  const errorDescription = hashParams.get('error_description');
  const normalizedErrorDescription = (errorDescription ?? '').toLowerCase();
  const supabaseAuthErrorDetected =
    errorCode === 'otp_expired' ||
    !!errorDescription ||
    normalizedErrorDescription.includes('email link is invalid or has expired');
  const resetRouteDetected =
    auth === AUTH_ROUTES.resetPassword ||
    type === 'recovery' ||
    !!code ||
    !!accessToken ||
    !!refreshToken ||
    supabaseAuthErrorDetected;

  return {
    route: resetRouteDetected ? AUTH_ROUTES.resetPasswordForm : null,
    searchParams: paramsToRecord(searchParams),
    hashParams: paramsToRecord(hashParams),
    resetRouteDetected,
    supabaseAuthErrorDetected,
    errorMessage: supabaseAuthErrorDetected
      ? 'Reset link expired or was already used. Please request a new reset email.'
      : null,
  };
}

function paramsToRecord(params: URLSearchParams) {
  // Convert params into plain objects for logging and state.
  return Array.from(params.entries()).reduce<Record<string, string>>((result, [key, value]) => {
    result[key] = value;
    return result;
  }, {});
}

function redactDeepLinkParams(params: Record<string, string>) {
  // Hide auth tokens from debug output.
  return Object.fromEntries(
    Object.entries(params).map(([key, value]) => {
      if (['access_token', 'refresh_token', 'code'].includes(key)) {
        return [key, value ? '[redacted]' : value];
      }

      return [key, value];
    })
  );
}

function normalizeRouteCandidate(value: string | null | undefined) {
  // Collapse a route candidate into a comparable token.
  if (!value) {
    return '';
  }

  return value
    .toLowerCase()
    .replace(/^\/+|\/+$/g, '')
    .replace(/^#+/g, '')
    .replace(/^\//g, '');
}

function parseNativeAuthRoute(url: string): ParsedNativeAuthRoute {
  // Parse native deep links and recovery callbacks into one shape.
  let parsedUrl: URL;

  try {
    parsedUrl = new URL(url);
  } catch {
    return {
      route: null,
      protocol: null,
      host: null,
      hostname: null,
      pathname: null,
      search: null,
      hash: null,
      path: null,
      normalizedRoute: null,
      queryParams: {},
      hashParams: {},
      code: null,
      accessToken: null,
      refreshToken: null,
      isRecoveryResetLink: false,
      hasRecoverySessionParams: false,
    };
  }

  const protocol = parsedUrl.protocol;
  const host = parsedUrl.host;
  const hostname = parsedUrl.hostname;
  const pathname = parsedUrl.pathname;
  const search = parsedUrl.search;
  const hash = parsedUrl.hash;
  const path = `${hostname}${pathname}`.replace(/\/+$/g, '').toLowerCase();
  const queryParams = new URLSearchParams(parsedUrl.search);
  const hashValue = parsedUrl.hash.startsWith('#') ? parsedUrl.hash.slice(1) : parsedUrl.hash;
  const hashParamsSource = hashValue.includes('?') ? hashValue.slice(hashValue.indexOf('?') + 1) : hashValue;
  const hashParams = new URLSearchParams(hashParamsSource);
  const type = queryParams.get('type') ?? hashParams.get('type');
  const code = queryParams.get('code') ?? hashParams.get('code');
  const accessToken = queryParams.get('access_token') ?? hashParams.get('access_token');
  const refreshToken = queryParams.get('refresh_token') ?? hashParams.get('refresh_token');
  const normalizedUrl = url.toLowerCase();
  const routeCandidates = [
    normalizeRouteCandidate(host),
    normalizeRouteCandidate(hostname),
    normalizeRouteCandidate(pathname),
    normalizeRouteCandidate(path),
    normalizeRouteCandidate(`${hostname}/${pathname}`),
    normalizedUrl.includes('reset-password-form')
      ? 'reset-password-form'
      : normalizedUrl.includes('reset-password')
        ? 'reset-password'
        : '',
  ];
  const normalizedRoute =
    routeCandidates.find(
      (candidate) => candidate === 'reset-password' || candidate === 'reset-password-form'
    ) ?? null;
  const isResetPasswordPath = !!normalizedRoute;
  const hasRecoveryParams =
    type === 'recovery' || !!code || (!!accessToken && !!refreshToken);
  const isRecoveryResetLink = isResetPasswordPath || hasRecoveryParams;
  const hasRecoverySessionParams = !!code || (!!accessToken && !!refreshToken);

  return {
    route: isRecoveryResetLink ? AUTH_ROUTES.resetPasswordForm : null,
    protocol,
    host,
    hostname,
    pathname,
    search,
    hash,
    path,
    normalizedRoute,
    queryParams: paramsToRecord(queryParams),
    hashParams: paramsToRecord(hashParams),
    code,
    accessToken,
    refreshToken,
    isRecoveryResetLink,
    hasRecoverySessionParams,
  };
}

async function hydrateRecoverySession(parsedRoute: ParsedNativeAuthRoute) {
  // Load the Supabase recovery session before showing the form.
  if (!parsedRoute.isRecoveryResetLink || !supabase) {
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
      const webAuthLink = parseWebAuthLink(window.location.search, window.location.hash);

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
  const [webResetErrorMessage, setWebResetErrorMessage] = useState<string | null>(() => {
    if (Platform.OS !== 'web') {
      return null;
    }

    return parseWebAuthLink(window.location.search, window.location.hash).errorMessage;
  });
  const [homeRefreshKey, setHomeRefreshKey] = useState(0);
  const [savedVideos, setSavedVideos] = useState<SavedVideo[]>([]);
  const [selectedSavedExerciseType, setSelectedSavedExerciseType] = useState<string | null>(null);
  const [selectedSavedVideo, setSelectedSavedVideo] = useState<SavedVideo | null>(null);
  const routeRef = useRef(route);
  const hadSessionRef = useRef(false);

  useEffect(() => {
    // Keep the current route in a ref for async deep-link handlers.
    routeRef.current = route;
  }, [route]);

  useEffect(() => {
    // Native links are parsed here so recovery sessions can be hydrated early.
    if (Platform.OS === 'web') {
      return;
    }

    const handleUrl = async (url: string | null, source: 'initial' | 'runtime') => {
      // Route both initial and runtime URLs through the same parser.
      if (!url) {
        console.log(`[DeepLink] raw ${source} URL`, url);
        console.log('[DeepLink] final route chosen', routeRef.current);
        return;
      }

      console.log(`[DeepLink] raw ${source} URL`, url);
      const parsedRoute = parseNativeAuthRoute(url);
      const nextRoute = parsedRoute.route;

      console.log('[DeepLink] parsed URL parts', {
        protocol: parsedRoute.protocol,
        host: parsedRoute.host,
        hostname: parsedRoute.hostname,
        pathname: parsedRoute.pathname,
        search: parsedRoute.search,
        hash: parsedRoute.hash,
      });
      console.log('[DeepLink] normalized route', parsedRoute.normalizedRoute);
      console.log('[DeepLink] parsed query/hash params', {
        queryParams: redactDeepLinkParams(parsedRoute.queryParams),
        hashParams: redactDeepLinkParams(parsedRoute.hashParams),
      });
      console.log('[DeepLink] recovery detected', parsedRoute.isRecoveryResetLink);
      console.log('[DeepLink] recovery session detected', parsedRoute.hasRecoverySessionParams);
      if (nextRoute) {
        if (parsedRoute.isRecoveryResetLink) {
          console.log('[Recovery] mode on', { reason: 'deep-link-detected' });
          setIsHandlingRecoveryLink(true);
          setIsRecoveryMode(true);
          setRecoverySessionReady(false);
          activatePasswordRecoveryMode();
          setRoute(AUTH_ROUTES.resetPasswordForm);
        }

        try {
          const exchangeMethod = await hydrateRecoverySession(parsedRoute);
          console.log('[Recovery] session exchange success', { method: exchangeMethod });

          if (supabase) {
            const {
              data: { session: currentSession },
            } = await supabase.auth.getSession();
            const hasSession = !!currentSession;

            setRecoverySessionReady(hasSession);
            console.log('[Recovery] getSession after exchange', { hasSession });
          }
        } catch (error) {
          setRecoverySessionReady(false);
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
    toWelcome: () => navigateToAuthRoute(AUTH_ROUTES.welcome),
    toLogin: () => navigateToAuthRoute(AUTH_ROUTES.login),
    toCreateAccount: () => navigateToAuthRoute(AUTH_ROUTES.createAccount),
    toResetPassword: () => navigateToAuthRoute(AUTH_ROUTES.resetPassword),
    toResetPasswordForm: () => navigateToAuthRoute(AUTH_ROUTES.resetPasswordForm),
  };
  const handleAnalysisSaved = () => {
    setHomeRefreshKey((key) => key + 1);
    authNavigation.toHome();
  };
  const handleOpenSavedLiftFolder = (exerciseType: string) => {
    setSelectedSavedExerciseType(exerciseType);
    setSelectedSavedVideo(null);
    navigateToAuthRoute(AUTH_ROUTES.savedLiftVideos);
  };
  const handleOpenSavedVideo = (video: SavedVideo) => {
    setSelectedSavedVideo(video);
    setSelectedSavedExerciseType(video.exercise_type);
    navigateToAuthRoute(AUTH_ROUTES.savedVideoReview);
  };
  const handleSavedVideoReviewBack = () => {
    navigateToAuthRoute(selectedSavedExerciseType ? AUTH_ROUTES.savedLiftVideos : AUTH_ROUTES.home);
  };
  const handleHomeRoute = () => {
    setSelectedSavedExerciseType(null);
    setSelectedSavedVideo(null);
    authNavigation.toHome();
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
      const parsedWebLink = parseWebAuthLink(window.location.search, window.location.hash);

      console.log('[WebDeepLink] full window.location.href', window.location.href);
      console.log('[WebDeepLink] search params', parsedWebLink.searchParams);
      console.log('[WebDeepLink] hash params', redactDeepLinkParams(parsedWebLink.hashParams));
      console.log('[WebDeepLink] reset route detected', parsedWebLink.resetRouteDetected);
      console.log('[WebDeepLink] Supabase auth error detected', parsedWebLink.supabaseAuthErrorDetected);

      setWebResetErrorMessage(parsedWebLink.errorMessage);

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
        route !== AUTH_ROUTES.savedLiftVideos &&
        route !== AUTH_ROUTES.savedVideoReview &&
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
      route === AUTH_ROUTES.savedLiftVideos ||
      route === AUTH_ROUTES.savedVideoReview
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
          initialErrorMessage={webResetErrorMessage}
        />
      );
    }

    if (session && user) {
      if (route === AUTH_ROUTES.uploadVideo) {
        return <UploadVideoScreen onBack={authNavigation.toAddVideo} onAnalysisSaved={handleAnalysisSaved} />;
      }

      if (route === AUTH_ROUTES.savedVideoReview && selectedSavedVideo) {
        return (
          <AnalysisReviewScreen
            mode="saved"
            videoUri={selectedSavedVideo.video_url}
            result={buildSavedVideoAnalysisResult(selectedSavedVideo)}
            onBack={handleSavedVideoReviewBack}
          />
        );
      }

      if (route === AUTH_ROUTES.savedLiftVideos && selectedSavedExerciseType) {
        const selectedVideos = savedVideos.filter(
          (video) => video.exercise_type === selectedSavedExerciseType
        );

        return (
          <SavedLiftVideosScreen
            exerciseType={selectedSavedExerciseType}
            videos={selectedVideos}
            onBack={handleHomeRoute}
            onOpenSavedVideo={handleOpenSavedVideo}
            onHomePress={handleHomeRoute}
            onAddPress={authNavigation.toAddVideo}
          />
        );
      }

      if (route === AUTH_ROUTES.addVideo) {
        return (
          <AddVideoScreen
            onHomePress={handleHomeRoute}
            onAddPress={authNavigation.toAddVideo}
            onUploadVideoPress={authNavigation.toUploadVideo}
          />
        );
      }

      return (
        <HomeScreen
          email={user.email}
          refreshKey={homeRefreshKey}
          onNavigateToAddVideo={authNavigation.toAddVideo}
          onOpenSavedLiftFolder={handleOpenSavedLiftFolder}
          onSavedVideosLoaded={setSavedVideos}
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

  if (Platform.OS !== 'web') {
    return screenContent;
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
          {screenContent}
        </View>
      </ScrollView>
    </View>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </SafeAreaProvider>
  );
}
