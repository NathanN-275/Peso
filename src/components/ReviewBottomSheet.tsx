import { Pressable, StyleSheet, Text, View } from 'react-native';
import tokens from '../theme/tokens';

type ReviewBottomSheetProps = {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
};

export default function ReviewBottomSheet({
  visible,
  title,
  onClose,
  children,
}: ReviewBottomSheetProps) {
  if (!visible) {
    return null;
  }

  return (
    <View style={styles.backdrop}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
      <View style={styles.sheet}>
        <View style={styles.handle} />
        <View style={styles.header}>
          <Text style={styles.title}>{title}</Text>
          <Pressable accessibilityRole="button" onPress={onClose} style={styles.closeButton}>
            <Text style={styles.closeText}>Close</Text>
          </Pressable>
        </View>
        <View style={styles.content}>{children}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0, 0, 0, 0.58)',
    zIndex: 30,
  },
  sheet: {
    width: '100%',
    maxHeight: '52%',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#10141B',
    paddingHorizontal: 18,
    paddingTop: 10,
    paddingBottom: 24,
    gap: 14,
  },
  content: {
    flexShrink: 1,
  },
  handle: {
    width: 44,
    height: 4,
    alignSelf: 'center',
    borderRadius: 4,
    backgroundColor: '#3A4352',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    color: tokens.colors.textPrimary,
    fontSize: 20,
    lineHeight: 26,
    fontWeight: '700',
  },
  closeButton: {
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  closeText: {
    color: tokens.colors.brand,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '700',
  },
});
