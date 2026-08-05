import { createContext, use, useEffect, useMemo, useState } from 'react';
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
import {
  activityCopy,
  prototypeScenarios,
  savedLifts,
  type PrototypeScenario,
  type SavedLiftFixture,
} from './fixtures';

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

const previewImage = require('../../assets/demo/peso-pose-overlay.jpg') as ImageSourcePropType;
const barPathImage = require('../../assets/demo/peso-pin-assisted-bar-path.jpg') as ImageSourcePropType;
const logoImage = require('../../assets/peso-logo.png') as ImageSourcePropType;

type ScenarioContextValue = {
  scenario: PrototypeScenario;
  setScenario: (scenario: PrototypeScenario) => void;
};

const ScenarioContext = createContext<ScenarioContextValue | null>(null);

function useScenario() {
  const value = use(ScenarioContext);
  if (!value) {
    throw new Error('ScenarioContext is unavailable');
  }
  return value;
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
  return (
    <AuthLayout eyebrow="Welcome back" title="Sign in to Peso" description="Use the same account as the mobile app.">
      <Field label="Email" placeholder="you@example.com" />
      <Field label="Password" placeholder="Enter your password" secureTextEntry />
      <Pressable accessibilityRole="link" onPress={() => navigate('/reset')}>
        <Text style={styles.inlineLink}>Forgot password?</Text>
      </Pressable>
      <ActionButton label="Sign in" onPress={() => navigate('/')} />
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
  const [usResident, setUsResident] = useState(false);
  const [terms, setTerms] = useState(false);
  return (
    <AuthLayout eyebrow="Limited beta" title="Create your account" description="The web beta is free and currently available to US residents.">
      <Field label="Email" placeholder="you@example.com" />
      <Field label="Password" placeholder="At least 8 characters" secureTextEntry />
      <CheckRow checked={usResident} onPress={() => setUsResident(!usResident)} label="I confirm that I reside in the United States." />
      <CheckRow checked={terms} onPress={() => setTerms(!terms)} label="I agree to the beta Terms and acknowledge the Privacy Policy." />
      <View style={styles.turnstileFixture} accessibilityLabel="Turnstile verification placeholder">
        <Text style={styles.turnstileTitle}>Security check</Text>
        <Text style={styles.turnstileBody}>Turnstile appears here when staging authentication is connected.</Text>
      </View>
      <ActionButton label="Create account" disabled={!usResident || !terms} onPress={() => navigate('/verify')} />
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
    <AuthLayout eyebrow="Check your inbox" title="Verify your email" description="We sent a verification link to nathan@example.com.">
      <View style={styles.messageCard}>
        <Text selectable style={styles.messageCardTitle}>Email verification is required</Text>
        <Text selectable style={styles.messageCardBody}>Open the link on this device. This prototype does not send an email.</Text>
      </View>
      <ActionButton label="I verified my email" onPress={() => navigate('/')} />
      <ActionButton label="Resend verification" variant="secondary" onPress={() => undefined} />
    </AuthLayout>
  );
}

function ResetScreen() {
  const navigate = useNavigate();
  return (
    <AuthLayout eyebrow="Account recovery" title="Reset your password" description="Enter your email and we’ll send a secure reset link.">
      <Field label="Email" placeholder="you@example.com" />
      <View style={styles.turnstileFixture} accessibilityLabel="Turnstile verification placeholder">
        <Text style={styles.turnstileTitle}>Security check</Text>
        <Text style={styles.turnstileBody}>Turnstile appears here when staging authentication is connected.</Text>
      </View>
      <ActionButton label="Send reset link" onPress={() => navigate('/login')} />
      <ActionButton label="Back to sign in" variant="quiet" onPress={() => navigate('/login')} />
    </AuthLayout>
  );
}

const navItems = [
  { path: '/', label: 'Home', short: 'H' },
  { path: '/record', label: 'Record', short: 'R' },
  { path: '/saved-lifts', label: 'Saved Lifts', short: 'S' },
  { path: '/profile', label: 'Profile', short: 'P' },
];

const routeTitles: Record<string, string> = {
  '/': 'Home',
  '/record': 'Record video',
  '/upload': 'Upload video',
  '/setup': 'Video setup',
  '/saved-lifts': 'Saved Lifts',
  '/profile': 'Profile',
  '/settings': 'Settings',
};

function navItemActive(pathname: string, path: string) {
  if (path === '/') return pathname === '/';
  return pathname === path || pathname.startsWith(`${path}/`);
}

function Navigation({ compact = false, mobile = false }: { compact?: boolean; mobile?: boolean }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const items = mobile ? navItems.slice(0, 4) : navItems;

  return (
    <View style={mobile ? styles.bottomNav : [styles.sidebar, compact && styles.sidebarCompact]} accessibilityLabel="Primary navigation">
      {!mobile && (
        <Pressable accessibilityRole="link" onPress={() => navigate('/')} style={styles.sidebarWordmark}>
          <Wordmark compact={compact} />
        </Pressable>
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
          {!compact && <Text selectable style={styles.prototypeBadge}>Fixture prototype · No backend</Text>}
        </View>
      )}
    </View>
  );
}

function AppShell() {
  const { width, height } = useWindowDimensions();
  const location = useLocation();
  const compact = width >= 768 && width < 1200;
  const mobile = width < 768;
  const title = location.pathname.startsWith('/saved-lifts/')
    ? 'Saved Lift'
    : location.pathname.startsWith('/processing')
      ? 'Analysis activity'
      : location.pathname.startsWith('/review')
        ? 'Review analysis'
        : routeTitles[location.pathname] ?? 'Peso';

  useEffect(() => {
    document.title = `${title} — Peso`;
  }, [title]);

  return (
    <View style={[styles.appRoot, { height: Math.max(height, 640) }]}>
      <View style={styles.appRow}>
        {!mobile && <Navigation compact={compact} />}
        <View style={styles.appMain}>
          <View style={styles.topbar}>
            <View>
              <Text selectable style={styles.topbarKicker}>PESO WEB BETA</Text>
              <Text accessibilityRole="header" selectable style={styles.topbarTitle}>{title}</Text>
            </View>
            <View style={styles.topbarAccount}>
              <View style={styles.avatar}><Text style={styles.avatarText}>N</Text></View>
              {width >= 560 && (
                <View>
                  <Text selectable style={styles.accountName}>Nathan</Text>
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

function ScenarioPicker() {
  const { scenario, setScenario } = useScenario();
  return (
    <View style={styles.scenarioPanel}>
      <View>
        <Text selectable style={styles.scenarioTitle}>Prototype state</Text>
        <Text selectable style={styles.scenarioDescription}>Switch fixtures to inspect empty, active, error, and limit behavior.</Text>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scenarioList}>
        {prototypeScenarios.map((item) => (
          <Pressable
            key={item.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: scenario === item.value }}
            onPress={() => setScenario(item.value)}
            style={[styles.scenarioChip, scenario === item.value && styles.scenarioChipActive]}
          >
            <Text style={[styles.scenarioChipText, scenario === item.value && styles.scenarioChipTextActive]}>{item.label}</Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function CapacityCard() {
  const { scenario } = useScenario();
  const used = scenario === 'quota' ? 3 : scenario === 'empty' ? 0 : 1;
  const remaining = 3 - used;
  return (
    <View style={styles.capacityCard}>
      <View style={styles.cardHeaderRow}>
        <View>
          <Text selectable style={styles.cardLabel}>ROLLING 24-HOUR CAPACITY</Text>
          <Text selectable style={styles.capacityNumber}>{remaining}<Text style={styles.capacityDenominator}> / 3 remaining</Text></Text>
        </View>
        <View style={[styles.statusPill, remaining === 0 && styles.statusPillWarning]}>
          <Text style={[styles.statusPillText, remaining === 0 && styles.statusPillWarningText]}>{remaining === 0 ? 'Full' : 'Available'}</Text>
        </View>
      </View>
      <View style={styles.capacitySegments} accessibilityLabel={`${remaining} of 3 analysis slots remaining`}>
        {[0, 1, 2].map((index) => <View key={index} style={[styles.capacitySegment, index < used && styles.capacitySegmentUsed]} />)}
      </View>
      <Text selectable style={styles.cardFine}>{remaining === 0 ? 'Next slot opens today at 6:18 PM.' : 'A slot is charged when a web analysis is accepted.'}</Text>
    </View>
  );
}

function ActivityCard() {
  const navigate = useNavigate();
  const { scenario } = useScenario();
  const copy = activityCopy[scenario];
  const toneStyle =
    copy.tone === 'success'
      ? styles.activityDotSuccess
      : copy.tone === 'danger'
        ? styles.activityDotDanger
        : copy.tone === 'warning'
          ? styles.activityDotWarning
          : copy.tone === 'info'
            ? styles.activityDotInfo
            : styles.activityDotNeutral;

  const hasAction = scenario !== 'empty' && scenario !== 'quota';
  const actionLabel = scenario === 'completed' ? 'Review result' : scenario === 'failed' ? 'Try again' : 'View activity';
  const onAction = () => {
    if (scenario === 'completed') navigate('/review/job-2042');
    else if (scenario === 'failed' || scenario === 'expired') navigate('/upload');
    else navigate('/processing/job-2042');
  };

  return (
    <View style={styles.activityCard}>
      <View style={[styles.activityDot, toneStyle]} />
      <View style={styles.activityCopy}>
        <Text selectable style={styles.activityTitle}>{copy.title}</Text>
        <Text selectable style={styles.activityDetail}>{copy.detail}</Text>
      </View>
      {hasAction && <ActionButton label={actionLabel} variant="secondary" compact onPress={onAction} />}
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

function LiftRow({ lift, onPress }: { lift: SavedLiftFixture; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={`${lift.exercise}, ${lift.load}, ${lift.performedReps} reps, ${lift.date}`}
      onPress={onPress}
      style={({ pressed }) => [styles.liftRow, pressed && styles.liftRowPressed]}
    >
      <Image source={lift.exercise === 'Squat' ? barPathImage : previewImage} style={styles.liftThumbnail as ImageStyle} accessibilityIgnoresInvertColors />
      <View style={styles.liftRowCopy}>
        <View style={styles.liftTitleRow}>
          <Text selectable style={styles.liftExercise}>{lift.exercise}</Text>
          {!lift.webEligible && <View style={styles.mobileBadge}><Text style={styles.mobileBadgeText}>Mobile history</Text></View>}
        </View>
        <Text selectable style={styles.liftMeta}>{lift.load} · {lift.performedReps} performed reps</Text>
        <Text selectable style={styles.liftDate}>{lift.date}</Text>
      </View>
      <Text style={styles.liftArrow}>›</Text>
    </Pressable>
  );
}

function HomeScreen() {
  const navigate = useNavigate();
  const { width } = useWindowDimensions();
  const { scenario } = useScenario();
  const blocked = scenario === 'quota';
  return (
    <PageScroll>
      <ScenarioPicker />
      <View style={styles.welcomeRow}>
        <View style={styles.welcomeCopy}>
          <Text accessibilityRole="header" selectable style={[styles.pageHeading, width < 768 && styles.pageHeadingMobile]}>Ready for your next set?</Text>
          <Text selectable style={styles.pageSubheading}>Analyze a squat from a recent browser. No special equipment needed.</Text>
        </View>
      </View>
      <View style={styles.homeGrid}>
        <View style={styles.quickActionsColumn}>
          <QuickAction title="Record Video" description="Use this device’s camera" symbol="●" disabled={blocked} onPress={() => navigate('/record')} />
          <QuickAction title="Upload Video" description="Choose a video from this device" symbol="↑" disabled={blocked} onPress={() => navigate('/upload')} />
        </View>
        <CapacityCard />
      </View>
      <View style={styles.sectionBlock}>
        <View style={styles.sectionTitleRow}>
          <Text accessibilityRole="header" selectable style={styles.sectionTitle}>Processing activity</Text>
        </View>
        <ActivityCard />
      </View>
      {scenario === 'completed' && (
        <View style={styles.pendingReviewBanner}>
          <View>
            <Text selectable style={styles.pendingTitle}>1 result needs your review</Text>
            <Text selectable style={styles.pendingBody}>Save or discard it before it expires tomorrow at 8:42 AM.</Text>
          </View>
          <ActionButton label="Review now" compact onPress={() => navigate('/review/job-2042')} />
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
          {savedLifts.slice(0, 3).map((lift) => <LiftRow key={lift.id} lift={lift} onPress={() => navigate(`/saved-lifts/${lift.id}`)} />)}
        </View>
      </View>
    </PageScroll>
  );
}

function RecordScreen() {
  const navigate = useNavigate();
  const recorderSupported =
    typeof navigator !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== 'undefined';
  const [recording, setRecording] = useState(false);
  const [recorded, setRecorded] = useState(false);

  const finishRecording = () => {
    setRecording(false);
    setRecorded(true);
  };

  return (
    <PageScroll>
      <View style={styles.narrowPage}>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>Record a squat set</Text>
        <Text selectable style={styles.pageSubheading}>Keep your full body and both ends of the bar visible. Record one set from the side.</Text>
        {!recorderSupported ? (
          <View style={styles.fallbackCard} role="alert">
            <Text selectable style={styles.fallbackTitle}>Recording is unavailable in this browser</Text>
            <Text selectable style={styles.fallbackBody}>You can still choose a video already saved on this device.</Text>
            <ActionButton label="Upload Video instead" onPress={() => navigate('/upload')} />
          </View>
        ) : (
          <>
            <View style={[styles.cameraStage, recording && styles.cameraStageRecording]}>
              <View style={styles.cameraGuide}>
                <View style={styles.cameraGuideBody} />
                <View style={styles.cameraGuideBar} />
              </View>
              <View style={styles.cameraStatus}>
                <View style={[styles.recordingDot, recording && styles.recordingDotLive]} />
                <Text style={styles.cameraStatusText}>{recording ? 'Prototype recording · 00:08' : recorded ? 'Clip ready · 00:18' : 'Camera preview'}</Text>
              </View>
              <Text selectable style={styles.cameraFixtureNote}>Camera permission is not requested by this fixture prototype.</Text>
            </View>
            <View style={styles.buttonRow}>
              {!recording && !recorded && <ActionButton label="Start recording" onPress={() => setRecording(true)} />}
              {recording && <ActionButton label="Stop recording" variant="danger" onPress={finishRecording} />}
              {recorded && <ActionButton label="Continue to setup" onPress={() => navigate('/setup')} />}
              {recorded && <ActionButton label="Record again" variant="secondary" onPress={() => setRecorded(false)} />}
              <ActionButton label="Upload instead" variant="quiet" onPress={() => navigate('/upload')} />
            </View>
          </>
        )}
      </View>
    </PageScroll>
  );
}

function pickLocalVideo(onSelected: (name: string) => void) {
  if (typeof document === 'undefined') return;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'video/mp4,video/quicktime,video/webm';
  input.onchange = () => {
    const file = input.files?.[0];
    if (file) onSelected(file.name);
  };
  input.click();
}

function UploadScreen() {
  const navigate = useNavigate();
  const [fileName, setFileName] = useState<string | null>(null);
  return (
    <PageScroll>
      <View style={styles.narrowPage}>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>Upload a squat video</Text>
        <Text selectable style={styles.pageSubheading}>Choose a 15–30 second clip. MP4, MOV, and WebM are supported in the prototype.</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Choose a squat video from this device"
          onPress={() => pickLocalVideo(setFileName)}
          style={({ pressed }) => [styles.dropZone, pressed && styles.dropZonePressed]}
        >
          <View style={styles.uploadIcon}><Text style={styles.uploadIconText}>↑</Text></View>
          <Text selectable style={styles.dropZoneTitle}>{fileName ?? 'Choose a video'}</Text>
          <Text selectable style={styles.dropZoneBody}>{fileName ? 'The file stays on this device in the fixture prototype.' : 'Select one file up to 50 MB'}</Text>
        </Pressable>
        <View style={styles.requirementsCard}>
          <Text selectable style={styles.requirementsTitle}>For the clearest result</Text>
          {['One squat set only', 'Full body and bar visible', 'Stable side view', 'Good lighting with minimal obstruction'].map((item) => (
            <View key={item} style={styles.requirementRow}><Text style={styles.requirementCheck}>✓</Text><Text selectable style={styles.requirementText}>{item}</Text></View>
          ))}
        </View>
        <View style={styles.buttonRow}>
          <ActionButton label="Continue to setup" disabled={!fileName} onPress={() => navigate('/setup')} />
          {!fileName && <ActionButton label="Use realistic demo file" variant="secondary" onPress={() => setFileName('squat-set-aug-04.mov')} />}
        </View>
      </View>
    </PageScroll>
  );
}

function SelectCard({ selected, title, description, onPress }: { selected: boolean; title: string; description: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="radio" accessibilityState={{ checked: selected }} onPress={onPress} style={[styles.selectCard, selected && styles.selectCardSelected]}>
      <View style={[styles.radio, selected && styles.radioSelected]}>{selected && <View style={styles.radioDot} />}</View>
      <View style={styles.selectCardCopy}>
        <Text selectable style={styles.selectCardTitle}>{title}</Text>
        <Text selectable style={styles.selectCardDescription}>{description}</Text>
      </View>
    </Pressable>
  );
}

function SetupScreen() {
  const navigate = useNavigate();
  const { setScenario } = useScenario();
  const [view, setView] = useState<'side' | 'front'>('side');
  const [visible, setVisible] = useState(true);
  const submit = () => {
    setScenario('queued');
    navigate('/processing/job-2042');
  };
  return (
    <PageScroll>
      <View style={styles.setupGrid}>
        <View>
          <Image source={previewImage} style={styles.setupPreview as ImageStyle} accessibilityLabel="Selected squat video preview" />
          <View style={styles.previewMeta}><Text style={styles.previewMetaText}>squat-set-aug-04.mov</Text><Text style={styles.previewMetaText}>00:18</Text></View>
        </View>
        <View style={styles.setupPanel}>
          <Text accessibilityRole="header" selectable style={styles.pageHeading}>Confirm the setup</Text>
          <Text selectable style={styles.pageSubheading}>Web beta accepts new squat submissions only.</Text>
          <View style={styles.fieldGroup}>
            <Text style={styles.fieldLabel}>Camera view</Text>
            <SelectCard selected={view === 'side'} title="Side view" description="Recommended for depth, torso, and bar path." onPress={() => setView('side')} />
            <SelectCard selected={view === 'front'} title="Front / three-quarter" description="Bilateral tracking; depth feedback may be limited." onPress={() => setView('front')} />
          </View>
          <CheckRow checked={visible} onPress={() => setVisible(!visible)} label="The lifter’s full body and visible end of the bar stay in frame." />
          <View style={styles.infoCallout}><Text style={styles.infoCalloutText}>This fixture creates no upload or job. Staging will validate the file before accepting a quota slot.</Text></View>
          <View style={styles.buttonRow}>
            <ActionButton label="Submit for analysis" disabled={!visible} onPress={submit} />
            <ActionButton label="Choose another video" variant="secondary" onPress={() => navigate('/upload')} />
          </View>
        </View>
      </View>
    </PageScroll>
  );
}

function ProcessingScreen() {
  const navigate = useNavigate();
  const { scenario, setScenario } = useScenario();
  const effectiveScenario: PrototypeScenario = ['queued', 'processing', 'completed', 'failed', 'expired'].includes(scenario) ? scenario : 'processing';
  const copy = activityCopy[effectiveScenario];
  const stepIndex = effectiveScenario === 'queued' ? 0 : effectiveScenario === 'processing' ? 1 : 2;

  const advance = () => {
    if (effectiveScenario === 'queued') setScenario('processing');
    else if (effectiveScenario === 'processing') setScenario('completed');
    else if (effectiveScenario === 'completed') navigate('/review/job-2042');
  };

  return (
    <PageScroll>
      <View style={styles.processingPage}>
        <View style={styles.processingVisual}>
          <Image source={barPathImage} style={styles.processingImage as ImageStyle} accessibilityLabel="Squat video awaiting analysis" />
          <View style={styles.processingOverlay}><Text style={styles.processingPercent}>{effectiveScenario === 'queued' ? '01' : effectiveScenario === 'processing' ? '62' : '100'}%</Text></View>
        </View>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>{copy.title}</Text>
        <Text selectable style={[styles.pageSubheading, styles.processingDescription]}>{copy.detail}</Text>
        <View style={styles.stepper} accessibilityLabel={`Analysis step ${stepIndex + 1} of 3`}>
          {['Queued', 'Analyzing', 'Ready'].map((label, index) => (
            <View key={label} style={styles.stepItem}>
              <View style={[styles.stepDot, index <= stepIndex && styles.stepDotActive]}><Text style={styles.stepDotText}>{index + 1}</Text></View>
              <Text style={[styles.stepLabel, index <= stepIndex && styles.stepLabelActive]}>{label}</Text>
            </View>
          ))}
        </View>
        {effectiveScenario === 'queued' && <ActionButton label="Cancel queued analysis" variant="danger" onPress={() => { setScenario('empty'); navigate('/'); }} />}
        {effectiveScenario === 'processing' && <ActionButton label="Show completed fixture" variant="secondary" onPress={advance} />}
        {effectiveScenario === 'completed' && <ActionButton label="Review result" onPress={advance} />}
        {(effectiveScenario === 'failed' || effectiveScenario === 'expired') && <ActionButton label="Upload another video" onPress={() => navigate('/upload')} />}
        <ActionButton label="Back to Home" variant="quiet" onPress={() => navigate('/')} />
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

function FixtureVideoControls({ label }: { label: string }) {
  const [playing, setPlaying] = useState(false);
  return (
    <View style={styles.reviewControls} accessibilityLabel={label}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={playing ? 'Pause analyzed video' : 'Play analyzed video'}
        accessibilityState={{ selected: playing }}
        onPress={() => setPlaying(!playing)}
        style={styles.playButton}
      >
        <Text style={styles.playButtonText}>{playing ? 'Ⅱ' : '▶'}</Text>
      </Pressable>
      <View style={styles.timeline} accessibilityLabel="Video progress, 4 seconds of 18 seconds">
        <View style={styles.timelineProgress} />
      </View>
      <Text style={styles.timecode}>0:04 / 0:18</Text>
    </View>
  );
}

function ReviewScreen() {
  const navigate = useNavigate();
  const { setScenario } = useScenario();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [reps, setReps] = useState('3');
  const [load, setLoad] = useState('225');
  const save = () => {
    setScenario('empty');
    navigate('/saved-lifts/lift-225');
  };
  return (
    <PageScroll>
      <View style={styles.reviewGrid}>
        <View>
          <View style={styles.reviewMedia}>
            <Image source={previewImage} style={styles.reviewImage as ImageStyle} accessibilityLabel="Analyzed squat with joint tracking overlay" />
            <FixtureVideoControls label="Analyzed video controls" />
          </View>
          <Text selectable style={styles.mediaDescription}>The overlay marks the upper back, hip, knee, and ankle. Use the playback controls to inspect each rep.</Text>
        </View>
        <View style={styles.reviewPanel}>
          <View style={styles.reviewTitleRow}>
            <View>
              <Text style={styles.eyebrow}>ANALYSIS COMPLETE</Text>
              <Text accessibilityRole="header" selectable style={styles.pageHeading}>Squat · Side view</Text>
            </View>
            <View style={styles.readyBadge}><Text style={styles.readyBadgeText}>Ready</Text></View>
          </View>
          <View style={styles.metricGrid}>
            <MetricCard label="Detected reps" value="3" detail="Model observation" />
            <MetricCard label="Depth" value="3 / 3" detail="Reps reached depth" />
            <MetricCard label="Bar path" value="Stable" detail="Over mid-foot" />
          </View>
          <View style={styles.cueCard}>
            <Text selectable style={styles.cueLabel}>FOCUS FOR YOUR NEXT SET</Text>
            <Text selectable style={styles.cueTitle}>Keep the descent as controlled as rep two.</Text>
            <Text selectable style={styles.cueBody}>Rep two showed the most consistent torso angle and bar position. Use that pace as your reference.</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityState={{ expanded: detailsOpen }} onPress={() => setDetailsOpen(!detailsOpen)} style={styles.disclosureButton}>
            <Text style={styles.disclosureTitle}>Optional workout details</Text>
            <Text style={styles.disclosureIcon}>{detailsOpen ? '−' : '+'}</Text>
          </Pressable>
          {detailsOpen && (
            <View style={styles.workoutFields}>
              <Field label="Performed reps" placeholder="3" value={reps} onChangeText={setReps} />
              <Field label="Load (lb)" placeholder="225" value={load} onChangeText={setLoad} />
            </View>
          )}
          <View style={styles.buttonRow}>
            <ActionButton label="Save to Saved Lifts" onPress={save} />
            <ActionButton label="Discard analysis" variant="danger" onPress={() => { setScenario('empty'); navigate('/'); }} />
          </View>
          <Text selectable style={styles.expiryText}>Unsaved result expires tomorrow at 8:42 AM.</Text>
        </View>
      </View>
    </PageScroll>
  );
}

function SavedLiftsScreen() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<'all' | 'squat' | 'mobile'>('all');
  const lifts = savedLifts.filter((lift) => filter === 'all' || (filter === 'squat' ? lift.exercise === 'Squat' : !lift.webEligible));
  return (
    <PageScroll>
      <View style={styles.savedHeader}>
        <View>
          <Text accessibilityRole="header" selectable style={styles.pageHeading}>Your Saved Lifts</Text>
          <Text selectable style={styles.pageSubheading}>Web and mobile history live together. New web submissions are squat-only.</Text>
        </View>
        <ActionButton label="Analyze a squat" compact onPress={() => navigate('/upload')} />
      </View>
      <View style={styles.filterRow} accessibilityRole="radiogroup">
        {([
          ['all', 'All lifts'],
          ['squat', 'Squats'],
          ['mobile', 'Mobile history'],
        ] as const).map(([value, label]) => (
          <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: filter === value }} onPress={() => setFilter(value)} style={[styles.filterChip, filter === value && styles.filterChipActive]}>
            <Text style={[styles.filterChipText, filter === value && styles.filterChipTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.savedList}>
        {lifts.map((lift) => <LiftRow key={lift.id} lift={lift} onPress={() => navigate(`/saved-lifts/${lift.id}`)} />)}
      </View>
    </PageScroll>
  );
}

function SavedLiftDetailScreen() {
  const navigate = useNavigate();
  const { liftId } = useParams();
  const lift = savedLifts.find((candidate) => candidate.id === liftId) ?? savedLifts[0];
  return (
    <PageScroll>
      <View style={styles.detailTopRow}>
        <ActionButton label="Back to Saved Lifts" variant="quiet" compact onPress={() => navigate('/saved-lifts')} />
        {!lift.webEligible && <View style={styles.mobileBadge}><Text style={styles.mobileBadgeText}>Saved on mobile</Text></View>}
      </View>
      <View style={styles.reviewGrid}>
        <View style={styles.reviewMedia}>
          <Image source={lift.exercise === 'Squat' ? barPathImage : previewImage} style={styles.reviewImage as ImageStyle} accessibilityLabel={`${lift.exercise} Saved Lift preview`} />
          <FixtureVideoControls label="Saved Lift video controls" />
        </View>
        <View style={styles.reviewPanel}>
          <Text style={styles.eyebrow}>{lift.date.toUpperCase()}</Text>
          <Text accessibilityRole="header" selectable style={styles.pageHeading}>{lift.exercise}</Text>
          <Text selectable style={styles.detailLoad}>{lift.load} × {lift.performedReps}</Text>
          <View style={styles.metricGrid}>
            <MetricCard label="Performed reps" value={String(lift.performedReps)} detail="Workout fact" />
            <MetricCard label="Detected reps" value={String(lift.detectedReps)} detail="Model observation" />
            <MetricCard label="Camera" value={lift.cameraView.replace(' view', '')} detail={lift.cameraView} />
          </View>
          <View style={styles.cueCard}>
            <Text selectable style={styles.cueLabel}>SAVED OBSERVATION</Text>
            <Text selectable style={styles.cueTitle}>{lift.cue}</Text>
            {!lift.webEligible && <Text selectable style={styles.cueBody}>Existing non-squat history is visible here, but the web beta only accepts new squat submissions.</Text>}
          </View>
        </View>
      </View>
    </PageScroll>
  );
}

function ProfileScreen() {
  const navigate = useNavigate();
  return (
    <PageScroll>
      <View style={styles.settingsPage}>
        <Text accessibilityRole="header" selectable style={styles.pageHeading}>Profile</Text>
        <Text selectable style={styles.pageSubheading}>Basic account information shared with your Peso mobile account.</Text>
        <View style={styles.profileCard}>
          <View style={styles.profileAvatar}><Text style={styles.profileAvatarText}>N</Text></View>
          <View><Text selectable style={styles.profileName}>Nathan</Text><Text selectable style={styles.profileEmail}>nathan@example.com · Verified</Text></View>
        </View>
        <View style={styles.settingsCard}>
          <Field label="Display name" placeholder="Nathan" value="Nathan" />
          <Field label="Email" placeholder="nathan@example.com" value="nathan@example.com" />
          <ActionButton label="Save profile fixture" onPress={() => undefined} />
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
          <Pressable accessibilityRole="link" onPress={() => navigate('/login')} style={styles.settingsLink}><Text style={[styles.settingTitle, { color: colors.red }]}>Sign out</Text><Text style={styles.liftArrow}>›</Text></Pressable>
        </View>
        <Text selectable style={styles.prototypeBadge}>Peso Web Beta prototype · Fixture data only</Text>
      </View>
    </PageScroll>
  );
}

export default function WebApp() {
  const [scenario, setScenario] = useState<PrototypeScenario>('completed');
  const value = useMemo(() => ({ scenario, setScenario }), [scenario]);

  return (
    <ScenarioContext value={value}>
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/signup" element={<SignupScreen />} />
        <Route path="/verify" element={<VerifyScreen />} />
        <Route path="/reset" element={<ResetScreen />} />
        <Route element={<AppShell />}>
          <Route index element={<HomeScreen />} />
          <Route path="/record" element={<RecordScreen />} />
          <Route path="/upload" element={<UploadScreen />} />
          <Route path="/setup" element={<SetupScreen />} />
          <Route path="/processing/:jobId" element={<ProcessingScreen />} />
          <Route path="/review/:jobId" element={<ReviewScreen />} />
          <Route path="/saved-lifts" element={<SavedLiftsScreen />} />
          <Route path="/saved-lifts/:liftId" element={<SavedLiftDetailScreen />} />
          <Route path="/profile" element={<ProfileScreen />} />
          <Route path="/settings" element={<SettingsScreen />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ScenarioContext>
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
  pageScroll: { flex: 1 },
  pageContent: { width: '100%', maxWidth: 1280, alignSelf: 'center', padding: 28, paddingBottom: 80, gap: 30 },
  sidebar: { width: 252, padding: 22, borderRightWidth: 1, borderRightColor: colors.line, backgroundColor: '#090D13' },
  sidebarCompact: { width: 86, paddingHorizontal: 12 },
  sidebarWordmark: { minHeight: 64, alignItems: 'flex-start', justifyContent: 'center' },
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
  prototypeBadge: { color: '#718097', fontFamily: fonts.medium, fontSize: 10, lineHeight: 15 },
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
  turnstileBody: { marginTop: 4, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, lineHeight: 15 },
  messageCard: { padding: 18, borderWidth: 1, borderColor: '#294A7D', borderRadius: 12, backgroundColor: '#0D1B33' },
  messageCardTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  messageCardBody: { marginTop: 6, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 12, lineHeight: 19 },
  scenarioPanel: { padding: 16, borderWidth: 1, borderColor: colors.line, borderRadius: 14, backgroundColor: '#0B1018', gap: 13 },
  scenarioTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 12 },
  scenarioDescription: { marginTop: 3, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  scenarioList: { gap: 8 },
  scenarioChip: { minHeight: 32, paddingHorizontal: 12, borderWidth: 1, borderColor: colors.line, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  scenarioChipActive: { borderColor: colors.brand, backgroundColor: colors.blueSoft },
  scenarioChipText: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 10 },
  scenarioChipTextActive: { color: colors.blueText },
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
  activityDotDanger: { backgroundColor: colors.red },
  activityDotWarning: { backgroundColor: colors.amber },
  activityCopy: { flex: 1, minWidth: 120 },
  activityTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  activityDetail: { marginTop: 5, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11, lineHeight: 17 },
  pendingReviewBanner: { padding: 18, borderWidth: 1, borderColor: '#2D579A', borderRadius: 14, backgroundColor: '#0D1B34', flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 15 },
  pendingTitle: { color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  pendingBody: { marginTop: 4, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  liftList: { gap: 9 },
  liftRow: { minHeight: 88, padding: 12, borderWidth: 1, borderColor: colors.line, borderRadius: 14, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', gap: 14 },
  liftRowPressed: { borderColor: colors.brand, backgroundColor: colors.surfaceRaised },
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
  requirementsCard: { padding: 20, borderWidth: 1, borderColor: colors.line, borderRadius: 15, backgroundColor: '#0B1018', gap: 11 },
  requirementsTitle: { marginBottom: 2, color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 13 },
  requirementRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  requirementCheck: { color: colors.green, fontFamily: fonts.bold, fontSize: 11 },
  requirementText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11 },
  setupGrid: { width: '100%', maxWidth: 1040, alignSelf: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 28, alignItems: 'flex-start' },
  setupPreview: { width: 330, height: 550, borderWidth: 1, borderColor: colors.line, borderRadius: 18, backgroundColor: '#05070A' },
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
  processingPercent: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 13, fontVariant: ['tabular-nums'] },
  processingDescription: { maxWidth: 560, textAlign: 'center', marginTop: -8 },
  stepper: { width: '100%', maxWidth: 520, paddingVertical: 14, flexDirection: 'row', justifyContent: 'space-between' },
  stepItem: { flex: 1, alignItems: 'center', gap: 7 },
  stepDot: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: '#252C37' },
  stepDotActive: { backgroundColor: colors.brand },
  stepDotText: { color: '#FFFFFF', fontFamily: fonts.bold, fontSize: 9 },
  stepLabel: { color: colors.textMuted, fontFamily: fonts.medium, fontSize: 10 },
  stepLabelActive: { color: colors.textPrimary },
  reviewGrid: { width: '100%', maxWidth: 1120, alignSelf: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 28, alignItems: 'flex-start' },
  reviewMedia: { width: 390, maxWidth: '100%', borderWidth: 1, borderColor: colors.line, borderRadius: 18, overflow: 'hidden', backgroundColor: '#05070A' },
  reviewImage: { width: '100%', height: 620, resizeMode: 'cover' },
  reviewControls: { minHeight: 58, paddingHorizontal: 13, flexDirection: 'row', alignItems: 'center', gap: 11, backgroundColor: '#090D13' },
  playButton: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.brand },
  playButtonText: { color: '#FFFFFF', fontSize: 11 },
  timeline: { flex: 1, height: 4, borderRadius: 2, overflow: 'hidden', backgroundColor: '#303947' },
  timelineProgress: { width: '28%', height: '100%', backgroundColor: colors.brand },
  timecode: { color: colors.textMuted, fontFamily: fonts.medium, fontSize: 9, fontVariant: ['tabular-nums'] },
  mediaDescription: { maxWidth: 390, marginTop: 10, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 10, lineHeight: 16 },
  reviewPanel: { flex: 1, minWidth: 330, gap: 18 },
  reviewTitleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 },
  readyBadge: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, backgroundColor: colors.greenSoft },
  readyBadgeText: { color: colors.green, fontFamily: fonts.bold, fontSize: 9 },
  metricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  metricCard: { flex: 1, minWidth: 120, minHeight: 110, padding: 14, borderWidth: 1, borderColor: colors.line, borderRadius: 13, backgroundColor: colors.surface },
  metricLabel: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 9 },
  metricValue: { marginTop: 12, color: colors.textPrimary, fontFamily: fonts.display, fontSize: 20 },
  metricDetail: { marginTop: 6, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 9 },
  cueCard: { padding: 19, borderWidth: 1, borderColor: '#294A7D', borderRadius: 14, backgroundColor: '#0D1A30' },
  cueLabel: { color: colors.blueText, fontFamily: fonts.bold, fontSize: 9, letterSpacing: 1 },
  cueTitle: { marginTop: 12, color: colors.textPrimary, fontFamily: fonts.semibold, fontSize: 16, lineHeight: 23 },
  cueBody: { marginTop: 8, color: colors.textMuted, fontFamily: fonts.regular, fontSize: 11, lineHeight: 18 },
  disclosureButton: { minHeight: 50, paddingHorizontal: 15, borderWidth: 1, borderColor: colors.line, borderRadius: 12, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  disclosureTitle: { color: colors.secondaryText, fontFamily: fonts.semibold, fontSize: 12 },
  disclosureIcon: { color: colors.blueText, fontFamily: fonts.regular, fontSize: 22 },
  workoutFields: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  expiryText: { color: colors.textMuted, fontFamily: fonts.regular, fontSize: 9 },
  savedHeader: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-end', gap: 18 },
  filterRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  filterChip: { minHeight: 34, paddingHorizontal: 13, borderWidth: 1, borderColor: colors.line, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface },
  filterChipActive: { borderColor: colors.brand, backgroundColor: colors.blueSoft },
  filterChipText: { color: colors.textMuted, fontFamily: fonts.semibold, fontSize: 10 },
  filterChipTextActive: { color: colors.blueText },
  savedList: { width: '100%', maxWidth: 880, gap: 10 },
  detailTopRow: { width: '100%', maxWidth: 1120, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  detailLoad: { color: colors.blueText, fontFamily: fonts.display, fontSize: 28 },
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
