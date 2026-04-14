import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import BottomNav, { NAV_HEIGHT } from '../components/BottomNav';
import Button from '../components/Button';
import tokens from '../theme/tokens';

type AddVideoScreenProps = {
  onHomePress?: () => void;
  onAddPress?: () => void;
  onProfilePress?: () => void;
};

export default function AddVideoScreen({
  onHomePress,
  onAddPress,
  onProfilePress,
}: AddVideoScreenProps) {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.content}>
          <Button label="Record New Video" style={styles.actionButton} />
          <Button label="Upload Video" style={styles.actionButton} />
        </View>

        <BottomNav
          activeTab="add"
          onHomePress={onHomePress}
          onAddPress={onAddPress}
          onProfilePress={onProfilePress}
        />
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
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.screenX,
    paddingTop: 72,
    paddingBottom: NAV_HEIGHT + 96,
    gap: 26,
  },
  actionButton: {
    width: '100%',
    maxWidth: 230,
    minHeight: 72,
    borderRadius: 9,
    paddingHorizontal: 24,
    paddingVertical: 18,
    backgroundColor: '#3B6EEA',
  },
});
