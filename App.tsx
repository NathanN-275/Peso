import './global.css';

import { useEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import { AuthProvider, useAuth } from './context/AuthContext';
import Button from './src/components/Button';
import CreateAccountScreen from './src/screens/CreateAccountScreen';
import LoginScreen from './src/screens/LoginScreen';
import ResetPasswordScreen from './src/screens/ResetPasswordScreen';
import ResetPasswordFormScreen from './src/screens/ResetPasswordFormScreen';
import WelcomeScreen from './src/screens/WelcomeScreen';

type AuthRoute =
  | 'welcome'
  | 'login'
  | 'create-account'
  | 'reset-password'
  | 'reset-password-form';

const WEB_ROUTE_HASHES: Record<AuthRoute, string> = {
  welcome: '#/welcome',
  login: '#/login',
  'create-account': '#/create-account',
  'reset-password': '#/reset-password',
  'reset-password-form': '#/reset-password-form',
};

function parseWebAuthRoute(hash: string): AuthRoute {
  const normalizedHash = hash.toLowerCase();

  if (normalizedHash === WEB_ROUTE_HASHES.login) {
    return 'login';
  }

  if (normalizedHash === WEB_ROUTE_HASHES['create-account']) {
    return 'create-account';
  }

  if (normalizedHash === WEB_ROUTE_HASHES['reset-password']) {
    return 'reset-password';
  }

  if (normalizedHash === WEB_ROUTE_HASHES['reset-password-form']) {
    return 'reset-password-form';
  }

  return 'welcome';
}

function HomeScreen({
  email,
  onSignOut,
}: {
  email: string | null | undefined;
  onSignOut: () => Promise<void>;
}) {
  return (
    <View
      className="flex-1 items-center justify-center bg-bg"
      style={{ paddingHorizontal: 24, gap: 16 }}
    >
      <Text className="text-text-primary" style={{ fontSize: 24, fontWeight: '700' }}>
        Signed in
      </Text>
      <Text className="text-text-primary" style={{ fontSize: 16, textAlign: 'center' }}>
        {email ?? 'Your account is active.'}
      </Text>
      <Button label="Sign Out" onPress={() => void onSignOut()} />
    </View>
  );
}

function AppContent() {
  const { session, user, initializing, configError, signOut } = useAuth();
  const [route, setRoute] = useState<AuthRoute>(() => {
    if (Platform.OS === 'web') {
      return parseWebAuthRoute(window.location.hash);
    }

    return 'welcome';
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
      navigateToAuthRoute('welcome');
      hadSessionRef.current = false;
    }
  }, [session]);

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
    return <HomeScreen email={user.email} onSignOut={signOut} />;
  }

  if (route === 'welcome') {
    return (
      <WelcomeScreen
        onLogin={() => navigateToAuthRoute('login')}
        onCreateAccount={() => navigateToAuthRoute('create-account')}
      />
    );
  }

  if (route === 'login') {
    return (
      <LoginScreen
        onBack={() => setRoute('welcome')}
        onForgotPassword={() => setRoute('reset-password')}
      />
    );
  }

  if (route === 'create-account') {
    return <CreateAccountScreen onBack={() => setRoute('welcome')} />;
  }

  if (route === 'reset-password') {
    return (
      <ResetPasswordScreen
        onBack={() => setRoute('login')}
        onSubmit={() => setRoute('reset-password-form')}
      />
    );
  }

  if (route === 'reset-password-form') {
    return (
      <ResetPasswordFormScreen
        onBack={() => setRoute('reset-password')}
        onReset={() => setRoute('login')}
      />
    );
  }

  return null;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
