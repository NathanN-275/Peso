import './global.css';

import { useEffect, useRef, useState } from 'react';
import { Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AuthProvider, useAuth } from './context/AuthContext';
import CreateAccountScreen from './src/screens/CreateAccountScreen';
import HomeScreen from './src/screens/HomeScreen';
import LoginScreen from './src/screens/LoginScreen';
import ResetPasswordScreen from './src/screens/ResetPasswordScreen';
import ResetPasswordFormScreen from './src/screens/ResetPasswordFormScreen';
import WelcomeScreen from './src/screens/WelcomeScreen';

const AUTH_ROUTES = {
  home: 'home',
  welcome: 'welcome',
  login: 'login',
  createAccount: 'create-account',
  resetPassword: 'reset-password',
  resetPasswordForm: 'reset-password-form',
} as const;

type AuthRoute = (typeof AUTH_ROUTES)[keyof typeof AUTH_ROUTES];

const WEB_ROUTE_HASHES: Record<AuthRoute, string> = {
  [AUTH_ROUTES.home]: '#/home',
  [AUTH_ROUTES.welcome]: '#/welcome',
  [AUTH_ROUTES.login]: '#/login',
  [AUTH_ROUTES.createAccount]: '#/create-account',
  [AUTH_ROUTES.resetPassword]: '#/reset-password',
  [AUTH_ROUTES.resetPasswordForm]: '#/reset-password-form',
};

const styles = StyleSheet.create({
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
  const normalizedHash = hash.toLowerCase();

  if (normalizedHash === WEB_ROUTE_HASHES[AUTH_ROUTES.home]) {
    return AUTH_ROUTES.home;
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

function AppContent() {
  const { session, user, initializing, configError } = useAuth();
  const [route, setRoute] = useState<AuthRoute>(() => {
    if (Platform.OS === 'web') {
      return parseWebAuthRoute(window.location.hash);
    }

    return AUTH_ROUTES.welcome;
  });
  const hadSessionRef = useRef(false);

  const navigateToAuthRoute = (nextRoute: AuthRoute) => {
    if (Platform.OS === 'web') {
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
    toWelcome: () => navigateToAuthRoute(AUTH_ROUTES.welcome),
    toLogin: () => navigateToAuthRoute(AUTH_ROUTES.login),
    toCreateAccount: () => navigateToAuthRoute(AUTH_ROUTES.createAccount),
    toResetPassword: () => navigateToAuthRoute(AUTH_ROUTES.resetPassword),
    toResetPasswordForm: () => navigateToAuthRoute(AUTH_ROUTES.resetPasswordForm),
  };
  const handleWelcomeLoginPress = authNavigation.toLogin;
  const handleWelcomeCreateAccountPress = authNavigation.toCreateAccount;

  useEffect(() => {
    if (Platform.OS !== 'web') {
      return;
    }

    const handleHashChange = () => {
      setRoute(parseWebAuthRoute(window.location.hash));
    };

    window.addEventListener('hashchange', handleHashChange);

    return () => {
      window.removeEventListener('hashchange', handleHashChange);
    };
  }, []);

  useEffect(() => {
    if (session) {
      hadSessionRef.current = true;
      return;
    }

    if (hadSessionRef.current) {
      authNavigation.toWelcome();
      hadSessionRef.current = false;
    }
  }, [session]);

  const screenContent = (() => {
    if (initializing) {
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

    if (session && user) {
      return <HomeScreen email={user.email} />;
    }

    if (route === AUTH_ROUTES.home) {
      return <HomeScreen email={user?.email ?? null} />;
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
          onSuccess={authNavigation.toHome}
        />
      );
    }

    if (route === AUTH_ROUTES.createAccount) {
      return (
        <CreateAccountScreen
          onBack={authNavigation.toWelcome}
          onSuccess={authNavigation.toHome}
        />
      );
    }

    if (route === AUTH_ROUTES.resetPassword) {
      return (
        <ResetPasswordScreen
          onBack={authNavigation.toLogin}
          onSubmit={authNavigation.toResetPasswordForm}
        />
      );
    }

    if (route === AUTH_ROUTES.resetPasswordForm) {
      return (
        <ResetPasswordFormScreen
          onBack={authNavigation.toResetPassword}
          onReset={authNavigation.toLogin}
        />
      );
    }

    return null;
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
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
