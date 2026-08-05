import { afterEach, describe, expect, it } from 'vitest';
import { annotationDraftKey, clearAnnotationDraft, loadAnnotationDraft, saveAnnotationDraft } from './annotationDraft';

const annotation = {
  id: 'draft-1', status: 'bad' as const, start_ms: 0, end_ms: 0,
  systems: [], issue_types: [], landmarks: [], expected_behaviors: [], source_stages: [],
  severity: 'visual_only' as const, notes: 'Keep this text', keyframes: [], corrections: [],
};

afterEach(() => window.localStorage.clear());

describe('annotation drafts', () => {
  it('persists and clears a draft per analysis run', () => {
    saveAnnotationDraft('run-1', { annotation, editingAnnotationId: null, savedAt: 1 });
    expect(loadAnnotationDraft('run-1')?.annotation.notes).toBe('Keep this text');
    expect(loadAnnotationDraft('run-2')).toBeNull();
    clearAnnotationDraft('run-1');
    expect(window.localStorage.getItem(annotationDraftKey('run-1'))).toBeNull();
  });
});
