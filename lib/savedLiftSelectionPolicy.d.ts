export type SavedLiftView = 'list' | 'grid';

export function normalizeSavedLiftView(value: unknown): SavedLiftView;
export function normalizeSavedLiftIds(values: unknown): string[];
export function toggleSavedLiftSelection(selectedIds: string[], liftId: string): string[];
export function selectVisibleSavedLifts(selectedIds: string[], visibleIds: string[]): string[];
export function pruneSavedLiftSelection(selectedIds: string[], availableIds: string[]): string[];
