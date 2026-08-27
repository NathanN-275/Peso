(function initializePesoTurnstile() {
  'use strict';

  const root = document.getElementById('peso-turnstile-root');
  const widget = document.getElementById('peso-turnstile-widget');
  const status = document.getElementById('peso-turnstile-status');
  const siteKey = root?.dataset.siteKey?.trim() ?? '';
  const action = new URLSearchParams(window.location.search).get('action') ?? '';
  const allowedActions = new Set(['login', 'signup', 'reset_password']);

  function post(eventStatus, details) {
    const bridge = window.ReactNativeWebView;
    if (!bridge || typeof bridge.postMessage !== 'function') return;

    bridge.postMessage(
      JSON.stringify({
        version: 1,
        type: 'peso.turnstile',
        action,
        status: eventStatus,
        ...(details ?? {}),
      })
    );
  }

  function fail(code, message) {
    if (status) status.textContent = message;
    post('error', { code });
  }

  window.pesoTurnstileReady = function pesoTurnstileReady() {
    if (!root || !widget || !status) return;

    if (!allowedActions.has(action)) {
      fail('invalid-action', 'Security check request is invalid.');
      return;
    }

    if (!siteKey) {
      fail('missing-site-key', 'Security verification is not configured.');
      return;
    }

    if (!window.turnstile) {
      fail('script-load', 'Security verification could not load.');
      return;
    }

    window.turnstile.render(widget, {
      sitekey: siteKey,
      action,
      callback(token) {
        status.textContent = 'Security check complete.';
        post('verified', { token });
      },
      'expired-callback'() {
        status.textContent = 'Security check expired.';
        post('expired');
      },
      'error-callback'() {
        fail('challenge-failed', 'Security verification failed.');
      },
    });

    status.textContent = 'Complete the security check.';
    post('ready');
  };

  window.setTimeout(() => {
    if (!window.turnstile) {
      fail('script-timeout', 'Security verification could not load.');
    }
  }, 12000);
})();
