import './global.css';

import { useState } from 'react';
import WelcomeScreen from './src/screens/WelcomeScreen';
import CreateAccountScreen from './src/screens/CreateAccountScreen';
import LoginScreen from './src/screens/LoginScreen';
import ResetPasswordScreen from './src/screens/ResetPasswordScreen';
import ResetPasswordFormScreen from './src/screens/ResetPasswordFormScreen';

export default function App() {
  const [screen, setScreen] = useState<
    'welcome' | 'create-account' | 'login' | 'reset-password' | 'reset-password-form'
  >('welcome');

  if (screen === 'create-account') {
    return <CreateAccountScreen onBack={() => setScreen('welcome')} />;
  }

  if (screen === 'login') {
    return (
      <LoginScreen
        onBack={() => setScreen('welcome')}
        onForgotPassword={() => setScreen('reset-password')}
      />
    );
  }

  if (screen === 'reset-password') {
    return (
      <ResetPasswordScreen
        onBack={() => setScreen('login')}
        onSubmit={() => setScreen('reset-password-form')}
      />
    );
  }

  if (screen === 'reset-password-form') {
    return (
      <ResetPasswordFormScreen
        onBack={() => setScreen('reset-password')}
        onReset={() => setScreen('login')}
      />
    );
  }

  return (
    <WelcomeScreen
      onLogin={() => setScreen('login')}
      onCreateAccount={() => setScreen('create-account')}
    />
  );
}
