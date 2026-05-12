import { Ionicons } from '@expo/vector-icons';
import { useEffect, useMemo, useState } from 'react';
import {
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  ANGLE_OPTIONS,
  CameraAngle,
  EXERCISE_OPTIONS,
  ExerciseOption,
  VideoSetupSelection,
} from '../constants/videoSetup';
import tokens from '../theme/tokens';
import Button from './Button';
import Input from './Input';

type VideoSetupModalProps = {
  visible: boolean;
  initialSelection?: VideoSetupSelection | null;
  onContinue: (selection: VideoSetupSelection) => void;
  onCancel: () => void;
  availableWidth?: number;
  availableHeight?: number;
};

function normalizeValue(value: string) {
  return value.trim().toLowerCase();
}

export default function VideoSetupModal({
  visible,
  initialSelection,
  onContinue,
  onCancel,
  availableWidth,
  availableHeight,
}: VideoSetupModalProps) {
  const { height: windowHeight, width: windowWidth } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [exerciseQuery, setExerciseQuery] = useState(initialSelection?.exercise ?? '');
  const [selectedExercise, setSelectedExercise] = useState<ExerciseOption | null>(
    initialSelection?.exercise ?? null
  );
  const [selectedAngle, setSelectedAngle] = useState<CameraAngle | null>(
    initialSelection?.angle ?? null
  );
  const [exerciseFocused, setExerciseFocused] = useState(false);
  const [angleMenuOpen, setAngleMenuOpen] = useState(false);

  const resolvedWidth = availableWidth ?? windowWidth;
  const resolvedHeight = availableHeight ?? windowHeight;
  const modalMaxHeight = Math.min(
    resolvedHeight * 0.78,
    Math.max(resolvedHeight - insets.top - insets.bottom - 24, 320)
  );
  const modalWidth = Math.min(Math.max(resolvedWidth - 32, 280), 350);

  useEffect(() => {
    if (!visible) {
      return;
    }

    setExerciseQuery(initialSelection?.exercise ?? '');
    setSelectedExercise(initialSelection?.exercise ?? null);
    setSelectedAngle(initialSelection?.angle ?? null);
    setExerciseFocused(false);
    setAngleMenuOpen(false);
  }, [initialSelection, visible]);

  const filteredExercises = useMemo(() => {
    const normalizedQuery = normalizeValue(exerciseQuery);

    if (!normalizedQuery) {
      return EXERCISE_OPTIONS;
    }

    return EXERCISE_OPTIONS.filter((exercise) =>
      normalizeValue(exercise).includes(normalizedQuery)
    );
  }, [exerciseQuery]);

  const canContinue = selectedExercise !== null && selectedAngle !== null;
  const validationMessage =
    exerciseQuery.trim().length > 0 && selectedExercise === null
      ? 'Choose an exercise from the list.'
      : 'Select an exercise and camera angle to continue.';

  const handleExerciseChange = (value: string) => {
    setExerciseQuery(value);
    setExerciseFocused(true);
    setAngleMenuOpen(false);

    if (normalizeValue(selectedExercise ?? '') !== normalizeValue(value)) {
      setSelectedExercise(null);
    }
  };

  const handleExerciseSelect = (exercise: ExerciseOption) => {
    setExerciseQuery(exercise);
    setSelectedExercise(exercise);
    setExerciseFocused(false);
  };

  const handleAngleSelect = (angle: CameraAngle) => {
    setSelectedAngle(angle);
    setAngleMenuOpen(false);
  };

  const handleContinue = () => {
    if (!selectedExercise || !selectedAngle) {
      return;
    }

    onContinue({
      exercise: selectedExercise,
      angle: selectedAngle,
    });
  };

  const modalBody = (
    <SafeAreaView style={styles.safeArea} edges={['top', 'bottom']}>
      <View style={styles.backdrop}>
        <View style={[styles.card, { width: modalWidth, maxHeight: modalMaxHeight }]}>
          <ScrollView
            bounces={false}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={styles.scrollContent}
          >
            <Text style={styles.title}>Video Setup</Text>
            <Text style={styles.subtitle}>
              Choose your exercise and camera angle before selecting a video.
            </Text>

            <View style={styles.section}>
              <Input
                label="Exercise Type"
                placeholder="Search exercises"
                value={exerciseQuery}
                onChangeText={handleExerciseChange}
                editable
                autoFocus
                autoCapitalize="words"
                onFocus={() => {
                  setExerciseFocused(true);
                  setAngleMenuOpen(false);
                }}
              />

              {exerciseFocused ? (
                <View style={styles.suggestionsCard}>
                  <ScrollView
                    nestedScrollEnabled
                    showsVerticalScrollIndicator={false}
                    keyboardShouldPersistTaps="handled"
                  >
                    {filteredExercises.length > 0 ? (
                      filteredExercises.map((exercise, index) => {
                        const isSelected = selectedExercise === exercise;
                        const isLastItem = index === filteredExercises.length - 1;

                        return (
                          <Pressable
                            key={exercise}
                            onPress={() => handleExerciseSelect(exercise)}
                            style={[
                              styles.suggestionItem,
                              isSelected ? styles.suggestionItemSelected : null,
                              isLastItem ? styles.lastListItem : null,
                            ]}
                          >
                            <Text
                              style={[
                                styles.suggestionText,
                                isSelected ? styles.suggestionTextSelected : null,
                              ]}
                            >
                              {exercise}
                            </Text>
                            {isSelected ? (
                              <Ionicons
                                name="checkmark"
                                size={16}
                                color={tokens.colors.textPrimary}
                              />
                            ) : null}
                          </Pressable>
                        );
                      })
                    ) : (
                      <Text style={styles.emptyStateText}>No matching exercises.</Text>
                    )}
                  </ScrollView>
                </View>
              ) : null}
            </View>

            <View style={styles.section}>
              <Text style={styles.fieldLabel}>Camera Angle</Text>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setAngleMenuOpen((current) => !current);
                  setExerciseFocused(false);
                }}
                style={[
                  styles.dropdownTrigger,
                  angleMenuOpen ? styles.dropdownTriggerActive : null,
                ]}
              >
                <Text
                  style={[
                    styles.dropdownValue,
                    selectedAngle ? styles.dropdownValueSelected : null,
                  ]}
                >
                  {selectedAngle ?? 'Select angle'}
                </Text>
                <Ionicons
                  name={angleMenuOpen ? 'chevron-up' : 'chevron-down'}
                  size={18}
                  color={tokens.colors.textMuted}
                />
              </Pressable>

              {angleMenuOpen ? (
                <View style={styles.dropdownMenu}>
                  <ScrollView
                    nestedScrollEnabled
                    showsVerticalScrollIndicator={false}
                    keyboardShouldPersistTaps="handled"
                  >
                    {ANGLE_OPTIONS.map((angle, index) => {
                      const isSelected = selectedAngle === angle;
                      const isLastItem = index === ANGLE_OPTIONS.length - 1;

                      return (
                        <Pressable
                          key={angle}
                          onPress={() => handleAngleSelect(angle)}
                          style={[
                            styles.dropdownOption,
                            isSelected ? styles.dropdownOptionSelected : null,
                            isLastItem ? styles.lastListItem : null,
                          ]}
                        >
                          <Text
                            style={[
                              styles.dropdownOptionText,
                              isSelected ? styles.dropdownOptionTextSelected : null,
                            ]}
                          >
                            {angle}
                          </Text>
                          {isSelected ? (
                            <Ionicons
                              name="checkmark"
                              size={16}
                              color={tokens.colors.textPrimary}
                            />
                          ) : null}
                        </Pressable>
                      );
                    })}
                  </ScrollView>
                </View>
              ) : null}
            </View>

            <Text style={styles.validationText}>{validationMessage}</Text>

            <View style={styles.actions}>
              <Button
                label="Continue"
                onPress={handleContinue}
                disabled={!canContinue}
                style={styles.actionButton}
              />
              <Pressable onPress={onCancel} style={styles.cancelButton}>
                <Text style={styles.cancelText}>Cancel</Text>
              </Pressable>
            </View>
          </ScrollView>
        </View>
      </View>
    </SafeAreaView>
  );

  if (!visible) {
    return null;
  }

  if (Platform.OS === 'web') {
    return <View style={styles.webOverlay}>{modalBody}</View>;
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onCancel}
      presentationStyle="overFullScreen"
    >
      {modalBody}
    </Modal>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
  },
  webOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 20,
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.78)',
    paddingHorizontal: 16,
    paddingVertical: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  card: {
    borderRadius: 20,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#12161D',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 12 },
    elevation: 12,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 22,
    paddingBottom: 18,
  },
  title: {
    color: tokens.colors.textPrimary,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '700',
  },
  subtitle: {
    marginTop: 8,
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  section: {
    marginTop: 20,
  },
  fieldLabel: {
    color: tokens.colors.textMuted,
    fontSize: 16,
    lineHeight: 20,
    marginBottom: 10,
  },
  suggestionsCard: {
    marginTop: 10,
    maxHeight: 220,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0F1218',
    overflow: 'hidden',
  },
  suggestionItem: {
    minHeight: 48,
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#243041',
  },
  suggestionItemSelected: {
    backgroundColor: '#1A2432',
  },
  lastListItem: {
    borderBottomWidth: 0,
  },
  suggestionText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 20,
  },
  suggestionTextSelected: {
    fontWeight: '600',
  },
  emptyStateText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  dropdownTrigger: {
    minHeight: 48,
    borderRadius: tokens.radii.input,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: tokens.colors.inputBg,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dropdownTriggerActive: {
    borderColor: tokens.colors.brand,
  },
  dropdownValue: {
    color: tokens.colors.textMuted,
    fontSize: 15,
    lineHeight: 20,
  },
  dropdownValueSelected: {
    color: tokens.colors.textPrimary,
  },
  dropdownMenu: {
    marginTop: 10,
    maxHeight: 180,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0F1218',
    overflow: 'hidden',
  },
  dropdownOption: {
    minHeight: 48,
    paddingHorizontal: 16,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#243041',
  },
  dropdownOptionSelected: {
    backgroundColor: '#1A2432',
  },
  dropdownOptionText: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    lineHeight: 20,
  },
  dropdownOptionTextSelected: {
    fontWeight: '600',
  },
  validationText: {
    marginTop: 16,
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  actions: {
    marginTop: 20,
    gap: 12,
  },
  actionButton: {
    width: '100%',
  },
  cancelButton: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 10,
  },
  cancelText: {
    color: tokens.colors.textMuted,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '600',
  },
});
