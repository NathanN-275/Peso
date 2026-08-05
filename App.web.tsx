import './global.css';

import { ArchivoBlack_400Regular } from '@expo-google-fonts/archivo-black/400Regular';
import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular';
import { Inter_500Medium } from '@expo-google-fonts/inter/500Medium';
import { Inter_600SemiBold } from '@expo-google-fonts/inter/600SemiBold';
import { Inter_700Bold } from '@expo-google-fonts/inter/700Bold';
import { useFonts } from 'expo-font';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { BrowserRouter } from 'react-router';
import { resolveWebRouterBase, resolveWebSurface } from './lib/webSurfacePolicy';
import NativeRoot from './src/native-root';
import WebApp from './src/web/web-app';

const webEnvironment = {
  EXPO_PUBLIC_WEB_SURFACE: process.env.EXPO_PUBLIC_WEB_SURFACE,
  EXPO_PUBLIC_WEB_ROUTER_BASE: process.env.EXPO_PUBLIC_WEB_ROUTER_BASE,
  NODE_ENV: process.env.NODE_ENV,
};

function WebAppRoot() {
  const [fontsLoaded] = useFonts({
    ArchivoBlack_400Regular,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
  });

  if (!fontsLoaded) {
    return (
      <View style={styles.loading} accessibilityLabel="Loading Peso">
        <ActivityIndicator color="#1F6BFF" size="large" />
        <Text style={styles.loadingText}>Loading Peso…</Text>
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <BrowserRouter basename={resolveWebRouterBase(webEnvironment)}>
        <WebApp />
      </BrowserRouter>
    </SafeAreaProvider>
  );
}

export default function App() {
  return resolveWebSurface(webEnvironment) === 'web-app'
    ? <WebAppRoot />
    : <NativeRoot />;
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
