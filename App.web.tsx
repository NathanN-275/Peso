import './global.css';

import { lazy, Suspense } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { BrowserRouter } from 'react-router';
import { resolveWebRouterBase, resolveWebSurface } from './lib/webSurfacePolicy';
import { AuthProvider } from './context/AuthContext';
import WebApp from './src/web/web-app';

const NativeRoot = lazy(() => import('./src/native-root'));

const webEnvironment = {
  EXPO_PUBLIC_WEB_SURFACE: process.env.EXPO_PUBLIC_WEB_SURFACE,
  EXPO_PUBLIC_WEB_ROUTER_BASE: process.env.EXPO_PUBLIC_WEB_ROUTER_BASE,
  NODE_ENV: process.env.NODE_ENV,
};

function WebAppRoot() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <BrowserRouter basename={resolveWebRouterBase(webEnvironment)}>
          <WebApp />
        </BrowserRouter>
      </AuthProvider>
    </SafeAreaProvider>
  );
}

export default function App() {
  return resolveWebSurface(webEnvironment) === 'web-app'
    ? <WebAppRoot />
    : (
      <Suspense fallback={<WebLoading />}>
        <NativeRoot />
      </Suspense>
    );
}

function WebLoading() {
  return (
    <View style={styles.loading} accessibilityLabel="Loading Peso">
      <ActivityIndicator color="#1F6BFF" size="large" />
      <Text style={styles.loadingText}>Loading Peso…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    minHeight: 640,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
    backgroundColor: '#07090D',
  },
  loadingText: {
    color: '#A7B3C7',
    fontFamily: 'Inter_600SemiBold',
    fontSize: 14,
  },
});
