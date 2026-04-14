import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, View } from 'react-native';
import tokens from '../theme/tokens';

type BottomNavTab = 'home' | 'add' | 'profile';

type BottomNavProps = {
  activeTab: BottomNavTab;
  onHomePress?: () => void;
  onAddPress?: () => void;
  onProfilePress?: () => void;
};

const NAV_HEIGHT = 62;
const ICON_SIZE = 34;
const INACTIVE_ICON_COLOR = '#174A82';
const BAR_BACKGROUND = '#2A2A2A';

function getIconColor(activeTab: BottomNavTab, tab: BottomNavTab) {
  return activeTab === tab ? tokens.colors.brand : INACTIVE_ICON_COLOR;
}

export default function BottomNav({
  activeTab,
  onHomePress,
  onAddPress,
  onProfilePress,
}: BottomNavProps) {
  return (
    <View style={styles.container}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Home"
        hitSlop={12}
        onPress={onHomePress}
        style={styles.iconButton}
      >
        <Ionicons name="home-outline" size={ICON_SIZE} color={getIconColor(activeTab, 'home')} />
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Add video"
        hitSlop={12}
        onPress={onAddPress}
        style={styles.iconButton}
      >
        <Ionicons
          name="add-circle-outline"
          size={ICON_SIZE}
          color={getIconColor(activeTab, 'add')}
        />
      </Pressable>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Profile"
        hitSlop={12}
        onPress={onProfilePress}
        style={styles.iconButton}
      >
        <Ionicons
          name="person-outline"
          size={ICON_SIZE}
          color={getIconColor(activeTab, 'profile')}
        />
      </Pressable>
    </View>
  );
}

export { NAV_HEIGHT };

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: NAV_HEIGHT,
    backgroundColor: BAR_BACKGROUND,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: 24,
  },
  iconButton: {
    minWidth: 56,
    minHeight: 56,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
