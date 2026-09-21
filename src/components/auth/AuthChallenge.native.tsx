import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';
import {
  buildAuthChallengeUrl,
  isTrustedAuthChallengeMessageSource,
  isTrustedAuthChallengeNavigation,
  parseAuthChallengeMessage,
} from '../../../lib/auth-challenge';
import type { AuthChallengeProps } from './AuthChallenge.types';

const configuredChallengeUrl =
  process.env.EXPO_PUBLIC_AUTH_CHALLENGE_URL?.trim() ?? '';

function challengeOrigin() {
  try {
    return new URL(configuredChallengeUrl).origin;
  } catch {
    return null;
  }
}

export default function AuthChallenge({
  action,
  resetSignal,
  onTokenChange,
  onError: reportError,
}: AuthChallengeProps) {
  const [retrySignal, setRetrySignal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const origin = challengeOrigin();
  const sourceUrl = useMemo(() => {
    if (!configuredChallengeUrl) return null;
    return buildAuthChallengeUrl(
      configuredChallengeUrl,
      action,
      resetSignal + retrySignal
    );
  }, [action, resetSignal, retrySignal]);

  useEffect(() => {
    onTokenChange(null);
    setStatus('loading');

    if (!sourceUrl || !origin) {
      reportError(
        'Security verification is not configured for this build. Contact Peso support.'
      );
      setStatus('error');
    }
  }, [action, onTokenChange, origin, reportError, sourceUrl]);

  if (!sourceUrl || !origin) {
    return (
      <View
        style={styles.root}
        testID="auth-challenge"
        accessibilityLabel="Security verification unavailable"
      >
        <Text style={styles.error}>Security verification is unavailable.</Text>
      </View>
    );
  }

  return (
    <View style={styles.root} testID="auth-challenge" accessibilityLabel="Security verification">
      <WebView
        key={sourceUrl}
        source={{ uri: sourceUrl }}
        originWhitelist={[origin, 'about:blank', 'about:srcdoc']}
        javaScriptEnabled
        domStorageEnabled
        sharedCookiesEnabled
        thirdPartyCookiesEnabled
        setSupportMultipleWindows={false}
        testID="auth-challenge-webview"
        onShouldStartLoadWithRequest={(request) =>
          isTrustedAuthChallengeNavigation(request.url, configuredChallengeUrl)
        }
        onMessage={(event) => {
          if (
            !isTrustedAuthChallengeMessageSource(
              event.nativeEvent.url,
              configuredChallengeUrl
            )
          ) {
            onTokenChange(null);
            reportError('Security verification returned an untrusted response. Retry the check.');
            setStatus('error');
            return;
          }

          const result = parseAuthChallengeMessage(event.nativeEvent.data, action);
          if (!result.ok) {
            onTokenChange(null);
            reportError('Security verification returned an invalid response. Retry the check.');
            setStatus('error');
            return;
          }

          if (result.event.status === 'verified') {
            reportError(null);
            onTokenChange(result.event.token);
            setStatus('ready');
          } else if (result.event.status === 'ready') {
            reportError(null);
            setStatus('ready');
          } else if (result.event.status === 'expired') {
            onTokenChange(null);
            reportError('Security check expired. Complete it again.');
            setStatus('ready');
          } else {
            onTokenChange(null);
            reportError('Security verification failed. Retry the security check.');
            setStatus('error');
          }
        }}
        onError={() => {
          onTokenChange(null);
          reportError('Security verification could not load. Check your connection and retry.');
          setStatus('error');
        }}
        onHttpError={() => {
          onTokenChange(null);
          reportError('Security verification could not load. Check your connection and retry.');
          setStatus('error');
        }}
        style={styles.webView}
      />
      {status === 'loading' ? <Text style={styles.status}>Loading security check…</Text> : null}
      {status === 'error' ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Retry security check"
          testID="auth-challenge-retry"
          onPress={() => setRetrySignal((value) => value + 1)}
          style={styles.retry}
        >
          <Text style={styles.retryText}>Retry security check</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    minHeight: 92,
    justifyContent: 'center',
  },
  webView: {
    minHeight: 72,
    backgroundColor: 'transparent',
  },
  status: {
    color: '#A6A6A6',
    fontSize: 13,
    marginTop: 4,
  },
  error: {
    color: '#FF8A8A',
    fontSize: 14,
  },
  retry: {
    alignSelf: 'flex-start',
    paddingVertical: 8,
  },
  retryText: {
    color: '#82AEFF',
    fontSize: 14,
    fontWeight: '700',
    textDecorationLine: 'underline',
  },
});
