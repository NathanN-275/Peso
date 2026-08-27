import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardTypeOptions,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {
  LoadUnit,
  parseWorkoutSaveDetails,
  resolveStoredLoadUnit,
  WorkoutSaveDetails,
} from '../../lib/workoutSavePolicy';
import tokens from '../theme/tokens';
import ReviewBottomSheet from './ReviewBottomSheet';

const LOAD_UNIT_PREFERENCE_KEY = 'peso:workout-load-unit';

type WorkoutDetailsSheetProps = {
  visible: boolean;
  detectedReps: number;
  onCancel: () => void;
  onSubmit: (details: WorkoutSaveDetails) => Promise<void>;
};

export default function WorkoutDetailsSheet({
  visible,
  detectedReps,
  onCancel,
  onSubmit,
}: WorkoutDetailsSheetProps) {
  const [repsText, setRepsText] = useState('');
  const [loadText, setLoadText] = useState('');
  const [loadUnit, setLoadUnit] = useState<LoadUnit>('lb');
  const [userNotes, setUserNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) {
      return;
    }

    setRepsText('');
    setLoadText('');
    setUserNotes('');
    setErrorMessage(null);
    void AsyncStorage.getItem(LOAD_UNIT_PREFERENCE_KEY)
      .then((storedUnit) => setLoadUnit(resolveStoredLoadUnit(storedUnit)))
      .catch(() => setLoadUnit('lb'));
  }, [detectedReps, visible]);

  const close = () => {
    if (!submitting) {
      onCancel();
    }
  };

  const submit = async () => {
    if (submitting) {
      return;
    }

    const parsed = parseWorkoutSaveDetails(repsText, loadText, loadUnit);
    if (!parsed.ok) {
      setErrorMessage(parsed.error);
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);

    try {
      await onSubmit({
        ...parsed.value,
        user_notes: userNotes.trim() || null,
      });
      await AsyncStorage.setItem(LOAD_UNIT_PREFERENCE_KEY, loadUnit);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to save this video.');
    } finally {
      setSubmitting(false);
    }
  };

  const numberKeyboard: KeyboardTypeOptions = 'number-pad';
  const decimalKeyboard: KeyboardTypeOptions = 'decimal-pad';

  return (
    <ReviewBottomSheet
      visible={visible}
      title="Workout details"
      onClose={close}
      showCloseButton={false}
      sheetStyle={styles.sheet}
    >
      <View style={styles.content}>
        <Text style={styles.subtitle}>
          Enter what you performed. The model detected {detectedReps} reps for comparison.
        </Text>

        <View style={styles.field}>
          <View style={styles.labelRow}>
            <Text style={styles.label}>Reps performed</Text>
            <Text style={styles.optionalLabel}>(optional)</Text>
          </View>
          <TextInput
            testID="workout-reps"
            accessibilityLabel="Reps performed"
            value={repsText}
            onChangeText={setRepsText}
            editable={!submitting}
            keyboardType={numberKeyboard}
            inputMode="numeric"
            placeholder="2"
            placeholderTextColor={tokens.colors.textMuted}
            style={styles.input}
          />
        </View>

        <View style={styles.field}>
          <View style={styles.labelRow}>
            <Text style={styles.label}>Weight lifted</Text>
            <Text style={styles.optionalLabel}>(optional)</Text>
          </View>
          <View style={styles.loadRow}>
            <TextInput
              testID="workout-load"
              accessibilityLabel="Weight lifted"
              value={loadText}
              onChangeText={setLoadText}
              editable={!submitting}
              keyboardType={decimalKeyboard}
              inputMode="decimal"
              placeholder="225"
              placeholderTextColor={tokens.colors.textMuted}
              style={[styles.input, styles.loadInput]}
            />
            <View style={styles.unitGroup}>
              {(['lb', 'kg'] as const).map((unit) => (
                <Pressable
                  key={unit}
                  accessibilityRole="button"
                  accessibilityState={{ selected: loadUnit === unit }}
                  onPress={() => setLoadUnit(unit)}
                  disabled={submitting}
                  style={[styles.unitButton, loadUnit === unit && styles.unitButtonSelected]}
                >
                  <Text style={[styles.unitText, loadUnit === unit && styles.unitTextSelected]}>
                    {unit}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        </View>

        <View style={styles.field}>
          <View style={styles.labelRow}>
            <Text style={styles.label}>Notes</Text>
            <Text style={styles.optionalLabel}>(optional)</Text>
          </View>
          <TextInput
            testID="workout-notes"
            accessibilityLabel="Workout notes"
            value={userNotes}
            onChangeText={setUserNotes}
            editable={!submitting}
            multiline
            placeholder="How did the set feel?"
            placeholderTextColor={tokens.colors.textMuted}
            style={[styles.input, styles.notesInput]}
          />
        </View>

        {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}

        <Pressable
          testID="workout-save"
          accessibilityRole="button"
          onPress={() => {
            void submit();
          }}
          disabled={submitting}
          style={[styles.saveButton, submitting && styles.disabledButton]}
        >
          {submitting ? (
            <ActivityIndicator color="#07111D" />
          ) : (
            <Text style={styles.saveButtonText}>Save Workout</Text>
          )}
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={close}
          disabled={submitting}
          style={[styles.cancelButton, submitting && styles.disabledButton]}
        >
          <Text style={styles.cancelButtonText}>Cancel</Text>
        </Pressable>
      </View>
    </ReviewBottomSheet>
  );
}

const styles = StyleSheet.create({
  sheet: {
    maxHeight: '72%',
    backgroundColor: '#202020',
    borderColor: '#343434',
    paddingHorizontal: 22,
    paddingBottom: 34,
  },
  content: {
    gap: 16,
  },
  subtitle: {
    color: '#D6D6D6',
    fontSize: 14,
    lineHeight: 20,
  },
  field: {
    gap: 7,
  },
  labelRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 5,
  },
  label: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '700',
  },
  optionalLabel: {
    color: '#A7A7A7',
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '400',
  },
  input: {
    minHeight: 50,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#10141B',
    color: tokens.colors.textPrimary,
    paddingHorizontal: 14,
    fontSize: 17,
  },
  notesInput: {
    minHeight: 84,
    paddingTop: 13,
    textAlignVertical: 'top',
  },
  loadRow: {
    flexDirection: 'row',
    gap: 10,
  },
  loadInput: {
    flex: 1,
  },
  unitGroup: {
    flexDirection: 'row',
    overflow: 'hidden',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
  },
  unitButton: {
    minWidth: 54,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#10141B',
  },
  unitButtonSelected: {
    backgroundColor: tokens.colors.brand,
  },
  unitText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    fontWeight: '800',
  },
  unitTextSelected: {
    color: '#07111D',
  },
  errorText: {
    color: '#FF8A8A',
    fontSize: 13,
    lineHeight: 18,
    textAlign: 'center',
  },
  saveButton: {
    minHeight: 54,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: tokens.colors.brand,
  },
  saveButtonText: {
    color: '#07111D',
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '800',
  },
  cancelButton: {
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#4A4A4A',
    backgroundColor: '#2A2A2A',
  },
  cancelButtonText: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '700',
  },
  disabledButton: {
    opacity: 0.55,
  },
});
