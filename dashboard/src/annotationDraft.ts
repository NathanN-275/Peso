import type { FeedbackAnnotation } from './api';

export type StoredAnnotationDraft = {
  annotation: FeedbackAnnotation;
  editingAnnotationId: string | null;
  savedAt: number;
};

const PREFIX = 'peso:analysis-annotation-draft:v1:';

export function annotationDraftKey(runId: string): string {
  return `${PREFIX}${runId}`;
}

export function loadAnnotationDraft(runId: string): StoredAnnotationDraft | null {
  try {
    const value = window.localStorage.getItem(annotationDraftKey(runId));
    if (!value) return null;
    const parsed = JSON.parse(value) as StoredAnnotationDraft;
    return parsed?.annotation && typeof parsed.savedAt === 'number' ? parsed : null;
  } catch {
    return null;
  }
}

export function saveAnnotationDraft(runId: string, draft: StoredAnnotationDraft): void {
  try {
    window.localStorage.setItem(annotationDraftKey(runId), JSON.stringify(draft));
  } catch {
    // Local drafts are best-effort; saving annotations remains available.
  }
}

export function clearAnnotationDraft(runId: string): void {
  try {
    window.localStorage.removeItem(annotationDraftKey(runId));
  } catch {
    // Storage can be unavailable in private browser contexts.
  }
}
