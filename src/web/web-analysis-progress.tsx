import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import VideoThumbnail from '../components/VideoThumbnail';
import type { AnalysisActivityItem } from '../types/videoAnalysis';
import { ANALYSIS_STAGES, analysisElapsed, analysisStepState, formatElapsed } from '../../lib/analysisActivityPresentation';

export function AnalysisIdentity({ activity }: { activity: AnalysisActivityItem }) {
  const date = new Date(activity.created_at);
  const title = activity.source_file_name || `${activity.view_type === 'side' ? 'Side-view ' : ''}${activity.exercise_type || 'Lift'} video`;
  return <View style={styles.identity}>
    <VideoThumbnail videoId={activity.video_id} available={activity.thumbnail_available === true}
      legacyUrl={activity.thumbnail_url} fit="contain" style={styles.thumbnail}
      label={`Preview of ${title}`} />
    <View style={styles.identityCopy}>
      <Text selectable style={styles.name}>{title}</Text>
      <Text selectable style={styles.muted}>{Number.isFinite(date.getTime()) ? `Queued ${date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit' })}` : 'Queued time unavailable'}</Text>
    </View>
  </View>;
}

export function AnalysisProgress({ activity, compact = false }: { activity: AnalysisActivityItem; compact?: boolean }) {
  const [now, setNow] = useState(Date.now);
  const active = activity.status === 'queued' || activity.status === 'processing';
  useEffect(() => {
    if (!active) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const update = () => {
      clearInterval(timer); setNow(Date.now());
      if (document.visibilityState === 'visible') timer = setInterval(() => setNow(Date.now()), 1000);
    };
    update(); document.addEventListener('visibilitychange', update);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [active, activity.job_id]);
  const elapsed = analysisElapsed(activity, now);
  return <View style={styles.progress}>
    <Text selectable style={styles.muted}>{active ? 'Elapsed' : 'Total time'} {formatElapsed(elapsed.total)}{active && elapsed.stage !== null ? ` · This step ${formatElapsed(elapsed.stage)}` : ''}</Text>
    {!compact && <View style={styles.steps} accessibilityLabel="Analysis stages">
      {ANALYSIS_STAGES.map(([key, label]: string[]) => {
        const state = analysisStepState(activity, key);
        return <View key={key} accessibilityLabel={`${label}: ${state}`} style={[styles.step, state === 'current' && styles.current, state === 'complete' && styles.complete, state === 'failed' && styles.failed]}>
          {state === 'current' ? <ActivityIndicator size="small" color="#8AB2FF" />
            : <Ionicons name={state === 'complete' ? 'checkmark-circle-outline' : state === 'failed' ? 'alert-circle-outline' : 'ellipse-outline'} size={18} color={state === 'failed' ? '#FF7185' : '#8AB2FF'} />}
          <Text style={[styles.stepText, state === 'pending' && styles.pending]}>{label}</Text>
        </View>;
      })}
    </View>}
  </View>;
}

const styles = StyleSheet.create({
  identity: { flexDirection: 'row', gap: 12, alignItems: 'center', width: '100%' },
  identityCopy: { flex: 1, minWidth: 0, gap: 4 }, name: { color: '#F3F6FF', fontSize: 16, fontWeight: '700', flexShrink: 1 },
  thumbnail: { width: 62, height: 62, borderRadius: 10, backgroundColor: '#10141C' },
  muted: { color: '#A5B2C6', fontSize: 13, lineHeight: 19 }, progress: { gap: 12, width: '100%' },
  steps: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, step: { flexDirection: 'row', gap: 6, alignItems: 'center', paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: '#242F40' },
  current: { backgroundColor: '#102653', borderColor: '#8AB2FF' }, complete: { borderColor: '#285A4A' }, failed: { borderColor: '#FF7185' },
  stepText: { color: '#F3F6FF', fontSize: 13 }, pending: { color: '#A5B2C6' },
});
