import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { AuthChallengeProps } from './AuthChallenge.types';

const turnstileSiteKey = process.env.EXPO_PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? '';

type TurnstileApi = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string;
  remove: (widgetId: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export default function AuthChallenge({
  action,
  resetSignal,
  onTokenChange,
  onError,
}: AuthChallengeProps) {
  const containerRef = useRef<HTMLElement | null>(null);
  const [retrySignal, setRetrySignal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    turnstileSiteKey ? 'loading' : 'error'
  );
  const configurationMissing = !turnstileSiteKey;

  useEffect(() => {
    onTokenChange(null);

    if (configurationMissing) {
      onError(
        'Security verification is not configured for this build. Contact Peso support.'
      );
      setStatus('error');
      return;
    }

    let active = true;
    let widgetId: string | null = null;
    let script: HTMLScriptElement | null = null;

    const fail = (message: string) => {
      if (!active) return;
      onTokenChange(null);
      onError(message);
      setStatus('error');
    };

    const render = () => {
      if (!active || !containerRef.current || !window.turnstile) return;
      containerRef.current.replaceChildren();
      widgetId = window.turnstile.render(containerRef.current, {
        sitekey: turnstileSiteKey,
        action,
        callback: (token: string) => {
          if (!active) return;
          onError(null);
          onTokenChange(token);
          setStatus('ready');
        },
        'expired-callback': () => {
          onTokenChange(null);
          onError('Security check expired. Complete it again.');
          setStatus('ready');
        },
        'error-callback': () => {
          fail('Security verification failed. Retry the security check.');
        },
      });
      onError(null);
      setStatus('ready');
    };

    const existingScript = document.querySelector<HTMLScriptElement>(
      'script[data-peso-turnstile]'
    );

    if (window.turnstile) {
      render();
    } else {
      if (existingScript?.dataset.pesoTurnstileFailed === 'true') {
        existingScript.remove();
      }

      script =
        document.querySelector<HTMLScriptElement>('script[data-peso-turnstile]') ??
        document.createElement('script');

      const onLoad = () => render();
      const onScriptError = () => {
        if (script) script.dataset.pesoTurnstileFailed = 'true';
        fail('Security verification could not load. Check your connection and retry.');
      };

      script.addEventListener('load', onLoad, { once: true });
      script.addEventListener('error', onScriptError, { once: true });

      if (!script.isConnected) {
        script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
        script.async = true;
        script.defer = true;
        script.dataset.pesoTurnstile = 'true';
        document.head.appendChild(script);
      }

      return () => {
        active = false;
        script?.removeEventListener('load', onLoad);
        script?.removeEventListener('error', onScriptError);
        if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
      };
    }

    return () => {
      active = false;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, [action, configurationMissing, onError, onTokenChange, resetSignal, retrySignal]);

  return (
    <View style={styles.root} testID="auth-challenge" accessibilityLabel="Security verification">
      <View ref={containerRef as never} style={styles.widget} />
      {status === 'loading' ? <Text style={styles.status}>Loading security check…</Text> : null}
      {status === 'error' && !configurationMissing ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Retry security check"
          testID="auth-challenge-retry"
          onPress={() => {
            setStatus('loading');
            setRetrySignal((value) => value + 1);
          }}
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
    minHeight: 76,
    justifyContent: 'center',
  },
  widget: {
    minHeight: 65,
  },
  status: {
    color: '#9CA9BF',
    fontSize: 13,
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
