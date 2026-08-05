import { createContext, use, useEffect, useMemo, useRef, useState } from 'react';
import {
  cancelDemoAnalysis,
  createIdleDemoAnalysis,
  progressDemoAnalysis,
  startDemoAnalysis,
  type DemoAnalysisPhase,
} from '../../lib/webDemoSessionPolicy';
import {
  createObjectUrlLease,
  type ObjectUrlLease,
} from '../../lib/webVideoSelectionPolicy';
import { createLocalVideoPreview } from '../utils/localVideoThumbnail';

export type WebDemoSession = {
  selectedFile: File | null;
  objectUrl: string | null;
  thumbnail: string | null;
  thumbnailStatus: 'empty' | 'loading' | 'ready' | 'fallback';
  filename: string | null;
  size: number | null;
  duration: number | null;
  phase: DemoAnalysisPhase;
  percentage: number;
  startTime: number | null;
};

type WebDemoSessionContextValue = {
  session: WebDemoSession;
  selectFile: (file: File) => Promise<void>;
  startAnalysis: () => void;
  cancelAnalysis: () => void;
  clearSession: () => void;
};

const emptySelection = {
  selectedFile: null,
  objectUrl: null,
  thumbnail: null,
  thumbnailStatus: 'empty' as const,
  filename: null,
  size: null,
  duration: null,
};

const initialSession: WebDemoSession = {
  ...emptySelection,
  ...createIdleDemoAnalysis(),
};

const WebDemoSessionContext = createContext<WebDemoSessionContextValue | null>(null);

export function useWebDemoSession() {
  const value = use(WebDemoSessionContext);

  if (!value) {
    throw new Error('WebDemoSessionContext is unavailable');
  }

  return value;
}

export function WebDemoSessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<WebDemoSession>(initialSession);
  const objectUrlLeaseRef = useRef<ObjectUrlLease | null>(null);
  const selectionVersionRef = useRef(0);

  const releaseSelectedFile = () => {
    selectionVersionRef.current += 1;
    objectUrlLeaseRef.current?.revoke();
    objectUrlLeaseRef.current = null;
  };

  const selectFile = async (file: File) => {
    releaseSelectedFile();
    const selectionVersion = selectionVersionRef.current;
    const objectUrlLease = createObjectUrlLease(file);
    objectUrlLeaseRef.current = objectUrlLease;

    setSession({
      ...emptySelection,
      ...createIdleDemoAnalysis(),
      selectedFile: file,
      objectUrl: objectUrlLease.url,
      thumbnailStatus: 'loading',
      filename: file.name,
      size: file.size,
    });

    try {
      const preview = await createLocalVideoPreview(objectUrlLease.url, {
        timeMs: 1_000,
        quality: 0.76,
      });

      if (selectionVersionRef.current !== selectionVersion) {
        return;
      }

      setSession((current) => ({
        ...current,
        thumbnail: preview.thumbnailUri,
        thumbnailStatus: 'ready',
        duration: preview.durationSeconds,
      }));
    } catch {
      if (selectionVersionRef.current !== selectionVersion) {
        return;
      }

      setSession((current) => ({
        ...current,
        thumbnail: null,
        thumbnailStatus: 'fallback',
        duration: null,
      }));
    }
  };

  const startAnalysis = () => {
    const analysis = startDemoAnalysis(Date.now());
    setSession((current) => ({ ...current, ...analysis }));
  };

  const cancelAnalysis = () => {
    setSession((current) => ({ ...current, ...cancelDemoAnalysis() }));
  };

  const clearSession = () => {
    releaseSelectedFile();
    setSession(initialSession);
  };

  useEffect(() => {
    if (session.startTime === null || session.phase === 'ready') {
      return;
    }

    const updateProgress = () => {
      setSession((current) => {
        if (current.startTime === null) {
          return current;
        }

        return {
          ...current,
          ...progressDemoAnalysis(current.startTime, Date.now()),
        };
      });
    };

    updateProgress();
    const timer = window.setInterval(updateProgress, 100);
    return () => window.clearInterval(timer);
  }, [session.phase, session.startTime]);

  useEffect(
    () => () => {
      objectUrlLeaseRef.current?.revoke();
    },
    []
  );

  const value = useMemo(
    () => ({ session, selectFile, startAnalysis, cancelAnalysis, clearSession }),
    [session]
  );

  return (
    <WebDemoSessionContext value={value}>
      {children}
    </WebDemoSessionContext>
  );
}
