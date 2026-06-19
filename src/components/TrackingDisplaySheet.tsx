import { useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import tokens from '../theme/tokens';
import type {
  TrackingAssistance,
  TrackingBodySourceName,
  TrackingPinName,
} from '../types/trackingSetup';
import ReviewBottomSheet from './ReviewBottomSheet';

type TrackingDisplaySheetProps = {
  visible: boolean;
  poseAvailable: boolean;
  poseEnabled: boolean;
  barbellAvailable: boolean;
  barbellEnabled: boolean;
  trackingAssistance?: TrackingAssistance | null;
  onPoseEnabledChange: (enabled: boolean) => void;
  onBarbellEnabledChange: (enabled: boolean) => void;
  onClose: () => void;
};

type TrackingOptionProps = {
  label: string;
  description: string;
  available: boolean;
  enabled: boolean;
  onEnabledChange: (enabled: boolean) => void;
};

const TRACKING_LABELS: Record<string, string> = {
  shoulder: 'Upper Back',
  upper_back: 'Upper Back',
  hip: 'Hip',
  knee: 'Knee',
  ankle: 'Ankle',
  barbell: 'Barbell',
};

const SOURCE_LABELS: Record<string, string> = {
  reference: 'reference',
  pin_guided: 'pin guided',
  pin_estimated: 'pin estimated',
  automatic: 'automatic',
  automatic_recovery: 'automatic recovery',
  stale_pin_rejected: 'stale pin rejected',
  gap: 'gap',
};

function formatPercent(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 'n/a';
  }
  return `${Math.round(value * 100)}%`;
}

function formatReason(value: string) {
  return value.split('_').join(' ');
}

function formatCoverageEntry([name, coverage]: [TrackingPinName, number]) {
  return `${TRACKING_LABELS[name] ?? name}: ${formatPercent(coverage)}`;
}

function formatSourceCounts(
  name: TrackingBodySourceName,
  trackingAssistance: TrackingAssistance
) {
  const counts = trackingAssistance.sourceCounts?.[name];
  if (!counts) {
    return null;
  }
  const parts = Object.entries(counts)
    .filter(([, count]) => Number(count) > 0)
    .map(([source, count]) => `${SOURCE_LABELS[source] ?? source}: ${count}`);

  if (!parts.length) {
    return null;
  }

  return `${TRACKING_LABELS[name] ?? name}: ${parts.join(', ')}`;
}

function CollapsibleDetails({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <View style={styles.detailSection}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((current) => !current)}
        style={({ pressed }) => [
          styles.detailHeader,
          pressed && styles.detailHeaderPressed,
        ]}
      >
        <Text style={styles.detailTitle}>{title}</Text>
        <Text style={styles.detailToggle}>{expanded ? 'Hide' : 'Show'}</Text>
      </Pressable>
      {expanded ? <View style={styles.detailBody}>{children}</View> : null}
    </View>
  );
}

function TrackingOption({
  label,
  description,
  available,
  enabled,
  onEnabledChange,
}: TrackingOptionProps) {
  const effectiveEnabled = available && enabled;

  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityHint={available ? description : 'Unavailable for this video'}
      accessibilityState={{ checked: effectiveEnabled, disabled: !available }}
      disabled={!available}
      onPress={() => onEnabledChange(!effectiveEnabled)}
      style={({ pressed }) => [
        styles.option,
        !available && styles.optionDisabled,
        pressed && available && styles.optionPressed,
      ]}
    >
      <View style={styles.optionCopy}>
        <Text style={[styles.optionLabel, !available && styles.disabledText]}>{label}</Text>
        <Text style={[styles.optionDescription, !available && styles.disabledText]}>
          {available ? description : 'Unavailable for this video'}
        </Text>
      </View>
      <View
        accessible={false}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        pointerEvents="none"
      >
        <Switch
          value={effectiveEnabled}
          disabled={!available}
          trackColor={{ false: '#3A4352', true: tokens.colors.brand }}
          thumbColor={tokens.colors.textPrimary}
          ios_backgroundColor="#3A4352"
        />
      </View>
    </Pressable>
  );
}

export default function TrackingDisplaySheet({
  visible,
  poseAvailable,
  poseEnabled,
  barbellAvailable,
  barbellEnabled,
  trackingAssistance,
  onPoseEnabledChange,
  onBarbellEnabledChange,
  onClose,
}: TrackingDisplaySheetProps) {
  const assistanceMode = trackingAssistance?.actualMode === 'pin_assisted'
    ? 'Pin-assisted'
    : trackingAssistance?.requestedMode === 'pins'
      ? 'Automatic fallback'
      : 'Automatic';
  const coverageEntries = Object.entries(trackingAssistance?.coverage ?? {}) as Array<
    [TrackingPinName, number]
  >;
  const bodySourceNames: TrackingBodySourceName[] = ['upper_back', 'hip', 'knee', 'ankle'];
  const bodySourceLines = trackingAssistance
    ? bodySourceNames
      .map((name) => formatSourceCounts(name, trackingAssistance))
      .filter((line): line is string => Boolean(line))
    : [];
  const rejectionEntries = Object.entries(trackingAssistance?.rejectionReasons ?? {});

  return (
    <ReviewBottomSheet
      visible={visible}
      title="Tracking display"
      onClose={onClose}
      scrollable
      sheetStyle={styles.sheet}
    >
      <View style={styles.content}>
        <Text style={styles.helperText}>
          Choose what appears over the video. Turn both off for a clean view.
        </Text>
        <View style={styles.options}>
          <TrackingOption
            label="Pose overlay"
            description="Body landmarks and connections"
            available={poseAvailable}
            enabled={poseEnabled}
            onEnabledChange={onPoseEnabledChange}
          />
          <TrackingOption
            label="Barbell path"
            description="Tracked bar path over time"
            available={barbellAvailable}
            enabled={barbellEnabled}
            onEnabledChange={onBarbellEnabledChange}
          />
        </View>
        {trackingAssistance?.requestedMode === 'pins' ? (
          <View style={styles.assistancePanel}>
            <View style={styles.assistanceHeadingRow}>
              <Text style={styles.assistanceHeading}>Tracking assistance</Text>
              <Text
                style={[
                  styles.assistanceMode,
                  trackingAssistance.used ? styles.assistanceModeUsed : styles.assistanceModeFallback,
                ]}
              >
                {assistanceMode}
              </Text>
            </View>
            <Text style={styles.assistanceDetail}>
              Body: {trackingAssistance.pinOwnedLandmarkCount ?? trackingAssistance.fusedLandmarkCount ?? 0}{' '}
              pin-owned, {trackingAssistance.fallbackLandmarkCount ?? 0} fallback/rejected
            </Text>
            <Text style={styles.assistanceDetail}>
              Barbell points: {trackingAssistance.manualBarbellPointCount ?? 0} pin-assisted,{' '}
              {trackingAssistance.automaticBarbellPointCount ?? 0} automatic
            </Text>
            {trackingAssistance.selectedSide ? (
              <Text style={styles.assistanceDetail}>
                Body side: {trackingAssistance.selectedSide}
              </Text>
            ) : null}
            {coverageEntries.length > 0 ? (
              <Text style={styles.assistanceDetail}>
                Coverage: {coverageEntries.map(formatCoverageEntry).join(', ')}
              </Text>
            ) : null}
            {trackingAssistance.fallbackReason ? (
              <Text style={styles.assistanceFallbackReason}>
                Fallback reason: {formatReason(trackingAssistance.fallbackReason)}
              </Text>
            ) : null}
            <CollapsibleDetails title="Body details">
              <Text style={styles.assistanceDetail}>
                Guided body points: {trackingAssistance.fusedLandmarkCount ?? 0}
              </Text>
              <Text style={styles.assistanceDetail}>
                Reference anchors: {trackingAssistance.directlyAnchoredLandmarkCount ?? 0}
              </Text>
              <Text style={styles.assistanceDetail}>
                Blended/guided: {trackingAssistance.blendedLandmarkCount ?? 0}
              </Text>
              <Text style={styles.assistanceDetail}>
                Automatic fallbacks: {trackingAssistance.fallbackLandmarkCount ?? 0}
              </Text>
              <Text style={styles.assistanceDetail}>
                Rejected body points: {trackingAssistance.rejectedTrackCount ?? 0}
              </Text>
              <Text style={styles.assistanceDetail}>
                Upper Back anchor frames: {trackingAssistance.upperBackAnchorUsedCount ?? 0}{' '}
                ({formatPercent(trackingAssistance.upperBackAnchorCoverage)})
              </Text>
              {trackingAssistance.velocityCapCount ? (
                <Text style={styles.assistanceDetail}>
                  Velocity caps: {trackingAssistance.velocityCapCount}
                </Text>
              ) : null}
              {bodySourceLines.map((line) => (
                <Text key={line} style={styles.assistanceDetail}>{line}</Text>
              ))}
              {rejectionEntries.length > 0 ? (
                <Text style={styles.assistanceDetail}>
                  Rejections: {rejectionEntries
                    .map(([reason, count]) => `${formatReason(reason)}: ${count}`)
                    .join(', ')}
                </Text>
              ) : null}
            </CollapsibleDetails>
            <CollapsibleDetails title="Barbell details">
              <Text style={styles.assistanceDetail}>
                Seed used: {trackingAssistance.barbellSeedUsed ? 'yes' : 'no'}
              </Text>
              <Text style={styles.assistanceDetail}>
                Pin-assisted barbell points: {trackingAssistance.manualBarbellPointCount ?? 0}
              </Text>
              <Text style={styles.assistanceDetail}>
                Automatic barbell points: {trackingAssistance.automaticBarbellPointCount ?? 0}
              </Text>
            </CollapsibleDetails>
          </View>
        ) : null}
      </View>
    </ReviewBottomSheet>
  );
}

const styles = StyleSheet.create({
  sheet: {
    maxHeight: '78%',
  },
  content: {
    gap: 16,
  },
  helperText: {
    color: tokens.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  options: {
    gap: 10,
  },
  assistancePanel: {
    gap: 6,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0C1016',
    padding: 14,
  },
  assistanceHeadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  assistanceHeading: {
    color: tokens.colors.textPrimary,
    fontSize: 15,
    fontWeight: '700',
  },
  assistanceMode: {
    fontSize: 12,
    fontWeight: '700',
  },
  assistanceModeUsed: {
    color: '#8CC0FF',
  },
  assistanceModeFallback: {
    color: '#FFD080',
  },
  assistanceDetail: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  assistanceFallbackReason: {
    color: '#FFD080',
    fontSize: 13,
    lineHeight: 18,
  },
  detailSection: {
    marginTop: 6,
    borderTopWidth: 1,
    borderTopColor: tokens.colors.inputBorder,
    paddingTop: 8,
  },
  detailHeader: {
    minHeight: 34,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  detailHeaderPressed: {
    opacity: 0.72,
  },
  detailTitle: {
    color: tokens.colors.textPrimary,
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '700',
  },
  detailToggle: {
    color: tokens.colors.brand,
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
  },
  detailBody: {
    gap: 5,
    paddingTop: 2,
  },
  option: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: tokens.colors.inputBorder,
    backgroundColor: '#0C1016',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  optionPressed: {
    backgroundColor: '#151C27',
  },
  optionDisabled: {
    opacity: 0.58,
  },
  optionCopy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  optionLabel: {
    color: tokens.colors.textPrimary,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '700',
  },
  optionDescription: {
    color: tokens.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  disabledText: {
    color: '#7D8797',
  },
});
