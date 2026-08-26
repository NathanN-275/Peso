import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  useWindowDimensions,
  View,
  type ImageSourcePropType,
  type ImageStyle,
  type ViewStyle,
} from 'react-native';
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router';
import tokens from '../theme/tokens';
import { useAuth } from '../../context/AuthContext';
import { parseWebAuthRedirect } from '../../lib/auth-redirect';
import {
  createSavedLiftExport,
  deleteSavedLifts,
  getSavedLiftExport,
  getSavedVideoPlaybackUrl,
  getSavedVideos,
} from '../../lib/backendApi';
import { readSidebarCollapsed, writeSidebarCollapsed } from '../../lib/sidebarPreferencePolicy';
import {
  normalizeSavedLiftView,
  pruneSavedLiftSelection,
  selectVisibleSavedLifts,
  toggleSavedLiftSelection,
  type SavedLiftView,
} from '../../lib/savedLiftSelectionPolicy';
import type { SavedLiftExportJob, SavedVideo, VideoAnalysisRep } from '../types/videoAnalysis';
import {
  WebAnalysisActivityProvider,
  useWebAnalysisActivity,
} from './web-analysis-activity';
import {
  WebProcessingRoute,
  WebRecordRoute,
  WebReviewRoute,
  WebSubmissionChoiceRoute,
  WebUploadRoute,
  WebVideoSetupRoute,
} from './web-analysis-routes';
import AuthChallenge from '../components/auth/AuthChallenge';

const colors = {
  ...tokens.colors,
  page: '#07090D',
  surface: '#0E131C',
  surfaceRaised: '#131A26',
  line: '#242F40',
  blueSoft: '#102653',
  blueText: '#8AB2FF',
  green: '#51E49B',
  greenSoft: '#0B2B20',
  amber: '#F4C76B',
  amberSoft: '#2D220D',
  red: '#FF7A8A',
  redSoft: '#32131A',
};

const fonts = {
  display: 'ArchivoBlack_400Regular',
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
};

function currentWebAuthLinkError() {
  if (typeof window === 'undefined') {
    return null;
  }

  return parseWebAuthRedirect(
    window.location.pathname,
    window.location.search,
    window.location.hash
  ).errorMessage;
}

const previewImageAsset = require('../../assets/demo/peso-pose-overlay.jpg') as number;
const previewImage = previewImageAsset as ImageSourcePropType;
const logoImage = require('../../assets/peso-logo.png') as ImageSourcePropType;
const SAVED_LIFT_CACHE_TTL_MS = 60_000;

let savedLiftLibraryCache: {
  userId: string;
  lifts: SavedVideo[];
  expiresAt: number;
} | null = null;

function invalidateSavedLiftLibraryCache() {
  savedLiftLibraryCache = null;
}

function getCachedSavedLifts(userId?: string): SavedVideo[] | null {
  const cache = savedLiftLibraryCache;
  return cache && cache.userId === userId && cache.expiresAt > Date.now()
    ? cache.lifts
    : null;
}

function formatTime(seconds: number | null) {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, seconds ?? 0) : 0;
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = Math.floor(safeSeconds % 60);
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

function titleCase(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatSavedDate(value: string | null) {
  if (!value) return 'Date unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function savedLiftRepCount(lift: SavedVideo) {
  if (lift.performed_reps) return lift.performed_reps;
  const detected = lift.analysis?.result_json.rep_count;
  return typeof detected === 'number' ? detected : lift.analysis?.rep_data.length ?? 0;
}

function savedLiftLoad(lift: SavedVideo) {
  const value = lift.load_value ?? lift.weight;
  const unit = lift.load_unit ?? lift.weight_unit;
  return value !== null && value !== undefined && unit ? `${value} ${unit}` : 'Load not recorded';
}

function exportFailureMessage(code: string | null) {
  if (code === 'archive_too_large') return 'This selection is too large for one export bundle.';
  if (code === 'capacity_unavailable') return 'Export capacity is busy. Try again in a moment.';
  if (code === 'lift_unavailable') return 'One or more selected Saved Lifts are no longer exportable.';
  if (code === 'archive_missing') return 'The temporary export archive is no longer available.';
  return 'Peso could not prepare this export. Try again.';
}

type ActionButtonProps = {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger' | 'quiet';
  disabled?: boolean;
  compact?: boolean;
};

function ActionButton({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  compact = false,
}: ActionButtonProps) {
  const variantStyle =
    variant === 'secondary'
      ? styles.buttonSecondary
      : variant === 'danger'
        ? styles.buttonDanger
        : variant === 'quiet'
          ? styles.buttonQuiet
          : styles.buttonPrimary;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        variantStyle,
        compact && styles.buttonCompact,
        pressed && !disabled && styles.buttonPressed,
        disabled && styles.buttonDisabled,
      ]}
    >
      <Text style={[styles.buttonText, variant === 'quiet' && styles.buttonQuietText]}>{label}</Text>
    </Pressable>
  );
}

function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <View style={[styles.wordmark, compact && styles.wordmarkCompact]} accessibilityLabel="Peso">
      <Image
        source={logoImage}
        accessibilityIgnoresInvertColors
        style={(compact ? styles.wordmarkImageCompact : styles.wordmarkImage) as ImageStyle}
      />
    </View>
  );
}

function AuthLayout({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  const navigate = useNavigate();
  const { width } = useWindowDimensions();

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      style={styles.authPage}
      contentContainerStyle={styles.authPageContent}
      keyboardShouldPersistTaps="handled"
    >
      <View style={[styles.authFrame, width < 760 && styles.authFrameMobile]}>
        <View style={[styles.authAside, width < 760 && styles.authAsideMobile]}>
          <Pressable accessibilityRole="link" onPress={() => window.location.assign('/')}>
            <Wordmark />
          </Pressable>
          <View style={styles.authAsideCopy}>
            <Text selectable style={styles.authAsideTitle}>A clearer view of your next set.</Text>
            <Text selectable style={styles.authAsideBody}>
              Record or upload one squat set and explore Peso’s visual feedback prototype.
            </Text>
          </View>
          <Text selectable style={styles.authAsideFine}>Free US beta · Squats only</Text>
        </View>
        <View style={styles.authPanel}>
          <Text selectable style={styles.eyebrow}>{eyebrow}</Text>
          <Text accessibilityRole="header" selectable style={styles.authTitle}>{title}</Text>
          <Text selectable style={styles.authDescription}>{description}</Text>
          <View style={styles.form}>{children}</View>
          <Pressable
            accessibilityRole="link"
            accessibilityLabel="Return to Peso home page"
            onPress={() => window.location.assign('/')}
            style={styles.authBackLink}
          >
            <Text style={styles.inlineLink}>← Back to peso home</Text>
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}

function Field({
  label,
  placeholder,
  secureTextEntry = false,
  value,
  onChangeText,
}: {
  label: string;
  placeholder: string;
  secureTextEntry?: boolean;
  value?: string;
  onChangeText?: (value: string) => void;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        autoCapitalize="none"
        placeholder={placeholder}
        placeholderTextColor="#66738A"
        secureTextEntry={secureTextEntry}
        value={value}
        onChangeText={onChangeText}
        style={styles.input}
      />
    </View>
  );
}

function CheckRow({ checked, label, onPress }: { checked: boolean; label: React.ReactNode; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={onPress}
      style={styles.checkRow}
    >
      <View style={[styles.checkbox, checked && styles.checkboxChecked]}>
        {checked && <Text style={styles.checkboxMark}>✓</Text>}
      </View>
      <Text style={styles.checkLabel}>{label}</Text>
    </Pressable>
  );
}

function LoginScreen() {
  const navigate = useNavigate();
  const { session, signInWithEmail, configError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(currentWebAuthLinkError);
  const [submitting, setSubmitting] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaError, setCaptchaError] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);

  useEffect(() => {
    if (session) navigate('/', { replace: true });
  }, [navigate, session]);

  const signIn = async () => {
    if (!captchaToken) {
      setError('Complete the security check and try again.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await signInWithEmail(email.trim(), password, captchaToken);
      navigate('/', { replace: true });
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : 'Unable to sign in.');
    } finally {
      setSubmitting(false);
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
    }
  };

  return (
    <AuthLayout eyebrow="Welcome back" title="Sign in to Peso" description="Use the same account as the mobile app.">
      <Field label="Email" placeholder="you@example.com" value={email} onChangeText={setEmail} />
      <Field label="Password" placeholder="Enter your password" secureTextEntry value={password} onChangeText={setPassword} />
      <View style={styles.turnstileFixture} accessibilityLabel="Turnstile verification">
        <Text style={styles.turnstileTitle}>Security check</Text>
        <AuthChallenge action="login" resetSignal={captchaReset} onTokenChange={setCaptchaToken} onError={setCaptchaError} />
      </View>
      {(error || captchaError || configError) && <Text selectable style={styles.formError}>{error ?? captchaError ?? configError}</Text>}
      <Pressable accessibilityRole="link" onPress={() => navigate('/reset')}>
        <Text style={styles.inlineLink}>Forgot password?</Text>
      </Pressable>
      <ActionButton label={submitting ? 'Signing in…' : error ? 'Retry sign in' : 'Sign in'} disabled={submitting || !email.trim() || !password || !captchaToken} onPress={() => void signIn()} />
      <View style={styles.formFooterRow}>
        <Text style={styles.mutedText}>New to Peso?</Text>
        <Pressable accessibilityRole="link" onPress={() => navigate('/signup')}>
          <Text style={styles.inlineLink}>Create an account</Text>
        </Pressable>
      </View>
    </AuthLayout>
  );
}

function SignupScreen() {
  const navigate = useNavigate();
  const { signUpWithEmail, configError } = useAuth();
  const [usResident, setUsResident] = useState(false);
  const [terms, setTerms] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaError, setCaptchaError] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);

  const signUp = async () => {
    if (!captchaToken) {
      setError('Complete the security check and try again.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const result = await signUpWithEmail(email.trim(), password, undefined, captchaToken);
      navigate(result.requiresEmailConfirmation ? '/verify' : '/', { replace: true });
    } catch (signUpError) {
      setError(signUpError instanceof Error ? signUpError.message : 'Unable to create account.');
    } finally {
      setSubmitting(false);
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
    }
  };

  return (
    <AuthLayout eyebrow="Limited beta" title="Create your account" description="The web beta is free and currently available to US residents.">
      <Field label="Email" placeholder="you@example.com" value={email} onChangeText={setEmail} />
      <Field label="Password" placeholder="At least 8 characters" secureTextEntry value={password} onChangeText={setPassword} />
      <CheckRow checked={usResident} onPress={() => setUsResident(!usResident)} label="I confirm that I reside in the United States." />
      <CheckRow checked={terms} onPress={() => setTerms(!terms)} label="I agree to the beta Terms and acknowledge the Privacy Policy." />
      <View style={styles.turnstileFixture} accessibilityLabel="Turnstile verification">
        <Text style={styles.turnstileTitle}>Security check</Text>
        <AuthChallenge action="signup" resetSignal={captchaReset} onTokenChange={setCaptchaToken} onError={setCaptchaError} />
      </View>
      {(error || captchaError || configError) && <Text selectable style={styles.formError}>{error ?? captchaError ?? configError}</Text>}
      <ActionButton label={submitting ? 'Creating account…' : error ? 'Retry account creation' : 'Create account'} disabled={submitting || !email.trim() || password.length < 8 || !usResident || !terms || !captchaToken} onPress={() => void signUp()} />
      <View style={styles.formFooterRow}>
        <Text style={styles.mutedText}>Already have an account?</Text>
        <Pressable accessibilityRole="link" onPress={() => navigate('/login')}>
          <Text style={styles.inlineLink}>Sign in</Text>
        </Pressable>
      </View>
    </AuthLayout>
  );
}

function VerifyScreen() {
  const navigate = useNavigate();
  return (
    <AuthLayout eyebrow="Check your inbox" title="Verify your email" description="Open the verification link sent to your email address.">
      <View style={styles.messageCard}>
        <Text selectable style={styles.messageCardTitle}>Email verification is required</Text>
        <Text selectable style={styles.messageCardBody}>After verification, return here and sign in with the same Peso Account.</Text>
      </View>
      <ActionButton label="Continue to sign in" onPress={() => navigate('/login')} />
    </AuthLayout>
  );
}

function ResetScreen() {
  const navigate = useNavigate();
  const { resetPasswordForEmail, updatePassword, passwordRecoveryMode, configError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(currentWebAuthLinkError);
  const [submitting, setSubmitting] = useState(false);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);
  const [captchaError, setCaptchaError] = useState<string | null>(null);
  const [captchaReset, setCaptchaReset] = useState(0);

  const reset = async () => {
    if (!captchaToken) {
      setError('Complete the security check and try again.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await resetPasswordForEmail(email.trim(), captchaToken);
      setMessage('If an account exists for this email, check your inbox for a secure reset link.');
    } catch (resetError) {
      setError(resetError instanceof Error ? resetError.message : 'Unable to send a reset link.');
    } finally {
      setSubmitting(false);
      setCaptchaToken(null);
      setCaptchaReset((value) => value + 1);
    }
  };

  const completeRecovery = async () => {
    if (password.length < 8) {
      setError('Use a password with at least 8 characters.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await updatePassword(password);
      setMessage('Password updated. Your Peso Account is ready to use.');
      setPassword('');
      setConfirmPassword('');
    } catch (recoveryError) {
      setError(recoveryError instanceof Error ? recoveryError.message : 'Unable to update your password.');
    } finally {
      setSubmitting(false);
    }
  };

  if (passwordRecoveryMode) {
    return (
      <AuthLayout eyebrow="Account recovery" title="Choose a new password" description="Set a new password for your Peso Account.">
        <Field label="New password" placeholder="At least 8 characters" secureTextEntry value={password} onChangeText={setPassword} />
        <Field label="Confirm password" placeholder="Enter the same password again" secureTextEntry value={confirmPassword} onChangeText={setConfirmPassword} />
        {(error || configError) && <Text selectable style={styles.formError}>{error ?? configError}</Text>}
        {message && <Text selectable style={styles.formSuccess}>{message}</Text>}
        <ActionButton label={submitting ? 'Updating password…' : 'Update password'} disabled={submitting || !password || !confirmPassword} onPress={() => void completeRecovery()} />
        {message && <ActionButton label="Continue to Peso" variant="quiet" onPress={() => navigate('/')} />}
      </AuthLayout>
    );
  }

  return (
    <AuthLayout eyebrow="Account recovery" title="Reset your password" description="Enter your email and we’ll send a secure reset link.">
      <Field label="Email" placeholder="you@example.com" value={email} onChangeText={setEmail} />
      <View style={styles.turnstileFixture} accessibilityLabel="Turnstile verification">
        <Text style={styles.turnstileTitle}>Security check</Text>
        <AuthChallenge action="reset_password" resetSignal={captchaReset} onTokenChange={setCaptchaToken} onError={setCaptchaError} />
      </View>
      {(error || captchaError || configError) && <Text selectable style={styles.formError}>{error ?? captchaError ?? configError}</Text>}
      {message && <Text selectable style={styles.formSuccess}>{message}</Text>}
      <ActionButton label={submitting ? 'Sending reset link…' : error ? 'Retry reset link' : 'Send reset link'} disabled={submitting || !email.trim() || !captchaToken} onPress={() => void reset()} />
      <ActionButton label="Back to sign in" variant="quiet" onPress={() => navigate('/login')} />
    </AuthLayout>
  );
}

const desktopNavItems = [
  { path: '/', label: 'Home', short: 'H' },
  { path: '/setup', label: 'Analyze', short: 'A' },
  { path: '/saved-lifts', label: 'Saved Lifts', short: 'S' },
  { path: '/profile', label: 'Profile', short: 'P' },
];

const mobileNavItems = desktopNavItems;

const routeTitles: Record<string, string> = {
  '/': 'Home',
  '/setup': 'Video setup',
  '/submit': 'Choose video',
  '/record': 'Record video',
  '/upload': 'Upload video',
  '/saved-lifts': 'Saved Lifts',
  '/profile': 'Profile',
  '/settings': 'Settings',
};

function navItemActive(pathname: string, path: string) {
  if (path === '/') return pathname === '/';
  return pathname === path || pathname.startsWith(`${path}/`);
}

function Navigation({
  compact = false,
  mobile = false,
  onToggleCompact,
}: {
  compact?: boolean;
  mobile?: boolean;
  onToggleCompact?: () => void;
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const items = mobile ? mobileNavItems : desktopNavItems;

  return (
    <View style={mobile ? styles.bottomNav : [styles.sidebar, compact && styles.sidebarCompact]} accessibilityLabel="Primary navigation">
      {!mobile && (
        <View style={styles.sidebarHeader}>
          <Pressable accessibilityRole="link" onPress={() => navigate('/')} style={styles.sidebarWordmark}>
            <Wordmark compact={compact} />
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={compact ? 'Expand sidebar' : 'Collapse sidebar'}
            accessibilityState={{ expanded: !compact }}
            onPress={onToggleCompact}
            style={({ pressed }) => [styles.sidebarToggle, pressed && styles.navItemPressed]}
          >
            <Text style={styles.sidebarToggleText}>{compact ? '›' : '‹'}</Text>
          </Pressable>
        </View>
      )}
      <View style={mobile ? styles.bottomNavItems : styles.navList}>
        {items.map((item) => {
          const active = navItemActive(pathname, item.path);
          return (
            <Pressable
              key={item.path}
              accessibilityRole="link"
              accessibilityLabel={item.label}
              accessibilityState={{ selected: active }}
              onPress={() => navigate(item.path)}
              style={({ pressed }) => [
                mobile ? styles.bottomNavItem : styles.navItem,
                active && (mobile ? styles.bottomNavItemActive : styles.navItemActive),
                pressed && styles.navItemPressed,
              ]}
            >
              <View style={[styles.navIcon, active && styles.navIconActive]}>
                <Text style={[styles.navIconText, active && styles.navIconTextActive]}>{item.short}</Text>
              </View>
              {(!compact || mobile) && <Text style={[styles.navLabel, active && styles.navLabelActive]}>{item.label}</Text>}
            </Pressable>
          );
        })}
      </View>
      {!mobile && (
        <View style={styles.sidebarFooter}>
          <Pressable accessibilityRole="link" accessibilityLabel="Settings" onPress={() => navigate('/settings')} style={styles.navItem}>
            <View style={styles.navIcon}><Text style={styles.navIconText}>⚙</Text></View>
            {!compact && <Text style={styles.navLabel}>Settings</Text>}
          </Pressable>
        </View>
      )}
    </View>
  );
}

function AppShell() {
  const { width, height } = useWindowDimensions();
  const location = useLocation();
  const { user } = useAuth();
  const [compact, setCompact] = useState(() =>
    readSidebarCollapsed(typeof window === 'undefined' ? null : window.localStorage)
  );
  const mobile = width < 768;
  const title = location.pathname.startsWith('/saved-lifts/')
    ? 'Saved Lift'
    : location.pathname.startsWith('/processing')
      ? 'Analysis activity'
      : location.pathname.startsWith('/review')
        ? 'Review analysis'
        : routeTitles[location.pathname] ?? 'Peso';
  const accountName = typeof user?.user_metadata?.name === 'string'
    ? user.user_metadata.name
    : user?.email?.split('@')[0] ?? 'Peso athlete';
  const accountInitial = accountName.charAt(0).toUpperCase() || 'P';
  const accountSurface = location.pathname.startsWith('/saved-lifts')
    || location.pathname === '/profile'
    || location.pathname === '/settings';

  useEffect(() => {
    document.title = `${title} — Peso`;
  }, [title]);

  useEffect(() => {
    writeSidebarCollapsed(
      typeof window === 'undefined' ? null : window.localStorage,
      compact
    );
  }, [compact]);

  return (
    <View style={[styles.appRoot, { height: Math.max(height, 640) }]}>
      <View style={styles.appRow}>
        {!mobile && <Navigation compact={compact} onToggleCompact={() => setCompact((value) => !value)} />}
        <View style={styles.appMain}>
          <View style={styles.topbar}>
            <View>
              <Text selectable style={styles.topbarKicker}>{accountSurface ? 'PESO ACCOUNT' : 'REAL ANALYSIS BETA'}</Text>
              <Text accessibilityRole="header" selectable style={styles.topbarTitle}>{title}</Text>
            </View>
            <View style={styles.topbarAccount}>
              <View style={styles.avatar}><Text style={styles.avatarText}>{accountInitial}</Text></View>
              {width >= 560 && (
                <View>
                  <Text selectable style={styles.accountName}>{accountName}</Text>
                  <Text selectable style={styles.accountPlan}>Beta tester</Text>
                </View>
              )}
            </View>
          </View>
          <View style={styles.routeArea}>
            <Outlet />
          </View>
          {mobile && <Navigation mobile />}
        </View>
      </View>
    </View>
  );
}

function AccountRoute() {
  const { session, initializing, configError } = useAuth();

  if (initializing) {
    return (
      <View style={styles.routeLoading} accessibilityLabel="Loading Peso Account">
        <Text selectable style={styles.mutedText}>Loading your Peso Account…</Text>
      </View>
    );
  }

  if (configError) {
    return (
      <View style={styles.routeLoading} role="alert">
        <Text selectable style={styles.formError}>{configError}</Text>
      </View>
    );
  }

  return session ? <AppShell /> : <Navigate to="/login" replace />;
}

function PageScroll({ children }: { children: React.ReactNode }) {
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      style={styles.pageScroll}
      contentContainerStyle={styles.pageContent}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  );
}

function CapacityCard() {
  const { activeCount, activeLimit } = useWebAnalysisActivity();
  const used = Math.min(activeCount, activeLimit);
  const remaining = Math.max(activeLimit - used, 0);
  return (
    <View style={styles.capacityCard}>
      <View style={styles.cardHeaderRow}>
        <View>
          <Text selectable style={styles.cardLabel}>ACTIVE ANALYSIS CAPACITY</Text>
          <Text selectable style={styles.capacityNumber}>{remaining}<Text style={styles.capacityDenominator}> / {activeLimit} available</Text></Text>
        </View>
        <View style={[styles.statusPill, remaining === 0 && styles.statusPillWarning]}>
          <Text style={[styles.statusPillText, remaining === 0 && styles.statusPillWarningText]}>{remaining === 0 ? 'Full' : 'Available'}</Text>
        </View>
      </View>
      <View style={styles.capacitySegments} accessibilityLabel={`${remaining} of ${activeLimit} analysis slots available`}>
        {Array.from({ length: activeLimit }, (_, index) => <View key={index} style={[styles.capacitySegment, index < used && styles.capacitySegmentUsed]} />)}
      </View>
      <Text selectable style={styles.cardFine}>{remaining === 0 ? 'Wait for an active analysis to finish before starting another.' : 'Queued and processing videos count toward this limit.'}</Text>
    </View>
  );
}

function ActivityCard() {
  const navigate = useNavigate();
  const { items, loading, error, refresh } = useWebAnalysisActivity();
  const activity = items[0] ?? null;
  const copy = activity?.stage === 'queued'
    ? { title: 'Squat set is queued', detail: 'Waiting for an analysis worker.' }
    : activity?.stage === 'downloading'
      ? { title: 'Preparing your video', detail: 'Downloading the uploaded source.' }
      : activity?.stage === 'pose'
        ? { title: 'Estimating pose', detail: 'Tracking the lifter through the set.' }
        : activity?.stage === 'barbell_tracking'
          ? { title: 'Tracking the barbell', detail: 'Building the visible bar path.' }
          : activity?.stage === 'saving'
            ? { title: 'Saving your analysis', detail: 'Preparing the result for review.' }
            : activity?.stage === 'ready'
              ? { title: 'Analysis ready to review', detail: 'Your real result is ready.' }
              : activity?.stage === 'failed'
                ? { title: 'Analysis could not finish', detail: 'Try another side-view squat video.' }
                : { title: 'No active analysis', detail: 'Record or upload a side-view squat to start a real analysis.' };
  const toneStyle = activity?.stage === 'ready'
    ? styles.activityDotSuccess
    : !activity
      ? styles.activityDotNeutral
      : styles.activityDotInfo;

  const hasAction = Boolean(activity);
  const actionLabel = activity?.stage === 'ready' ? 'Review result' : 'View activity';
  const onAction = () => navigate(
    activity?.stage === 'ready'
      ? `/review/${activity.video_id}`
      : `/processing/${activity?.video_id}`
  );

  return (
    <View style={styles.activityCard}>
      <View style={[styles.activityDot, toneStyle]} />
      <View style={styles.activityCopy}>
        <Text selectable style={styles.activityTitle}>{copy.title}</Text>
        <Text selectable style={styles.activityDetail}>{loading && !activity ? 'Refreshing activity…' : copy.detail}</Text>
        {error ? <Text selectable style={styles.formError}>{error}</Text> : null}
      </View>
      {hasAction && <ActionButton label={actionLabel} variant="secondary" compact onPress={onAction} />}
      {error && <ActionButton label="Retry" variant="quiet" compact onPress={() => void refresh()} />}
    </View>
  );
}

function QuickAction({
  title,
  description,
  symbol,
  onPress,
  disabled,
}: {
  title: string;
  description: string;
  symbol: string;
  onPress: () => void;
  disabled: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${description}`}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.quickAction, pressed && !disabled && styles.quickActionPressed, disabled && styles.quickActionDisabled]}
    >
      <View style={styles.quickActionIcon}><Text style={styles.quickActionSymbol}>{symbol}</Text></View>
      <View style={styles.quickActionCopy}>
        <Text selectable style={styles.quickActionTitle}>{title}</Text>
        <Text selectable style={styles.quickActionDescription}>{description}</Text>
      </View>
      <Text style={styles.quickActionArrow}>→</Text>
    </Pressable>
  );
}

function useSavedLiftLibrary() {
  const { session, user } = useAuth();
  const cachedLifts = getCachedSavedLifts(user?.id);
  const [lifts, setLifts] = useState<SavedVideo[]>(cachedLifts ?? []);
  const [loading, setLoading] = useState(cachedLifts === null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async (signal?: AbortSignal) => {
    if (!session?.access_token) return;
    setLoading(true);
    setError(null);
    try {
      const nextLifts = await getSavedVideos(session.access_token, signal);
      if (user?.id) {
        savedLiftLibraryCache = {
          userId: user.id,
          lifts: nextLifts,
          expiresAt: Date.now() + SAVED_LIFT_CACHE_TTL_MS,
        };
      }
      setLifts(nextLifts);
    } catch (loadError) {
      if (!signal?.aborted) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load Saved Lifts.');
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const nextCachedLifts = getCachedSavedLifts(user?.id);
    if (nextCachedLifts) {
      setLifts(nextCachedLifts);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [session?.access_token, user?.id]);

  return { lifts, loading, error, refresh: () => refresh() };
}

function LiftRow({
  lift,
  onPress,
  selectionMode = false,
  selected = false,
}: {
  lift: SavedVideo;
  onPress: () => void;
  selectionMode?: boolean;
  selected?: boolean;
}) {
  const exercise = titleCase(lift.exercise_type);
  const reps = savedLiftRepCount(lift);
  return (
    <Pressable
      accessibilityRole={selectionMode ? 'checkbox' : 'link'}
      accessibilityState={selectionMode ? { checked: selected } : undefined}
      accessibilityLabel={`${exercise}, ${savedLiftLoad(lift)}, ${reps} reps, ${formatSavedDate(lift.saved_at ?? lift.created_at)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.liftRow, selected && styles.liftSelected, pressed && styles.liftRowPressed]}
    >
      {selectionMode && (
        <View style={[styles.selectionCheckbox, selected && styles.selectionCheckboxSelected]}>
          {selected && <Text style={styles.checkboxMark}>✓</Text>}
        </View>
      )}
      <Image source={lift.thumbnail_url ? { uri: lift.thumbnail_url } : previewImage} style={styles.liftThumbnail as ImageStyle} accessibilityIgnoresInvertColors />
      <View style={styles.liftRowCopy}>
        <View style={styles.liftTitleRow}>
          <Text selectable style={styles.liftExercise}>{exercise}</Text>
        </View>
        <Text selectable style={styles.liftMeta}>{savedLiftLoad(lift)} · {reps} performed reps</Text>
        <Text selectable style={styles.liftDate}>{formatSavedDate(lift.saved_at ?? lift.created_at)}</Text>
      </View>
      {!selectionMode && <Text style={styles.liftArrow}>›</Text>}
    </Pressable>
  );
}

function HomeScreen() {
  const navigate = useNavigate();
  const { width } = useWindowDimensions();
  const { items, activeCount, activeLimit } = useWebAnalysisActivity();
  const { lifts, loading, error } = useSavedLiftLibrary();
  const blocked = activeCount >= activeLimit;
  const readyItems = items.filter((item) => item.stage === 'ready');
  return (
    <PageScroll>
      <View style={styles.welcomeRow}>
        <View style={styles.welcomeCopy}>
          <Text accessibilityRole="header" selectable style={[styles.pageHeading, width < 768 && styles.pageHeadingMobile]}>Ready for your next set?</Text>
          <Text selectable style={styles.pageSubheading}>Analyze a squat from a recent browser. No special equipment needed.</Text>
        </View>
      </View>
      <View style={styles.homeGrid}>
        <View style={styles.quickActionsColumn}>
          <QuickAction title="Analyze a squat" description="Set up, then upload or record" symbol="●" disabled={blocked} onPress={() => navigate('/setup')} />
        </View>
        <CapacityCard />
      </View>
      <View style={styles.sectionBlock}>
        <View style={styles.sectionTitleRow}>
          <Text accessibilityRole="header" selectable style={styles.sectionTitle}>Processing activity</Text>
        </View>
        <ActivityCard />
      </View>
      {readyItems.length > 0 && (
        <View style={styles.pendingReviewBanner}>
          <View>
            <Text selectable style={styles.pendingTitle}>{readyItems.length} result{readyItems.length === 1 ? '' : 's'} need your review</Text>
            <Text selectable style={styles.pendingBody}>Save or discard completed analyses before they expire.</Text>
          </View>
          <ActionButton label="Review now" compact onPress={() => navigate(`/review/${readyItems[0].video_id}`)} />
        </View>
      )}
      <View style={styles.sectionBlock}>
        <View style={styles.sectionTitleRow}>
          <Text accessibilityRole="header" selectable style={styles.sectionTitle}>Recent Saved Lifts</Text>
          <Pressable accessibilityRole="link" onPress={() => navigate('/saved-lifts')}>
            <Text style={styles.inlineLink}>View all</Text>
          </Pressable>
        </View>
        <View style={styles.liftList}>
          {loading && <Text selectable style={styles.mutedText}>Loading Saved Lifts…</Text>}
          {error && <Text selectable style={styles.formError}>{error}</Text>}
          {!loading && !error && lifts.length === 0 && <Text selectable style={styles.mutedText}>Your shared Saved Lift Library is empty.</Text>}
          {lifts.slice(0, 3).map((lift) => <LiftRow key={lift.id} lift={lift} onPress={() => navigate(`/saved-lifts/${lift.id}`)} />)}
        </View>
      </View>
    </PageScroll>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <View style={styles.metricCard}>
      <Text selectable style={styles.metricLabel}>{label}</Text>
      <Text selectable style={styles.metricValue}>{value}</Text>
      <Text selectable style={styles.metricDetail}>{detail}</Text>
    </View>
  );
}

function AnalyzedVideoPlayer({
  label,
  sourceUri = '',
  posterUri = '',
}: {
  label: string;
  sourceUri?: string;
  posterUri?: string;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(18.933);

  const togglePlayback = async () => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      await video.play();
    } else {
      video.pause();
    }
  };

  const seek = (nextTime: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = nextTime;
    setCurrentTime(nextTime);
  };

  const seekBy = (offsetSeconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    seek(Math.max(0, Math.min(duration, video.currentTime + offsetSeconds)));
  };

  return (
    <View accessibilityLabel={label}>
      <video
        ref={videoRef}
        className="peso-analyzed-video"
        src={sourceUri}
        poster={posterUri}
        playsInline
        preload="metadata"
        aria-label={label}
        onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <View style={styles.reviewControls}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={playing ? 'Pause analyzed video' : 'Play analyzed video'}
          accessibilityState={{ selected: playing }}
          onPress={() => void togglePlayback()}
          style={styles.playButton}
        >
          <Text style={styles.playButtonText}>{playing ? 'Ⅱ' : '▶'}</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Seek back 5 seconds"
          onPress={() => seekBy(-5)}
          style={styles.seekButton}
        >
          <Text style={styles.seekButtonText}>−5</Text>
        </Pressable>
        <input
          className="peso-video-range"
          type="range"
          min="0"
          max={duration || 18.933}
          step="0.01"
          value={Math.min(currentTime, duration || 18.933)}
          aria-label={`Seek analyzed video, ${formatTime(currentTime)} of ${formatTime(duration)}`}
          onClick={(event) => {
            const bounds = event.currentTarget.getBoundingClientRect();
            const ratio = bounds.width > 0
              ? (event.clientX - bounds.left) / bounds.width
              : 0;
            seek(Math.max(0, Math.min(duration, ratio * duration)));
          }}
          onInput={(event) => seek(Number(event.currentTarget.value))}
          onChange={(event) => seek(Number(event.currentTarget.value))}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Seek forward 5 seconds"
          onPress={() => seekBy(5)}
          style={styles.seekButton}
        >
          <Text style={styles.seekButtonText}>+5</Text>
        </Pressable>
        <Text style={styles.timecode}>{formatTime(currentTime)} / {formatTime(duration)}</Text>
      </View>
    </View>
  );
}

function LiftGridCard({
  lift,
  onPress,
  selectionMode,
  selected,
}: {
  lift: SavedVideo;
  onPress: () => void;
  selectionMode: boolean;
  selected: boolean;
}) {
  const exercise = titleCase(lift.exercise_type);
  return (
    <Pressable
      accessibilityRole={selectionMode ? 'checkbox' : 'link'}
      accessibilityState={selectionMode ? { checked: selected } : undefined}
      accessibilityLabel={`${exercise}, ${savedLiftLoad(lift)}, ${savedLiftRepCount(lift)} reps`}
      onPress={onPress}
      style={({ pressed }) => [styles.liftGridCard, selected && styles.liftSelected, pressed && styles.liftRowPressed]}
    >
      <Image source={lift.thumbnail_url ? { uri: lift.thumbnail_url } : previewImage} style={styles.liftGridImage as ImageStyle} accessibilityIgnoresInvertColors />
      {selectionMode && (
        <View style={[styles.gridSelectionCheckbox, selected && styles.selectionCheckboxSelected]}>
          {selected && <Text style={styles.checkboxMark}>✓</Text>}
        </View>
      )}
      <View style={styles.liftGridCopy}>
        <Text selectable style={styles.liftExercise}>{exercise}</Text>
        <Text selectable style={styles.liftMeta}>{savedLiftLoad(lift)} · {savedLiftRepCount(lift)} reps</Text>
        <Text selectable style={styles.liftDate}>{formatSavedDate(lift.saved_at ?? lift.created_at)}</Text>
      </View>
    </Pressable>
  );
}

function SavedLiftsScreen() {
  const navigate = useNavigate();
  const { session, user } = useAuth();
  const { lifts, loading, error, refresh } = useSavedLiftLibrary();
  const [filter, setFilter] = useState('all');
  const [view, setView] = useState<SavedLiftView>(() => normalizeSavedLiftView(
    typeof window === 'undefined' ? null : window.localStorage.getItem('peso.saved-lifts.view')
  ));
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [exportJob, setExportJob] = useState<SavedLiftExportJob | null>(null);

  const filters = useMemo(() => [
    { value: 'all', label: 'All lifts' },
    ...Array.from(new Set(lifts.map((lift) => lift.exercise_type))).map((exercise) => ({
      value: exercise,
      label: titleCase(exercise),
    })),
  ], [lifts]);
  const visibleLifts = useMemo(
    () => lifts.filter((lift) => filter === 'all' || lift.exercise_type === filter),
    [filter, lifts]
  );
  const exportStorageKey = user ? `peso.saved-lift-export-job:${user.id}` : null;

  useEffect(() => {
    if (typeof window !== 'undefined') window.localStorage.setItem('peso.saved-lifts.view', view);
  }, [view]);

  useEffect(() => {
    setSelectedIds((current) => pruneSavedLiftSelection(current, lifts.map((lift) => lift.id)));
  }, [lifts]);

  useEffect(() => {
    if (!exportStorageKey || typeof window === 'undefined') return;
    setExportJobId(window.localStorage.getItem(exportStorageKey));
  }, [exportStorageKey]);

  useEffect(() => {
    if (!exportJobId || !session?.access_token) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let active = true;

    const poll = async () => {
      try {
        const job = await getSavedLiftExport(exportJobId, session.access_token);
        if (!active) return;
        setExportJob(job);
        if (job.status === 'queued' || job.status === 'processing') {
          timer = setTimeout(() => void poll(), 2000);
        }
      } catch (pollError) {
        if (active) setActionError(pollError instanceof Error ? pollError.message : 'Unable to check export status.');
      }
    };

    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [exportJobId, session?.access_token]);

  const startExport = async () => {
    if (!session?.access_token || selectedIds.length === 0) return;
    setActionBusy(true);
    setActionError(null);
    try {
      const job = await createSavedLiftExport(selectedIds, session.access_token);
      setExportJob(job);
      setExportJobId(job.id);
      if (exportStorageKey && typeof window !== 'undefined') {
        window.localStorage.setItem(exportStorageKey, job.id);
      }
      setSelectedIds([]);
      setSelectionMode(false);
    } catch (exportError) {
      setActionError(exportError instanceof Error ? exportError.message : 'Unable to start Saved Lift export.');
    } finally {
      setActionBusy(false);
    }
  };

  const downloadExport = async () => {
    if (!exportJobId || !session?.access_token) return;
    setActionError(null);
    try {
      const job = await getSavedLiftExport(exportJobId, session.access_token);
      setExportJob(job);
      if (job.download_url) window.location.assign(job.download_url);
    } catch (downloadError) {
      setActionError(downloadError instanceof Error ? downloadError.message : 'Unable to download the export.');
    }
  };

  const deleteSelection = async () => {
    if (!session?.access_token || selectedIds.length === 0) return;
    const confirmed = window.confirm(
      `Permanently delete ${selectedIds.length} selected Saved Lift${selectedIds.length === 1 ? '' : 's'}? This also removes them from the shared mobile library and cannot be undone.`
    );
    if (!confirmed) return;

    setActionBusy(true);
    setActionError(null);
    try {
      await deleteSavedLifts(selectedIds, session.access_token);
      invalidateSavedLiftLibraryCache();
      setSelectedIds([]);
      setSelectionMode(false);
      await refresh();
    } catch (deleteError) {
      setActionError(deleteError instanceof Error ? deleteError.message : 'Unable to delete Saved Lifts.');
    } finally {
      setActionBusy(false);
    }
  };

  const toggleSelectionMode = () => {
    setSelectionMode((current) => !current);
    setSelectedIds([]);
  };

  return (
    <PageScroll>
      <View style={styles.savedHeader}>
        <View>
          <Text accessibilityRole="header" selectable style={styles.pageHeading}>Your Saved Lifts</Text>
          <Text selectable style={styles.pageSubheading}>One source-agnostic library shared by Peso web and mobile.</Text>
        </View>
        <View style={styles.buttonRow}>
          <ActionButton label={selectionMode ? 'Cancel selection' : 'Select lifts'} variant="secondary" compact onPress={toggleSelectionMode} />
          <ActionButton label="Analyze a squat" compact onPress={() => navigate('/setup')} />
        </View>
      </View>

      {exportJob && (
        <View style={styles.exportStatusCard} role="status">
          <View style={styles.activityCopy}>
            <Text selectable style={styles.activityTitle}>
              {exportJob.status === 'completed'
                ? 'Saved Lift export ready'
                : exportJob.status === 'failed' || exportJob.status === 'expired'
                  ? 'Saved Lift export unavailable'
                  : `Preparing ${exportJob.lift_count} Saved Lift${exportJob.lift_count === 1 ? '' : 's'}…`}
            </Text>
            <Text selectable style={styles.activityDetail}>
              {exportJob.status === 'completed'
                ? `One ZIP is available until ${formatSavedDate(exportJob.expires_at)}.`
                : exportJob.status === 'failed'
                  ? exportFailureMessage(exportJob.failure_code)
                  : exportJob.status === 'expired'
                    ? 'The temporary archive expired. Select the lifts again to create a new one.'
                    : 'You can leave this page; preparation continues on the backend.'}
            </Text>
          </View>
          {exportJob.status === 'completed' && <ActionButton label="Download ZIP" compact onPress={() => void downloadExport()} />}
        </View>
      )}

      {actionError && <Text selectable style={styles.formError}>{actionError}</Text>}

      <View style={styles.savedControls}>
        <View style={styles.filterRow} accessibilityRole="radiogroup">
          {filters.map(({ value, label }) => (
            <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: filter === value }} onPress={() => setFilter(value)} style={[styles.filterChip, filter === value && styles.filterChipActive]}>
              <Text style={[styles.filterChipText, filter === value && styles.filterChipTextActive]}>{label}</Text>
            </Pressable>
          ))}
        </View>
        <View style={styles.viewToggle} accessibilityRole="radiogroup">
          {(['list', 'grid'] as const).map((option) => (
            <Pressable key={option} accessibilityRole="radio" accessibilityLabel={`${titleCase(option)} View`} accessibilityState={{ checked: view === option }} onPress={() => setView(option)} style={[styles.viewToggleButton, view === option && styles.viewToggleButtonActive]}>
              <Text style={[styles.filterChipText, view === option && styles.filterChipTextActive]}>{option === 'list' ? '☰' : '▦'} {titleCase(option)}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {selectionMode && (
        <View style={styles.selectionToolbar}>
          <Text selectable style={styles.selectionCount}>{selectedIds.length} selected</Text>
          <View style={styles.buttonRow}>
            <ActionButton label="Select visible" variant="quiet" compact onPress={() => setSelectedIds((current) => selectVisibleSavedLifts(current, visibleLifts.map((lift) => lift.id)))} />
            <ActionButton label={actionBusy ? 'Preparing…' : 'Export ZIP'} disabled={actionBusy || selectedIds.length === 0} compact onPress={() => void startExport()} />
            <ActionButton label={actionBusy ? 'Deleting…' : 'Delete'} variant="danger" disabled={actionBusy || selectedIds.length === 0} compact onPress={() => void deleteSelection()} />
          </View>
        </View>
      )}

      {loading && <Text selectable style={styles.mutedText}>Loading Saved Lifts…</Text>}
      {error && <Text selectable style={styles.formError}>{error}</Text>}
      {!loading && !error && visibleLifts.length === 0 && <Text selectable style={styles.mutedText}>No Saved Lifts match this view.</Text>}
      <View style={view === 'grid' ? styles.savedGrid : styles.savedList}>
        {visibleLifts.map((lift) => {
          const selected = selectedIds.includes(lift.id);
          const onPress = () => selectionMode
            ? setSelectedIds((current) => toggleSavedLiftSelection(current, lift.id))
            : navigate(`/saved-lifts/${lift.id}`);
          return view === 'grid'
            ? <LiftGridCard key={lift.id} lift={lift} selectionMode={selectionMode} selected={selected} onPress={onPress} />
            : <LiftRow key={lift.id} lift={lift} selectionMode={selectionMode} selected={selected} onPress={onPress} />;
        })}
      </View>
    </PageScroll>
  );
}

function insightNumber(value: number | undefined, digits = 2) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function RepInsight({ rep, index }: { rep: VideoAnalysisRep; index: number }) {
  return (
    <View style={styles.repInsightCard}>
      <Text selectable style={styles.repInsightTitle}>Rep {rep.rep_index ?? rep.repIndex ?? index + 1}</Text>
      <View style={styles.metricGrid}>
        <MetricCard label="Duration" value={`${insightNumber(rep.duration)} s`} detail="Rep elapsed time" />
        <MetricCard label="Rep speed" value={insightNumber(rep.repSpeed)} detail="Repetitions per second" />
        <MetricCard label="Avg hip velocity" value={insightNumber(rep.avgVelocity, 3)} detail="Relative video estimate" />
        <MetricCard label="Peak hip velocity" value={insightNumber(rep.peakVelocity, 3)} detail="Relative video estimate" />
      </View>
    </View>
  );
}

function SavedLiftDetailScreen() {
  const navigate = useNavigate();
  const { liftId } = useParams();
  const { session } = useAuth();
  const { lifts, loading, error } = useSavedLiftLibrary();
  const [playbackUrl, setPlaybackUrl] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const lift = lifts.find((candidate) => candidate.id === liftId);

  useEffect(() => {
    if (!lift || !session?.access_token || lift.storage_state === 'pruned') return;
    let active = true;
    getSavedVideoPlaybackUrl(lift.id, session.access_token)
      .then((response) => {
        if (active) setPlaybackUrl(response.video_url);
      })
      .catch((loadError) => {
        if (active) setPlaybackError(loadError instanceof Error ? loadError.message : 'Unable to load Saved Lift video.');
      });
    return () => { active = false; };
  }, [lift?.id, lift?.storage_state, session?.access_token]);

  if (loading) return <PageScroll><Text selectable style={styles.mutedText}>Loading Saved Lift…</Text></PageScroll>;
  if (error) return <PageScroll><Text selectable style={styles.formError}>{error}</Text></PageScroll>;
  if (!lift) {
    return (
      <PageScroll>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>Saved Lift not found</Text>
        <ActionButton label="Back to Saved Lifts" variant="quiet" compact onPress={() => navigate('/saved-lifts')} />
      </PageScroll>
    );
  }

  const exercise = titleCase(lift.exercise_type);
  const detectedReps = lift.analysis?.result_json.rep_count ?? lift.analysis?.rep_data.length ?? 0;
  const performedReps = lift.performed_reps ?? lift.corrected_rep_count ?? detectedReps;
  const cue = lift.analysis?.coaching_feedback[0] ?? lift.analysis?.summary[0] ?? 'No saved coaching cue is available.';
  const posterUri = lift.thumbnail_url ?? '';

  return (
    <PageScroll>
      <View style={styles.detailTopRow}>
        <ActionButton label="Back to Saved Lifts" variant="quiet" compact onPress={() => navigate('/saved-lifts')} />
      </View>
      <View style={styles.reviewGrid}>
        <View style={styles.reviewMedia}>
          {playbackUrl ? (
            <AnalyzedVideoPlayer label="Saved Lift video controls" sourceUri={playbackUrl} posterUri={posterUri} />
          ) : (
            <Image source={lift.thumbnail_url ? { uri: lift.thumbnail_url } : previewImage} style={styles.reviewImage as ImageStyle} accessibilityLabel={`${exercise} Saved Lift preview`} />
          )}
          {lift.storage_state === 'pruned' && <Text selectable style={styles.mediaNotice}>This Saved Lift video has expired; analysis insights remain available.</Text>}
          {playbackError && <Text selectable style={styles.formError}>{playbackError}</Text>}
        </View>
        <View style={styles.reviewPanel}>
          <Text style={styles.eyebrow}>{formatSavedDate(lift.saved_at ?? lift.created_at).toUpperCase()}</Text>
          <Text accessibilityRole="header" selectable style={styles.pageHeading}>{exercise}</Text>
          <Text selectable style={styles.detailLoad}>{savedLiftLoad(lift)} × {performedReps}</Text>
          <View style={styles.metricGrid}>
            <MetricCard label="Performed reps" value={String(performedReps)} detail="Workout fact" />
            <MetricCard label="Detected reps" value={String(detectedReps)} detail="Model observation" />
            <MetricCard label="Camera" value={titleCase(lift.view_type)} detail={`${titleCase(lift.view_type)} view`} />
          </View>
          <View style={styles.cueCard}>
            <Text selectable style={styles.cueLabel}>SAVED OBSERVATION</Text>
            <Text selectable style={styles.cueTitle}>{cue}</Text>
          </View>
        </View>
      </View>
      {lift.analysis?.rep_data.length ? (
        <View style={styles.insightsSection}>
          <View>
            <Text accessibilityRole="header" selectable style={styles.sectionTitle}>Lift Insights</Text>
            <Text selectable style={styles.pageSubheading}>Per-repetition timing and framing-dependent hip movement estimates.</Text>
          </View>
          {lift.analysis.rep_data.map((rep, index) => <RepInsight key={`${rep.rep_index ?? index}`} rep={rep} index={index} />)}
        </View>
      ) : null}
    </PageScroll>
  );
}

function ProfileScreen() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const displayName = typeof user?.user_metadata?.name === 'string'
    ? user.user_metadata.name
    : user?.email?.split('@')[0] ?? 'Peso athlete';
  const initial = displayName.charAt(0).toUpperCase() || 'P';
  return (
    <PageScroll>
      <View style={styles.settingsPage}>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>Profile</Text>
        <Text selectable style={styles.pageSubheading}>Basic account information shared with your Peso mobile account.</Text>
        <View style={styles.profileCard}>
          <View style={styles.profileAvatar}><Text style={styles.profileAvatarText}>{initial}</Text></View>
          <View><Text selectable style={styles.profileName}>{displayName}</Text><Text selectable style={styles.profileEmail}>{user?.email ?? 'Email unavailable'} · {user?.email_confirmed_at ? 'Verified' : 'Unverified'}</Text></View>
        </View>
        <ActionButton label="Open Settings" variant="secondary" onPress={() => navigate('/settings')} />
      </View>
    </PageScroll>
  );
}

function SettingRow({ title, description, value, onChange }: { title: string; description: string; value: boolean; onChange: (value: boolean) => void }) {
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingCopy}><Text selectable style={styles.settingTitle}>{title}</Text><Text selectable style={styles.settingDescription}>{description}</Text></View>
      <Switch accessibilityLabel={title} value={value} onValueChange={onChange} trackColor={{ false: '#303848', true: colors.brand }} thumbColor="#FFFFFF" />
    </View>
  );
}

function SettingsScreen() {
  const navigate = useNavigate();
  const { signOut } = useAuth();
  const [analytics, setAnalytics] = useState(false);
  const [updates, setUpdates] = useState(true);
  return (
    <PageScroll>
      <View style={styles.settingsPage}>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>Settings</Text>
        <Text selectable style={styles.pageSubheading}>Control optional product data and account preferences.</Text>
        <View style={styles.settingsCard}>
          <SettingRow title="Product analytics" description="Opt in to the limited event list. Session replay stays off." value={analytics} onChange={setAnalytics} />
          <SettingRow title="Beta updates" description="Receive important testing and availability updates." value={updates} onChange={setUpdates} />
        </View>
        <View style={styles.settingsCard}>
          <Pressable accessibilityRole="link" onPress={() => window.location.assign('/privacy')} style={styles.settingsLink}><Text style={styles.settingTitle}>Privacy Policy</Text><Text style={styles.liftArrow}>›</Text></Pressable>
          <Pressable accessibilityRole="link" onPress={() => window.location.assign('/terms')} style={styles.settingsLink}><Text style={styles.settingTitle}>Terms of Use</Text><Text style={styles.liftArrow}>›</Text></Pressable>
          <Pressable accessibilityRole="link" onPress={() => { void signOut().then(() => navigate('/login', { replace: true })); }} style={styles.settingsLink}><Text style={[styles.settingTitle, { color: colors.red }]}>Sign out</Text><Text style={styles.liftArrow}>›</Text></Pressable>
        </View>
      </View>
    </PageScroll>
  );
}

export default function WebApp() {
  return (
    <WebAnalysisActivityProvider>
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/signup" element={<SignupScreen />} />
        <Route path="/verify" element={<VerifyScreen />} />
        <Route path="/reset" element={<ResetScreen />} />
        <Route element={<AccountRoute />}>
          <Route index element={<HomeScreen />} />
          <Route path="/setup" element={<WebVideoSetupRoute />} />
          <Route path="/submit" element={<WebSubmissionChoiceRoute />} />
          <Route path="/record" element={<WebRecordRoute />} />
          <Route path="/upload" element={<WebUploadRoute />} />
          <Route path="/processing/:videoId" element={<WebProcessingRoute />} />
          <Route path="/review/:videoId" element={<WebReviewRoute onLibraryChanged={invalidateSavedLiftLibraryCache} />} />
          <Route path="/saved-lifts" element={<SavedLiftsScreen />} />
          <Route path="/saved-lifts/:liftId" element={<SavedLiftDetailScreen />} />
          <Route path="/profile" element={<ProfileScreen />} />
          <Route path="/settings" element={<SettingsScreen />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </WebAnalysisActivityProvider>
  );
}

const shadow: ViewStyle = { boxShadow: '0 20px 60px rgba(0, 0, 0, 0.24)' } as ViewStyle;

const styles = StyleSheet.create({
  appRoot: { flex: 1, minHeight: 640, backgroundColor: colors.page },
  appRow: { flex: 1, flexDirection: 'row' },
  appMain: { flex: 1, minWidth: 0 },
  topbar: { minHeight: 82, paddingHorizontal: 28, paddingVertical: 16, borderBottomWidth: 1, borderBottomColor: colors.line, backgroundColor: '#090D13', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 20 },
  topbarKicker: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 9, letterSpacing: 1.4 },
  topbarTitle: { marginTop: 4, color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 19 },
  topbarAccount: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  avatar: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand },
  avatarText: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 14 },
  accountName: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 12 },
  accountPlan: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, marginTop: 2 },
  routeArea: { flex: 1, minHeight: 0 },
  routeLoading: { flex: 1, minHeight: 640, alignItems: 'center', justifyContent: 'center', padding: 28, backgroundColor: colors.page },
  pageScroll: { flex: 1 },
  pageContent: { width: '100%', maxWidth: 1280, alignSelf: 'center', padding: 28, paddingBottom: 80, gap: 30 },
  sidebar: { width: 252, padding: 18, borderRightWidth: 1, borderRightColor: colors.line, backgroundColor: '#090D13' },
  sidebarCompact: { width: 86, paddingHorizontal: 12 },
  sidebarHeader: { minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  sidebarWordmark: { flex: 1, minWidth: 0, minHeight: 52, alignItems: 'flex-start', justifyContent: 'center' },
  sidebarToggle: { width: 32, height: 32, borderWidth: 1, borderColor: colors.line, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  sidebarToggleText: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 20, lineHeight: 22 },
  wordmark: { width: 118, height: 54, alignItems: 'center', justifyContent: 'center' },
  wordmarkCompact: { width: 60, height: 44 },
  wordmarkImage: { width: 118, height: 54, resizeMode: 'contain' },
  wordmarkImageCompact: { width: 60, height: 28, resizeMode: 'contain' },
  navList: { flex: 1, gap: 8, paddingTop: 34 },
  navItem: { minHeight: 48, paddingHorizontal: 10, borderRadius: 12, flexDirection: 'row', alignItems: 'center', gap: 12 },
  navItemActive: { backgroundColor: colors.blueSoft },
  navItemPressed: { opacity: 0.72 },
  navIcon: { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: '#151C28' },
  navIconActive: { backgroundColor: colors.brand },
  navIconText: { color: colors.textMuted, fontFamily: fonts.bold, fontSize: 11 },
  navIconTextActive: { color: '#FFFFFF' },
  navLabel: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 13 },
  navLabelActive: { color: colors.textPrimary },
  sidebarFooter: { gap: 12 },
  bottomNav: { minHeight: 68, paddingHorizontal: 8, paddingBottom: 4, borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: '#090D13' },
  bottomNavItems: { flex: 1, flexDirection: 'row', justifyContent: 'space-around' },
  bottomNavItem: { minWidth: 72, paddingVertical: 8, alignItems: 'center', justifyContent: 'center', gap: 3, borderTopWidth: 2, borderTopColor: 'transparent' },
  bottomNavItemActive: { borderTopColor: colors.brand },
  authPage: { flex: 1, backgroundColor: colors.page },
  authPageContent: { flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  authFrame: { width: '100%', maxWidth: 1060, minHeight: 680, flexDirection: 'row', borderWidth: 1, borderColor: colors.line, borderRadius: 24, overflow: 'hidden', backgroundColor: colors.surface, ...shadow },
  authFrameMobile: { maxWidth: 560, flexDirection: 'column' },
  authAside: { width: '43%', padding: 44, justifyContent: 'space-between', backgroundColor: '#0A1427', borderRightWidth: 1, borderRightColor: '#243C67' },
  authAsideMobile: { width: '100%', minHeight: 230, padding: 28, borderRightWidth: 0, borderBottomWidth: 1, borderBottomColor: '#243C67' },
  authAsideCopy: { gap: 14 },
  authAsideTitle: { maxWidth: 340, color: colors.textPrimary, fontFamily: fonts.display, fontSize: 37, lineHeight: 41 },
  authAsideBody: { maxWidth: 340, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 15, lineHeight: 24 },
  authAsideFine: { color: colors.blueText, fontFamily: fonts.semibold, fontSize: 11 },
  authPanel: { flex: 1, minWidth: 0, padding: 44, justifyContent: 'center' },
  eyebrow: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 10, letterSpacing: 1.4 },
  authTitle: { marginTop: 10, color: colors.textPrimary, fontFamily: fonts.display, fontSize: 35, lineHeight: 41 },
  authDescription: { marginTop: 13, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 14, lineHeight: 21 },
  form: { gap: 16, paddingTop: 28 },
  formError: { color: colors.red, fontFamily: fonts.medium, fontSize: 11, lineHeight: 17 },
  formSuccess: { color: colors.green, fontFamily: fonts.medium, fontSize: 11, lineHeight: 17 },
  field: { gap: 7 },
  fieldLabel: { color: colors.secondaryText, fontFamily: fonts.semibold, fontSize: 11 },
  input: { width: '100%', height: 48, paddingHorizontal: 14, borderWidth: 1, borderColor: colors.inputBorder, borderRadius: 11, backgroundColor: colors.inputBg, color: colors.textPrimary, fontFamily: fonts.regular, fontSize: 14 },
  inlineLink: { color: colors.blueText, fontFamily: fonts.semibold, fontSize: 12, textDecorationLine: 'underline' },
  authBackLink: { alignSelf: 'flex-start', paddingTop: 22 },
  formFooterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'center' },
  mutedText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 12 },
  button: { minHeight: 46, paddingHorizontal: 18, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  buttonPrimary: { backgroundColor: colors.brand },
  buttonSecondary: { borderWidth: 1, borderColor: colors.secondaryBorder, backgroundColor: colors.secondarySurface },
  buttonDanger: { borderWidth: 1, borderColor: '#6D2935', backgroundColor: colors.redSoft },
  buttonQuiet: { backgroundColor: 'transparent' },
  buttonCompact: { minHeight: 38, paddingHorizontal: 14 },
  buttonPressed: { opacity: 0.82 },
  buttonDisabled: { opacity: 0.4 },
  buttonText: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 12 },
  buttonQuietText: { color: colors.blueText },
  checkRow: { minHeight: 40, flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  checkbox: { width: 20, height: 20, borderWidth: 1, borderColor: '#52617A', borderRadius: 5, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.inputBg },
  checkboxChecked: { borderColor: colors.brand, backgroundColor: colors.brand },
  checkboxMark: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 12 },
  checkLabel: { flex: 1, color: colors.secondaryText, fontFamily: fonts.regular, fontSize: 12, lineHeight: 19 },
  turnstileFixture: { padding: 14, borderWidth: 1, borderStyle: 'dashed', borderColor: '#44526A', borderRadius: 10, backgroundColor: '#0A0E15' },
  turnstileTitle: { color: colors.secondaryText, fontFamily: fonts.semibold, fontSize: 11 },
  turnstileWidget: { minHeight: 66, marginTop: 10 },
  messageCard: { padding: 18, borderWidth: 1, borderColor: '#294A7D', borderRadius: 12, backgroundColor: '#0D1B33' },
  messageCardTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  messageCardBody: { marginTop: 6, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 12, lineHeight: 19 },
  welcomeRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', gap: 20 },
  welcomeCopy: { flex: 1, minWidth: 0 },
  pageHeading: { color: colors.textPrimary, fontFamily: fonts.display, fontSize: 32, lineHeight: 38 },
  pageHeadingMobile: { width: '100%', fontSize: 29, lineHeight: 35 },
  pageSubheading: { maxWidth: 680, marginTop: 8, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 14, lineHeight: 22 },
  homeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 18 },
  quickActionsColumn: { flex: 1, minWidth: 310, gap: 12 },
  quickAction: { minHeight: 106, padding: 18, borderWidth: 1, borderColor: colors.line, borderRadius: 16, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 15, ...shadow },
  quickActionPressed: { borderColor: colors.brand, backgroundColor: colors.surfaceRaised },
  quickActionDisabled: { opacity: 0.45 },
  quickActionIcon: { width: 50, height: 50, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.blueSoft },
  quickActionSymbol: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 22 },
  quickActionCopy: { flex: 1 },
  quickActionTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 16 },
  quickActionDescription: { marginTop: 5, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  quickActionArrow: { color: colors.blueText, fontFamily: fonts.regular, fontSize: 20 },
  capacityCard: { flex: 1, minWidth: 310, minHeight: 224, padding: 22, borderWidth: 1, borderColor: colors.line, borderRadius: 16, backgroundColor: '#0D1522', justifyContent: 'space-between', ...shadow },
  cardHeaderRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  cardLabel: { color: colors.textMuted, fontFamily: fonts.bold, fontSize: 9, letterSpacing: 1.1 },
  capacityNumber: { marginTop: 12, color: colors.textPrimary, fontFamily: fonts.display, fontSize: 35, fontVariant: ['tabular-nums'] },
  capacityDenominator: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 13 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14, backgroundColor: colors.greenSoft },
  statusPillText: { color: colors.green, fontFamily: fonts.bold, fontSize: 9 },
  statusPillWarning: { backgroundColor: colors.amberSoft },
  statusPillWarningText: { color: colors.amber },
  capacitySegments: { flexDirection: 'row', gap: 7 },
  capacitySegment: { flex: 1, height: 7, borderRadius: 4, backgroundColor: colors.brand },
  capacitySegmentUsed: { backgroundColor: '#333D4B' },
  cardFine: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, lineHeight: 15 },
  sectionBlock: { gap: 12 },
  sectionTitleRow: { minHeight: 30, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 16 },
  sectionTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 17 },
  activityCard: { minHeight: 94, padding: 17, borderWidth: 1, borderColor: colors.line, borderRadius: 14, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 14 },
  activityDot: { width: 9, height: 9, borderRadius: 5 },
  activityDotNeutral: { backgroundColor: '#60708A' },
  activityDotInfo: { backgroundColor: colors.brand },
  activityDotSuccess: { backgroundColor: colors.green },
  activityCopy: { flex: 1, minWidth: 120 },
  activityTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  activityDetail: { marginTop: 5, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11, lineHeight: 17 },
  pendingReviewBanner: { padding: 18, borderWidth: 1, borderColor: '#2D579A', borderRadius: 14, backgroundColor: '#0D1B34', flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 15 },
  pendingTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  pendingBody: { marginTop: 4, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  liftList: { gap: 9 },
  liftRow: { minHeight: 88, padding: 12, borderWidth: 1, borderColor: colors.line, borderRadius: 14, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 14 },
  liftRowPressed: { borderColor: colors.brand, backgroundColor: colors.surfaceRaised },
  liftSelected: { borderColor: colors.brand, backgroundColor: colors.blueSoft },
  selectionCheckbox: { width: 22, height: 22, borderWidth: 1, borderColor: '#52617A', borderRadius: 6, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.inputBg },
  selectionCheckboxSelected: { borderColor: colors.brand, backgroundColor: colors.brand },
  liftThumbnail: { width: 62, height: 62, borderRadius: 10, backgroundColor: '#10141C' },
  liftRowCopy: { flex: 1, minWidth: 0 },
  liftTitleRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  liftExercise: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  liftMeta: { marginTop: 5, color: colors.secondaryText, fontFamily: fonts.regular, fontSize: 11 },
  liftDate: { marginTop: 4, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10 },
  liftArrow: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 23 },
  mobileBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 9, backgroundColor: '#222A36' },
  mobileBadgeText: { color: '#BCC4D0', fontFamily: fonts.semibold, fontSize: 8 },
  narrowPage: { width: '100%', maxWidth: 760, alignSelf: 'center', gap: 24 },
  fallbackCard: { padding: 24, borderWidth: 1, borderColor: '#71572B', borderRadius: 16, backgroundColor: colors.amberSoft, gap: 12 },
  fallbackTitle: { color: colors.amber, fontFamily: fonts.semibold, fontSize: 17 },
  fallbackBody: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 13, lineHeight: 20 },
  cameraStage: { minHeight: 430, borderWidth: 1, borderColor: '#334158', borderRadius: 19, overflow: 'hidden', backgroundColor: '#0B111A', alignItems: 'center', justifyContent: 'center' },
  cameraStageRecording: { borderColor: colors.red },
  cameraGuide: { width: 230, height: 310, borderWidth: 1, borderStyle: 'dashed', borderColor: '#3D7EF5', borderRadius: 100, alignItems: 'center', justifyContent: 'center' },
  cameraGuideBody: { width: 72, height: 210, borderWidth: 2, borderColor: '#4F83DC', borderRadius: 34 },
  cameraGuideBar: { position: 'absolute', width: 270, height: 4, borderRadius: 2, backgroundColor: '#4F83DC', top: 110 },
  cameraStatus: { position: 'absolute', top: 18, left: 18, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 12, backgroundColor: 'rgba(0,0,0,.72)', flexDirection: 'row', alignItems: 'center', gap: 7 },
  recordingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#697386' },
  recordingDotLive: { backgroundColor: colors.red },
  cameraStatusText: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 10, fontVariant: ['tabular-nums'] },
  cameraFixtureNote: { position: 'absolute', bottom: 16, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, textAlign: 'center' },
  buttonRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  dropZone: { minHeight: 310, padding: 28, borderWidth: 2, borderStyle: 'dashed', borderColor: '#35445D', borderRadius: 18, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  dropZonePressed: { borderColor: colors.brand, backgroundColor: '#0E192B' },
  uploadIcon: { width: 58, height: 58, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.blueSoft },
  uploadIconText: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 28 },
  dropZoneTitle: { marginTop: 17, color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 16, textAlign: 'center' },
  dropZoneBody: { marginTop: 6, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11, textAlign: 'center' },
  uploadThumbnail: { width: 154, height: 182, borderRadius: 14, backgroundColor: '#05070A', resizeMode: 'cover' },
  requirementsCard: { padding: 20, borderWidth: 1, borderColor: colors.line, borderRadius: 15, backgroundColor: '#0B1018', gap: 11 },
  requirementsTitle: { marginBottom: 2, color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  requirementRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  requirementCheck: { color: colors.green, fontFamily: fonts.bold, fontSize: 11 },
  requirementText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  setupGrid: { width: '100%', maxWidth: 1040, alignSelf: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 28, alignItems: 'flex-start' },
  setupPreview: { width: 330, height: 550, borderWidth: 1, borderColor: colors.line, borderRadius: 18, backgroundColor: '#05070A' },
  setupPreviewFallback: { width: 330, height: 550, borderWidth: 1, borderColor: colors.line, borderRadius: 18, backgroundColor: '#090D13', alignItems: 'center', justifyContent: 'center', gap: 12 },
  setupPreviewFallbackIcon: { color: colors.blueText, fontSize: 28 },
  setupPreviewFallbackText: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 11 },
  previewMeta: { marginTop: 10, flexDirection: 'row', justifyContent: 'space-between' },
  previewMetaText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, fontVariant: ['tabular-nums'] },
  setupPanel: { flex: 1, minWidth: 310, gap: 22 },
  fieldGroup: { gap: 9 },
  selectCard: { minHeight: 82, padding: 15, borderWidth: 1, borderColor: colors.line, borderRadius: 13, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 12 },
  selectCardSelected: { borderColor: colors.brand, backgroundColor: '#0E1B31' },
  radio: { width: 20, height: 20, borderWidth: 1, borderColor: '#59667A', borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  radioSelected: { borderColor: colors.brand },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brand },
  selectCardCopy: { flex: 1 },
  selectCardTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  selectCardDescription: { marginTop: 4, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, lineHeight: 15 },
  infoCallout: { padding: 14, borderRadius: 11, backgroundColor: '#101722' },
  infoCalloutText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, lineHeight: 16 },
  processingPage: { width: '100%', maxWidth: 680, alignSelf: 'center', alignItems: 'center', gap: 18, paddingTop: 18 },
  processingVisual: { width: 220, height: 310, borderWidth: 1, borderColor: colors.line, borderRadius: 18, overflow: 'hidden', backgroundColor: '#05070A' },
  processingImage: { width: '100%', height: '100%' },
  processingOverlay: { position: 'absolute', right: 10, bottom: 10, width: 62, height: 62, borderRadius: 31, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(5,9,15,.88)', borderWidth: 1, borderColor: '#3C68AD' },
  processingDescription: { maxWidth: 560, textAlign: 'center', marginTop: -8 },
  stepper: { width: '100%', maxWidth: 520, paddingVertical: 14, flexDirection: 'row', justifyContent: 'space-between' },
  stepItem: { flex: 1, alignItems: 'center', gap: 7 },
  stepDot: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: '#252C37' },
  stepDotActive: { backgroundColor: colors.brand },
  stepDotText: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 9 },
  stepLabel: { color: colors.textMuted, fontFamily: fonts.medium, fontSize: 10 },
  stepLabelActive: { color: colors.textPrimary },
  reviewGrid: { width: '100%', maxWidth: 952, alignSelf: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 24, alignItems: 'flex-start' },
  reviewMedia: { width: 332, maxWidth: '100%', borderWidth: 1, borderColor: '#35435A', borderRadius: 24, overflow: 'hidden', backgroundColor: '#05070A' },
  reviewImage: { width: '100%', height: 527, resizeMode: 'cover' },
  reviewControls: { minHeight: 49, paddingHorizontal: 11, flexDirection: 'row', alignItems: 'center', gap: 9, backgroundColor: '#090D13' },
  playButton: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand },
  playButtonText: { color: '#FFFFFF', fontSize: 9 },
  seekButton: { minWidth: 26, height: 28, borderRadius: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: '#151C28' },
  seekButtonText: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 8 },
  timecode: { color: colors.textMuted, fontFamily: fonts.medium, fontSize: 8, fontVariant: ['tabular-nums'] },
  mediaDescription: { maxWidth: 332, marginTop: 9, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 9, lineHeight: 14 },
  mediaNotice: { padding: 12, color: colors.amber, backgroundColor: colors.amberSoft, fontFamily: fonts.medium, fontSize: 10, lineHeight: 16 },
  reviewPanel: { flex: 1, minWidth: 310, gap: 15 },
  reviewTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  reviewEyebrow: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 8, letterSpacing: 1.2 },
  reviewPageHeading: { marginTop: 5, color: colors.textPrimary, fontFamily: fonts.display, fontSize: 27, lineHeight: 32 },
  readyBadge: { paddingHorizontal: 9, paddingVertical: 5, borderRadius: 10, backgroundColor: colors.greenSoft },
  readyBadgeText: { color: colors.green, fontFamily: fonts.bold, fontSize: 8 },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metricCard: { flex: 1, minWidth: 102, minHeight: 94, padding: 12, borderWidth: 1, borderColor: colors.line, borderRadius: 11, backgroundColor: colors.surface },
  metricLabel: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 8 },
  metricValue: { marginTop: 10, color: colors.textPrimary, fontFamily: fonts.display, fontSize: 17 },
  metricDetail: { marginTop: 5, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 8 },
  cueCard: { padding: 16, borderWidth: 1, borderColor: '#294A7D', borderRadius: 12, backgroundColor: '#0D1A30' },
  cueLabel: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 8, letterSpacing: 0.85 },
  cueTitle: { marginTop: 10, color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 14, lineHeight: 20 },
  cueBody: { marginTop: 7, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 9, lineHeight: 15 },
  disclosureButton: { minHeight: 43, paddingHorizontal: 13, borderWidth: 1, borderColor: colors.line, borderRadius: 10, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  disclosureTitle: { color: colors.secondaryText, fontFamily: fonts.semibold, fontSize: 10 },
  disclosureIcon: { color: colors.blueText, fontFamily: fonts.regular, fontSize: 19 },
  workoutFields: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  expiryText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 8 },
  savedHeader: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-end', gap: 18 },
  savedControls: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 14 },
  filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  filterChip: { minHeight: 34, paddingHorizontal: 13, borderWidth: 1, borderColor: colors.line, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  filterChipActive: { borderColor: colors.brand, backgroundColor: colors.blueSoft },
  filterChipText: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 10 },
  filterChipTextActive: { color: colors.blueText },
  savedList: { width: '100%', maxWidth: 880, gap: 10 },
  savedGrid: { width: '100%', flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  liftGridCard: { width: 220, minHeight: 280, borderWidth: 1, borderColor: colors.line, borderRadius: 15, overflow: 'hidden', backgroundColor: colors.surface },
  liftGridImage: { width: '100%', aspectRatio: 1, backgroundColor: '#10141C', resizeMode: 'cover' },
  liftGridCopy: { padding: 13, gap: 5 },
  gridSelectionCheckbox: { position: 'absolute', top: 10, right: 10, width: 25, height: 25, borderWidth: 1, borderColor: '#70809A', borderRadius: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(7, 9, 13, 0.88)' },
  viewToggle: { flexDirection: 'row', padding: 3, borderWidth: 1, borderColor: colors.line, borderRadius: 11, backgroundColor: colors.surface },
  viewToggleButton: { minHeight: 32, paddingHorizontal: 11, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  viewToggleButtonActive: { backgroundColor: colors.blueSoft },
  selectionToolbar: { padding: 14, borderWidth: 1, borderColor: '#294A7D', borderRadius: 13, backgroundColor: '#0D1A30', flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  selectionCount: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 12 },
  exportStatusCard: { padding: 16, borderWidth: 1, borderColor: '#2D579A', borderRadius: 14, backgroundColor: '#0D1B34', flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 14 },
  detailTopRow: { width: '100%', maxWidth: 952, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  detailLoad: { color: colors.blueText, fontFamily: fonts.display, fontSize: 24 },
  insightsSection: { width: '100%', maxWidth: 952, alignSelf: 'center', gap: 14 },
  repInsightCard: { padding: 16, borderWidth: 1, borderColor: colors.line, borderRadius: 14, backgroundColor: colors.surface, gap: 12 },
  repInsightTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  settingsPage: { width: '100%', maxWidth: 760, alignSelf: 'center', gap: 22 },
  profileCard: { padding: 20, borderWidth: 1, borderColor: colors.line, borderRadius: 15, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 15 },
  profileAvatar: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand },
  profileAvatarText: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 20 },
  profileName: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 16 },
  profileEmail: { marginTop: 5, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  settingsCard: { padding: 18, borderWidth: 1, borderColor: colors.line, borderRadius: 15, backgroundColor: colors.surface, gap: 15 },
  settingRow: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 16 },
  settingCopy: { flex: 1 },
  settingTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 12 },
  settingDescription: { marginTop: 4, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, lineHeight: 16 },
  settingsLink: { minHeight: 50, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: colors.line },
});
