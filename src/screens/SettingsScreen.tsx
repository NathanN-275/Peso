import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { deleteAccount } from '../../lib/backendApi';
import {
  getProfileDisplayName,
  loadOwnProfile,
  saveOwnProfile,
  uploadProfileAvatar,
} from '../../lib/profile';
import type { UserProfile } from '../../lib/profile';
import { supabase } from '../../lib/supabase';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import Button from '../components/Button';
import Input from '../components/Input';
import tokens from '../theme/tokens';

type SettingsPanel =
  | 'main'
  | 'profile'
  | 'account'
  | 'notifications'
  | 'workouts'
  | 'privacy'
  | 'units'
  | 'language';

type SettingsScreenProps = {
  onBack: () => void;
  onHomePress?: () => void;
  onAddPress?: () => void;
  onProfilePress?: () => void;
  onManageSavedVideos?: () => void;
  onAccountDeleted?: () => void;
};

const DELETE_CONFIRMATION_TEXT = 'DELETE';

function SettingsAction({
  icon,
  label,
  detail,
  destructive = false,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  detail?: string;
  destructive?: boolean;
  onPress?: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.actionRow}>
      <View style={[styles.actionIcon, destructive && styles.destructiveIcon]}>
        <Ionicons name={icon} size={22} color={destructive ? '#FFB4B4' : tokens.colors.textPrimary} />
      </View>
      <View style={styles.actionCopy}>
        <Text style={[styles.actionLabel, destructive && styles.destructiveText]} numberOfLines={1}>
          {label}
        </Text>
        {detail ? <Text style={styles.actionDetail} numberOfLines={2}>{detail}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={22} color="#8E96A3" />
    </Pressable>
  );
}

function SettingsSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      <View style={styles.actionStack}>{children}</View>
    </View>
  );
}

function PlaceholderPanel({
  title,
  copy,
}: {
  title: string;
  copy: string;
}) {
  return (
    <View style={styles.placeholderPanel}>
      <Text style={styles.placeholderTitle}>{title}</Text>
      <Text style={styles.placeholderCopy}>{copy}</Text>
    </View>
  );
}

function validateUsername(username: string) {
  const trimmedUsername = username.trim();

  if (!trimmedUsername) {
    return null;
  }

  if (!/^[A-Za-z0-9_]{3,30}$/.test(trimmedUsername)) {
    return 'Username must be 3-30 letters, numbers, or underscores.';
  }

  return null;
}

export default function SettingsScreen({
  onBack,
  onHomePress,
  onAddPress,
  onProfilePress,
  onManageSavedVideos,
  onAccountDeleted,
}: SettingsScreenProps) {
  const { session, user, signOut } = useAuth();
  const [panel, setPanel] = useState<SettingsPanel>('main');
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState(user?.email ?? '');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [updatingEmail, setUpdatingEmail] = useState(false);
  const [updatingPassword, setUpdatingPassword] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [deleteDialogVisible, setDeleteDialogVisible] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadProfile = async () => {
      if (!user) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setErrorMessage(null);

      try {
        const nextProfile = await loadOwnProfile(user);

        if (cancelled) {
          return;
        }

        setProfile(nextProfile);
        setUsername(nextProfile.username ?? '');
        setDisplayName(nextProfile.display_name ?? '');
        setEmail(user.email ?? '');
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : 'Unable to load settings.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadProfile();

    return () => {
      cancelled = true;
    };
  }, [user]);

  const clearMessages = () => {
    setMessage(null);
    setErrorMessage(null);
  };

  const showPanel = (nextPanel: SettingsPanel) => {
    clearMessages();
    setPanel(nextPanel);
  };

  const handleTopBack = () => {
    if (panel === 'main') {
      onBack();
      return;
    }

    clearMessages();
    setPanel('main');
  };

  const handleSaveProfile = async () => {
    if (!user) {
      return;
    }

    const usernameError = validateUsername(username);

    if (usernameError) {
      setErrorMessage(usernameError);
      setMessage(null);
      return;
    }

    if (displayName.trim().length > 80) {
      setErrorMessage('Display name must be 80 characters or less.');
      setMessage(null);
      return;
    }

    setSavingProfile(true);
    clearMessages();

    try {
      const nextProfile = await saveOwnProfile(user, {
        username,
        display_name: displayName,
        avatar_path: profile?.avatar_path ?? null,
      });

      setProfile(nextProfile);
      setUsername(nextProfile.username ?? '');
      setDisplayName(nextProfile.display_name ?? '');
      setMessage('Profile updated.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to update profile.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChooseAvatar = async () => {
    if (!user || savingProfile) {
      return;
    }

    clearMessages();

    try {
      if (Platform.OS !== 'web') {
        let permission = await ImagePicker.getMediaLibraryPermissionsAsync();

        if (!permission.granted) {
          permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        }

        if (!permission.granted) {
          setErrorMessage('Photo library access is required.');
          return;
        }
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.85,
      });

      if (result.canceled || !result.assets[0]) {
        return;
      }

      setSavingProfile(true);
      const uploadResult = await uploadProfileAvatar(user, result.assets[0], profile?.avatar_path);
      const nextProfile = await saveOwnProfile(user, {
        username,
        display_name: displayName,
        avatar_path: uploadResult.avatarPath,
      });

      setProfile({
        ...nextProfile,
        avatar_url: uploadResult.avatarUrl,
      });
      setMessage('Profile picture updated.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to update profile picture.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleUpdateEmail = async () => {
    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setErrorMessage('Enter an email address.');
      setMessage(null);
      return;
    }

    if (!supabase) {
      setErrorMessage('Supabase is not configured.');
      setMessage(null);
      return;
    }

    setUpdatingEmail(true);
    clearMessages();

    try {
      const { error } = await supabase.auth.updateUser({ email: trimmedEmail });

      if (error) {
        throw error;
      }

      setMessage('Email update started. Check your inbox.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to update email.');
    } finally {
      setUpdatingEmail(false);
    }
  };

  const handleUpdatePassword = async () => {
    const trimmedPassword = password.trim();
    const trimmedConfirmPassword = confirmPassword.trim();

    if (trimmedPassword.length < 6) {
      setErrorMessage('Use a password with at least 6 characters.');
      setMessage(null);
      return;
    }

    if (trimmedPassword !== trimmedConfirmPassword) {
      setErrorMessage('Passwords do not match.');
      setMessage(null);
      return;
    }

    if (!supabase) {
      setErrorMessage('Supabase is not configured.');
      setMessage(null);
      return;
    }

    setUpdatingPassword(true);
    clearMessages();

    try {
      const { error } = await supabase.auth.updateUser({ password: trimmedPassword });

      if (error) {
        throw error;
      }

      setPassword('');
      setConfirmPassword('');
      setMessage('Password updated.');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to update password.');
    } finally {
      setUpdatingPassword(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!session?.access_token || deleteConfirmation !== DELETE_CONFIRMATION_TEXT) {
      return;
    }

    setDeletingAccount(true);
    clearMessages();

    try {
      await deleteAccount(session.access_token);
      try {
        await signOut();
      } catch {
        // Deleted auth users may already be invalidated by the backend.
      }
      setDeleteDialogVisible(false);
      onAccountDeleted?.();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to delete account.');
    } finally {
      setDeletingAccount(false);
    }
  };

  const handleLogout = async () => {
    clearMessages();

    try {
      await signOut();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to log out.');
    }
  };

  const renderMessageBlock = () => (
    <>
      {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}
      {message ? <Text style={styles.messageText}>{message}</Text> : null}
    </>
  );

  const renderMainPanel = () => (
    <>
      <SettingsSection title="Account">
        <SettingsAction icon="person-outline" label="Profile" onPress={() => showPanel('profile')} />
        <SettingsAction icon="lock-closed-outline" label="Account" onPress={() => showPanel('account')} />
        <SettingsAction icon="notifications-outline" label="Notifications" onPress={() => showPanel('notifications')} />
      </SettingsSection>

      <SettingsSection title="Preferences">
        <SettingsAction icon="barbell-outline" label="Workouts" onPress={() => showPanel('workouts')} />
        <SettingsAction icon="shield-checkmark-outline" label="Privacy & Data" onPress={() => showPanel('privacy')} />
        <SettingsAction icon="speedometer-outline" label="Units" onPress={() => showPanel('units')} />
        <SettingsAction icon="flag-outline" label="Language" onPress={() => showPanel('language')} />
      </SettingsSection>

      <SettingsSection title="Session">
        <SettingsAction icon="log-out-outline" label="Log Out" onPress={handleLogout} />
      </SettingsSection>
    </>
  );

  const renderProfilePanel = () => (
    <>
      <View style={styles.profileHeader}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Change profile picture"
          onPress={handleChooseAvatar}
          style={styles.avatarButton}
          disabled={savingProfile}
        >
          {profile?.avatar_url ? (
            <Image source={{ uri: profile.avatar_url }} style={styles.avatarImage} resizeMode="cover" />
          ) : (
            <Ionicons name="person" size={52} color="#AEB7C6" />
          )}
          <View style={styles.avatarEditBadge}>
            <Ionicons name="camera" size={15} color={tokens.colors.textPrimary} />
          </View>
        </Pressable>
        <Text style={styles.profileName}>{getProfileDisplayName(profile, user)}</Text>
      </View>

      {renderMessageBlock()}

      <View style={styles.formStack}>
        <Input
          label="Display Name"
          placeholder="Name"
          value={displayName}
          onChangeText={setDisplayName}
          autoCapitalize="words"
        />
        <Input
          label="Username"
          placeholder="username"
          value={username}
          onChangeText={setUsername}
        />
        <Button
          label={savingProfile ? 'Saving...' : 'Save Profile'}
          onPress={handleSaveProfile}
          disabled={savingProfile}
          style={styles.fullButton}
        />
      </View>
    </>
  );

  const renderAccountPanel = () => (
    <>
      {renderMessageBlock()}

      <View style={styles.formStack}>
        <Input
          label="Email"
          placeholder="email@example.com"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          textContentType="emailAddress"
        />
        <Button
          label={updatingEmail ? 'Updating...' : 'Update Email'}
          onPress={handleUpdateEmail}
          disabled={updatingEmail}
          style={styles.fullButton}
        />
        <Input
          label="New Password"
          placeholder="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          textContentType="newPassword"
        />
        <Input
          label="Confirm Password"
          placeholder="Password"
          value={confirmPassword}
          onChangeText={setConfirmPassword}
          secureTextEntry
          textContentType="newPassword"
        />
        <Button
          label={updatingPassword ? 'Updating...' : 'Update Password'}
          onPress={handleUpdatePassword}
          disabled={updatingPassword}
          style={styles.fullButton}
        />
      </View>
    </>
  );

  const renderPrivacyPanel = () => (
    <>
      {renderMessageBlock()}

      <View style={styles.actionStack}>
        <SettingsAction
          icon="folder-open-outline"
          label="Manage Saved Videos"
          detail="Open saved lift library"
          onPress={onManageSavedVideos}
        />
        <SettingsAction icon="download-outline" label="Export Data" detail="Coming soon" />
        <SettingsAction
          icon="trash-outline"
          label="Delete Account"
          detail="Remove profile, videos, and auth account"
          destructive
          onPress={() => {
            setDeleteConfirmation('');
            setDeleteDialogVisible(true);
          }}
        />
      </View>
    </>
  );

  const renderPanel = () => {
    if (loading) {
      return (
        <View style={styles.stateBlock}>
          <ActivityIndicator color={tokens.colors.brand} />
          <Text style={styles.stateText}>Loading settings...</Text>
        </View>
      );
    }

    switch (panel) {
      case 'profile':
        return renderProfilePanel();
      case 'account':
        return renderAccountPanel();
      case 'privacy':
        return renderPrivacyPanel();
      case 'notifications':
        return <PlaceholderPanel title="Notifications" copy="Coming soon." />;
      case 'workouts':
        return <PlaceholderPanel title="Workouts" copy="Coming soon." />;
      case 'units':
        return <PlaceholderPanel title="Units" copy="Coming soon." />;
      case 'language':
        return <PlaceholderPanel title="Language" copy="Coming soon." />;
      case 'main':
      default:
        return renderMainPanel();
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" onPress={handleTopBack} style={styles.backButton}>
            <Ionicons name="arrow-back" size={24} color={tokens.colors.textPrimary} />
          </Pressable>
          <Text style={styles.title}>Settings</Text>
          <View style={styles.topBarSpacer} />
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {renderPanel()}
        </ScrollView>

        <BottomNav
          activeTab="profile"
          onHomePress={onHomePress}
          onAddPress={onAddPress}
          onProfilePress={onProfilePress}
        />

        {deleteDialogVisible ? (
          <View style={styles.deleteOverlay} accessibilityViewIsModal>
            <Pressable
              accessibilityLabel="Close delete account confirmation"
              onPress={() => setDeleteDialogVisible(false)}
              style={StyleSheet.absoluteFill}
            />
            <View style={styles.deleteDialog}>
              <Text style={styles.deleteTitle}>Delete Account</Text>
              <Text style={styles.deleteCopy}>Type DELETE to confirm.</Text>
              <TextInput
                value={deleteConfirmation}
                onChangeText={setDeleteConfirmation}
                autoCapitalize="characters"
                editable={!deletingAccount}
                placeholder={DELETE_CONFIRMATION_TEXT}
                placeholderTextColor={tokens.colors.textMuted}
                style={styles.deleteInput}
              />
              <View style={styles.deleteActions}>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setDeleteDialogVisible(false)}
                  disabled={deletingAccount}
                  style={styles.cancelDeleteButton}
                >
                  <Text style={styles.cancelDeleteText}>Cancel</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  onPress={handleDeleteAccount}
                  disabled={deletingAccount || deleteConfirmation !== DELETE_CONFIRMATION_TEXT}
                  style={[
                    styles.confirmDeleteButton,
                    (deletingAccount || deleteConfirmation !== DELETE_CONFIRMATION_TEXT) && styles.disabledButton,
                  ]}
                >
                  <Text style={styles.confirmDeleteText}>
                    {deletingAccount ? 'Deleting...' : 'Delete'}
                  </Text>
                </Pressable>
              </View>
            </View>
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#000',
  },
  container: {
    flex: 1,
    backgroundColor: '#000',
    overflow: 'hidden',
  },
  topBar: {
    minHeight: 54,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
  },
  backButton: {
    width: 42,
    height: 42,
    alignItems: 'center',
    justifyContent: 'center',
  },
  topBarSpacer: {
    width: 42,
  },
  title: {
    flex: 1,
    color: tokens.colors.textPrimary,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '600',
    textAlign: 'center',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: NAV_HEIGHT + 30,
    gap: 24,
  },
  section: {
    gap: 9,
  },
  sectionTitle: {
    color: '#8B93A1',
    fontSize: 19,
    lineHeight: 25,
    fontWeight: '500',
    paddingHorizontal: 20,
  },
  actionStack: {
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: '#2B2D31',
  },
  actionRow: {
    minHeight: 62,
    backgroundColor: '#1A1B1F',
    borderBottomWidth: 1,
    borderBottomColor: '#2B2D31',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 9,
    gap: 14,
  },
  actionIcon: {
    width: 34,
    alignItems: 'center',
    justifyContent: 'center',
  },
  destructiveIcon: {},
  actionCopy: {
    flex: 1,
    minWidth: 0,
  },
  actionLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 19,
    lineHeight: 24,
    fontWeight: '500',
  },
  destructiveText: {
    color: '#FFB4B4',
    fontWeight: '700',
  },
  actionDetail: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
    marginTop: 2,
  },
  profileHeader: {
    alignItems: 'center',
    paddingHorizontal: 20,
    gap: 8,
  },
  avatarButton: {
    width: 92,
    height: 92,
    borderRadius: 46,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#D8D8D8',
  },
  avatarImage: {
    width: '100%',
    height: '100%',
    borderRadius: 46,
  },
  avatarEditBadge: {
    position: 'absolute',
    right: 2,
    bottom: 4,
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: tokens.colors.brand,
    borderWidth: 2,
    borderColor: '#000',
  },
  profileName: {
    color: tokens.colors.textPrimary,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '800',
    textAlign: 'center',
  },
  formStack: {
    paddingHorizontal: 20,
    gap: 10,
  },
  fullButton: {
    width: '100%',
    alignSelf: 'stretch',
  },
  stateBlock: {
    minHeight: 220,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  stateText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
  },
  messageText: {
    color: '#9DE7B0',
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  placeholderPanel: {
    paddingHorizontal: 20,
    gap: 8,
  },
  placeholderTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '800',
  },
  placeholderCopy: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  deleteOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 100,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    backgroundColor: 'rgba(0, 0, 0, 0.76)',
  },
  deleteDialog: {
    width: '100%',
    maxWidth: 340,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#523038',
    backgroundColor: '#15171B',
    padding: 18,
    gap: 14,
  },
  deleteTitle: {
    color: '#FFB4B4',
    fontSize: 20,
    lineHeight: 26,
    fontWeight: '800',
  },
  deleteCopy: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  deleteInput: {
    height: 46,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#523038',
    backgroundColor: '#0F1116',
    color: tokens.colors.textPrimary,
    paddingHorizontal: 12,
    fontSize: 15,
  },
  deleteActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  cancelDeleteButton: {
    minHeight: 42,
    minWidth: 86,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  cancelDeleteText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    fontWeight: '700',
  },
  confirmDeleteButton: {
    minHeight: 42,
    minWidth: 86,
    borderRadius: 8,
    backgroundColor: '#C33F4A',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
  },
  confirmDeleteText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    fontWeight: '800',
  },
  disabledButton: {
    opacity: 0.55,
  },
});
