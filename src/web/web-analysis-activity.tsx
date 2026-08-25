import type * as ImagePicker from 'expo-image-picker';
import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AppState, Platform } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import { mergeAnalysisActivity, shouldPollAnalysisActivity } from '../../lib/analysisActivityPolicy';
import { getAnalysisActivity } from '../../lib/backendApi';
import { getFreshBackendAccessToken } from '../../lib/backendAuth';
import type {
  AnalysisActivityItem,
  AnalysisActivityResponse,
  VideoAnalysisStatus,
} from '../types/videoAnalysis';

const DEFAULT_ACTIVE_LIMIT = 3;
const OPTIMISTIC_STORAGE_PREFIX = 'peso.analysis-activity.optimistic';

type QueuedAnalysis = {
  videoId: string;
  jobId: string | null;
  status: VideoAnalysisStatus;
};

type WebAnalysisActivityContextValue = {
  items: AnalysisActivityItem[];
  activeCount: number;
  activeLimit: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<AnalysisActivityItem[]>;
  recordQueued: (activity: QueuedAnalysis) => void;
  removeActivity: (videoId: string) => void;
  pendingRecordedAsset: ImagePicker.ImagePickerAsset | null;
  setPendingRecordedAsset: (asset: ImagePicker.ImagePickerAsset | null) => void;
};

const WebAnalysisActivityContext = createContext<WebAnalysisActivityContextValue | null>(null);

function storageKey(userId: string) {
  return `${OPTIMISTIC_STORAGE_PREFIX}:${userId}`;
}

function readOptimisticItems(userId: string): AnalysisActivityItem[] {
  if (typeof window === 'undefined') return [];

  try {
    const value = JSON.parse(window.localStorage.getItem(storageKey(userId)) ?? '[]');
    return Array.isArray(value) ? mergeAnalysisActivity([], value, Date.now()) : [];
  } catch {
    return [];
  }
}

function writeOptimisticItems(userId: string, items: AnalysisActivityItem[]) {
  if (typeof window === 'undefined') return;

  if (items.length === 0) {
    window.localStorage.removeItem(storageKey(userId));
    return;
  }

  window.localStorage.setItem(storageKey(userId), JSON.stringify(items));
}

function optimisticActivity(activity: QueuedAnalysis): AnalysisActivityItem {
  const timestamp = new Date().toISOString();
  const processing = activity.status === 'processing';

  return {
    job_id: activity.jobId ?? `optimistic:${activity.videoId}`,
    video_id: activity.videoId,
    status: processing ? 'processing' : 'queued',
    stage: processing ? 'downloading' : 'queued',
    exercise_type: 'squat',
    view_type: 'side',
    created_at: timestamp,
    updated_at: timestamp,
    expires_at: null,
    thumbnail_url: null,
    stage_started_at: timestamp,
    stage_timestamps: { queued: timestamp },
    last_heartbeat_at: null,
    failure_class: null,
  };
}

export function useWebAnalysisActivity() {
  const value = use(WebAnalysisActivityContext);

  if (!value) {
    throw new Error('WebAnalysisActivityContext is unavailable');
  }

  return value;
}

export function WebAnalysisActivityProvider({ children }: { children: React.ReactNode }) {
  const { session, user } = useAuth();
  const [items, setItems] = useState<AnalysisActivityItem[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [activeLimit, setActiveLimit] = useState(DEFAULT_ACTIVE_LIMIT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [surfaceActive, setSurfaceActive] = useState(
    Platform.OS !== 'web' || typeof document === 'undefined' || document.visibilityState === 'visible'
  );
  const [pendingRecordedAsset, setPendingRecordedAsset] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const optimisticItemsRef = useRef<AnalysisActivityItem[]>([]);
  const itemsRef = useRef<AnalysisActivityItem[]>([]);

  useEffect(() => {
    if (!user?.id) {
      optimisticItemsRef.current = [];
      itemsRef.current = [];
      setItems([]);
      setActiveCount(0);
      setActiveLimit(DEFAULT_ACTIVE_LIMIT);
      setError(null);
      return;
    }

    const optimisticItems = readOptimisticItems(user.id);
    optimisticItemsRef.current = optimisticItems;
    itemsRef.current = optimisticItems;
    setItems(optimisticItems);
    setActiveCount(optimisticItems.filter((item) => item.status === 'queued' || item.status === 'processing').length);
  }, [user?.id]);

  useEffect(() => {
    if (Platform.OS === 'web') {
      const handleVisibility = () => setSurfaceActive(document.visibilityState === 'visible');
      document.addEventListener('visibilitychange', handleVisibility);
      return () => document.removeEventListener('visibilitychange', handleVisibility);
    }

    const subscription = AppState.addEventListener('change', (state) => {
      setSurfaceActive(state === 'active');
    });
    return () => subscription.remove();
  }, []);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!session?.access_token || !user?.id) {
      return [];
    }

    setLoading(itemsRef.current.length === 0);
    try {
      const accessToken = await getFreshBackendAccessToken();
      const response: AnalysisActivityResponse = await getAnalysisActivity(accessToken, signal);
      const mergedItems = mergeAnalysisActivity(response.items, optimisticItemsRef.current, Date.now());
      const serverVideoIds = new Set(response.items.map((item) => item.video_id));
      const remainingOptimisticItems = mergedItems.filter(
        (item) => item.job_id.startsWith('optimistic:') && !serverVideoIds.has(item.video_id)
      );

      optimisticItemsRef.current = remainingOptimisticItems;
      writeOptimisticItems(user.id, remainingOptimisticItems);
      itemsRef.current = mergedItems;
      setItems(mergedItems);
      setActiveCount(response.active_count);
      setActiveLimit(response.active_limit);
      setError(null);
      return mergedItems;
    } catch (refreshError) {
      if (signal?.aborted || (refreshError instanceof Error && refreshError.name === 'AbortError')) {
        return itemsRef.current;
      }

      const hasQueuedWork = itemsRef.current.some((item) => item.status === 'queued' || item.status === 'processing');
      setError(
        hasQueuedWork
          ? 'Your video is still queued. Activity could not refresh; retry in a moment.'
          : 'Unable to refresh analysis activity.'
      );
      return itemsRef.current;
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [session?.access_token, user?.id]);

  useEffect(() => {
    if (!session?.access_token || !user?.id || !surfaceActive) return;

    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const poll = async () => {
      const nextItems = await refresh(controller.signal);
      if (!active) return;

      if (shouldPollAnalysisActivity(nextItems, surfaceActive)) {
        timer = setTimeout(() => void poll(), 4000);
      }
    };

    void poll();
    return () => {
      active = false;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [refresh, session?.access_token, surfaceActive, user?.id]);

  const recordQueued = useCallback((activity: QueuedAnalysis) => {
    if (!user?.id) return;

    const optimistic = optimisticActivity(activity);
    const nextOptimisticItems = [
      optimistic,
      ...optimisticItemsRef.current.filter((item) => item.video_id !== optimistic.video_id),
    ];
    optimisticItemsRef.current = nextOptimisticItems;
    writeOptimisticItems(user.id, nextOptimisticItems);
    const nextItems = [optimistic, ...itemsRef.current.filter((item) => item.video_id !== optimistic.video_id)];
    itemsRef.current = nextItems;
    setItems(nextItems);
    setActiveCount((current) => Math.min(Math.max(current + 1, 1), activeLimit));
    setError(null);
  }, [activeLimit, user?.id]);

  const removeActivity = useCallback((videoId: string) => {
    if (user?.id) {
      const nextOptimisticItems = optimisticItemsRef.current.filter((item) => item.video_id !== videoId);
      optimisticItemsRef.current = nextOptimisticItems;
      writeOptimisticItems(user.id, nextOptimisticItems);
    }
    const nextItems = itemsRef.current.filter((item) => item.video_id !== videoId);
    itemsRef.current = nextItems;
    setItems(nextItems);
    setActiveCount((current) => Math.max(0, current - 1));
  }, [user?.id]);

  const value = useMemo(() => ({
    items,
    activeCount,
    activeLimit,
    loading,
    error,
    refresh: () => refresh(),
    recordQueued,
    removeActivity,
    pendingRecordedAsset,
    setPendingRecordedAsset,
  }), [
    activeCount,
    activeLimit,
    error,
    items,
    loading,
    pendingRecordedAsset,
    recordQueued,
    refresh,
    removeActivity,
  ]);

  return (
    <WebAnalysisActivityContext value={value}>
      {children}
    </WebAnalysisActivityContext>
  );
}
