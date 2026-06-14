import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import tokens from '../theme/tokens';

type ConfirmationDialogProps = {
  visible: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  checkboxLabel?: string;
  checkboxValue?: boolean;
  onCheckboxChange?: (value: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmationDialog({
  visible,
  title,
  message,
  confirmLabel,
  cancelLabel = 'Cancel',
  destructive = false,
  checkboxLabel,
  checkboxValue = false,
  onCheckboxChange,
  onConfirm,
  onCancel,
}: ConfirmationDialogProps) {
  if (!visible) {
    return null;
  }

  return (
    <View style={styles.overlay} accessibilityViewIsModal>
      <Pressable
        accessibilityLabel="Close confirmation"
        onPress={onCancel}
        style={StyleSheet.absoluteFill}
      />
      <View style={styles.dialog}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.message}>{message}</Text>
        {checkboxLabel ? (
          <Pressable
            accessibilityRole="checkbox"
            accessibilityState={{ checked: checkboxValue }}
            onPress={() => onCheckboxChange?.(!checkboxValue)}
            style={styles.checkboxRow}
          >
            <View style={[styles.checkbox, checkboxValue && styles.checkboxChecked]}>
              {checkboxValue ? <Ionicons name="checkmark" size={16} color="#05070A" /> : null}
            </View>
            <Text style={styles.checkboxLabel}>{checkboxLabel}</Text>
          </Pressable>
        ) : null}
        <View style={styles.actions}>
          <Pressable accessibilityRole="button" onPress={onCancel} style={styles.cancelButton}>
            <Text style={styles.cancelText}>{cancelLabel}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={onConfirm}
            style={[styles.confirmButton, destructive && styles.destructiveButton]}
          >
            <Text style={styles.confirmText}>{confirmLabel}</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 100,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    backgroundColor: 'rgba(0, 0, 0, 0.72)',
  },
  dialog: {
    width: '100%',
    maxWidth: 340,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#151A22',
    padding: 20,
    gap: 14,
  },
  title: {
    color: tokens.colors.textPrimary,
    fontSize: 19,
    lineHeight: 24,
    fontWeight: '700',
  },
  message: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  checkboxRow: {
    minHeight: 40,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: tokens.colors.textMuted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxChecked: {
    borderColor: tokens.colors.brand,
    backgroundColor: tokens.colors.brand,
  },
  checkboxLabel: {
    flex: 1,
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 19,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  cancelButton: {
    minHeight: 42,
    minWidth: 84,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    paddingHorizontal: 14,
  },
  cancelText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    fontWeight: '600',
  },
  confirmButton: {
    minHeight: 42,
    minWidth: 84,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 10,
    backgroundColor: tokens.colors.brand,
    paddingHorizontal: 14,
  },
  destructiveButton: { backgroundColor: '#C33F4A' },
  confirmText: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    fontWeight: '700',
  },
});
